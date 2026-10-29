from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
import maintenance as domain
import staff_villa_operations as staff_ops
import villa_catalog as catalog
from villa_operations import apply_operational_status
from test_maintenance import TaskStore


class VillaOperationsTests(TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.store.catalog = [{**deepcopy(catalog.DEFAULT_VILLA_CATALOG[0]), 'status': 'Available'}]
        self.person = {'id': str(uuid4()), 'role': 'staff', 'department': 'Maintenance', 'full_name': 'Technician', 'position': 'Technician', 'is_active': True, 'account_status': 'Active'}
        self.store.people = [self.person]
        self.context = {'account': {'id': str(uuid4()), 'full_name': 'Administrator'}}
        for p in [patch.object(domain, 'service_client', return_value=self.store), patch.object(domain, 'fetch_staff', return_value=self.person),
                  patch.object(domain, 'get_villa_catalog_map', side_effect=lambda: catalog.get_villa_catalog_map(self.store)), patch.object(domain, 'emit_table'),
                  patch.object(staff_ops, 'service_client', return_value=self.store), patch.object(catalog, '_service', return_value=self.store), patch.object(catalog, '_require_admin', return_value={'id': self.context['account']['id']})]:
            p.start(); self.addCleanup(p.stop)

    def create(self, **changes):
        return domain.create_maintenance(domain.MaintenanceRequest(title='Inspect Villa 1', description='Check pool pump and electrical connections.', villaId='villa-1', kind='Inspection', **changes), self.context)['data']

    def update(self, row, **changes):
        data = {'title': row['title'], 'description': row['description'], 'villaId': 'villa-1', 'kind': 'Inspection', 'blocksBooking': row['maintenance']['blocksBooking'],
                'assignedStaffId': self.person['id'], 'expectedUpdatedAt': row['updatedAt'], 'status': row['status'], **changes}
        return domain.update_maintenance(row['id'], domain.MaintenanceUpdate(**data), self.context)['data']

    def test_villa_request_does_not_pause_bookings_before_admin_approval(self):
        self.create(blocksBooking=True)
        villa = catalog._read_rows(self.store)[0]
        self.assertEqual(villa['status'], 'Available')
        self.assertEqual(villa['operations'], {'open': 1, 'blocking': 0, 'inspections': 1, 'forVerification': 0, 'hasHistory': True})
        self.assertFalse(domain.details(self.store.records[0])['blocksBooking'])

    def test_booking_map_remains_blocked_until_every_blocking_request_is_verified(self):
        first = self.create(); second = self.create()
        self.assertEqual(catalog.get_villa_catalog_map(self.store)['villa-1']['operational_status'], 'available')
        first = self.update(first, status='In Progress', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')
        second = self.update(second, status='In Progress', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')
        self.assertEqual(catalog.get_villa_catalog_map(self.store)['villa-1']['operational_status'], 'under_maintenance')
        first = self.update(first, status='Pending Review', repairNotes='Inspection completed and pump tested.')
        self.assertEqual(catalog._read_rows(self.store)[0]['operations']['forVerification'], 1)
        self.update(first, status='Completed', repairNotes='Inspection completed and pump tested.', verificationNote='Pump tested and villa ready for guests.')
        self.assertEqual(catalog._read_rows(self.store)[0]['status'], 'Under Maintenance')
        self.update(second, status='Cancelled', verificationNote='Duplicate inspection; original inspection verified.')
        self.assertEqual(catalog.get_villa_catalog_map(self.store)['villa-1']['operational_status'], 'available')

    def test_catalog_cannot_reopen_active_work_or_persist_a_derived_block(self):
        request = self.create()
        self.update(request, status='In Progress', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')
        values = dict(title='Villa 1', landing_title='Family Villa', price=5000, capacity=8, details='A comfortable private villa.')
        with self.assertRaises(HTTPException) as caught:
            catalog.update_villa_catalog('villa-1', catalog.VillaCatalogUpdate(**values, status='Available'), None)
        self.assertEqual(caught.exception.status_code, 409)
        result = catalog.update_villa_catalog('villa-1', catalog.VillaCatalogUpdate(**values, status='Under Maintenance'), None)
        self.assertEqual(result['data']['status'], 'Under Maintenance')
        self.assertEqual(self.store.catalog[0]['status'], 'Available')
        self.assertEqual(self.store.catalog[0]['price'], 5000)

    def test_cannot_clear_a_block_or_move_it_without_verification(self):
        row = self.create()
        row = self.update(row, status='In Progress', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')
        for changes in [{'blocksBooking': False}, {'villaId': 'villa-2'}, {'status': 'Cancelled'}]:
            with self.subTest(changes=changes), self.assertRaises(HTTPException): self.update(row, **changes)

    def test_staff_can_report_but_cannot_submit_prices_assignments_or_approvals(self):
        app = FastAPI(); app.include_router(staff_ops.router)
        payload = dict(villaId='villa-1', kind='Repair', title='Air conditioner failed', description='Room is hot and the unit will not start.', blocksBooking=True)
        with TestClient(app) as client: self.assertEqual(client.post('/staff/villa-operations', json=payload).status_code, 401)
        app.dependency_overrides[staff_ops.require_staff] = lambda: self.context
        with TestClient(app) as client:
            self.assertEqual(client.post('/staff/villa-operations', json={**payload, 'price': 1, 'status': 'Completed'}).status_code, 422)
            self.assertEqual(client.post('/staff/villa-operations', json=payload).status_code, 201)
            result = client.get('/staff/villa-operations').json()['data']
        self.assertEqual(result['villas'][0]['status'], 'Available')
        self.assertEqual(len(result['reports']), 1)
        self.assertFalse(result['reports'][0]['maintenance']['blocksBooking'])
        self.assertNotIn('repairCost', result['reports'][0])
        self.assertEqual(self.store.records[0]['created_by_staff_id'], self.context['account']['id'])

    def test_manual_block_is_preserved_after_all_work_is_closed(self):
        villa = apply_operational_status([{'id': 'villa-1', 'status': 'Under Maintenance'}], self.store)[0]
        self.assertEqual(villa['manual_status'], 'Under Maintenance')
        self.assertEqual(villa['status'], 'Under Maintenance')

    def test_availability_checks_include_blocking_requests_beyond_first_page(self):
        self.store.records = [{'id': str(index), 'source': domain.SOURCE, 'status': 'Pending', 'status_history': [
            {'maintenance': {'villaId': 'villa-1', 'blocksBooking': index == 500, 'kind': 'Inspection'}}
        ]} for index in range(501)]
        villa = catalog._read_rows(self.store)[0]
        self.assertEqual(villa['operations']['open'], 501)
        self.assertEqual(villa['status'], 'Under Maintenance')

    def test_admin_created_work_is_available_to_assigned_maintenance_portal_and_reopens_villa(self):
        import staff
        self.store.catalog[0]['status'] = 'Under Maintenance'
        row = self.create()
        technician_context = {'account': self.person}
        work = staff_ops.staff_villas(technician_context)['data']['reports'][0]
        self.assertTrue(work['assignedToMe'])
        self.assertEqual(work['maintenance']['villaId'], 'villa-1')
        self.assertTrue(work['checklist'])
        with patch('maintenance_oncall.service_client', return_value=self.store), patch('maintenance_oncall.emit_table'), patch('maintenance_oncall.notify_admins'):
            result = staff_ops.staff_availability(row['id'], staff_ops.StaffAvailability(
                expectedUpdatedAt=work['updatedAt'], decision='Accepted', expectedArrival=datetime.now(timezone.utc) + timedelta(hours=1)), technician_context)
        self.assertEqual(result['data']['maintenance']['onCall']['state'], 'Accepted')
        self.assertEqual(catalog._read_rows(self.store)[0]['status'], 'Under Maintenance')
        # Admin confirmation is the boundary that blocks new reservations.
        approved = self.update(result['data'], status='In Progress')
        self.assertTrue(approved['maintenance']['blocksBooking'])
        with patch.object(staff, 'fetch_task', side_effect=lambda _: deepcopy(self.store.records[0])), patch.object(staff, 'service_client', return_value=self.store), patch.object(staff, 'notify_admins'):
            started = staff.staff_update_task(row['id'], staff.StaffTaskUpdateRequest(status='In Progress', expectedUpdatedAt=approved['updatedAt']), technician_context)['data']
            waiting = staff.staff_update_task(row['id'], staff.StaffTaskUpdateRequest(status='In Progress', expectedUpdatedAt=started['updatedAt'], waitingForParts=True, partsNotes='Replacement capacitor required.'), technician_context)['data']
            self.assertTrue(domain.details(self.store.records[0])['waitingForParts'])
            reviewed = staff.staff_update_task(row['id'], staff.StaffTaskUpdateRequest(status='Pending Review', expectedUpdatedAt=waiting['updatedAt'], checklist=[{**item, 'done': True} for item in waiting['checklist']], notes='Replaced capacitor and tested the pool pump.', waitingForParts=False, partsNotes='Capacitor fitted.'), technician_context)['data']
        self.assertEqual(catalog._read_rows(self.store)[0]['status'], 'Under Maintenance')
        self.assertEqual(reviewed['status'], 'Pending Review')
        self.update(domain.serialize(self.store.records[0], self.person), status='Completed', repairNotes='Replaced capacitor and tested the pool pump.', verificationNote='Pump tested and villa ready for guests.')
        villa = catalog._read_rows(self.store)[0]
        self.assertEqual(villa['status'], 'Available')
        self.assertTrue(villa['operations']['hasHistory'])
        self.assertEqual(staff_ops.staff_villas(technician_context)['data']['reports'][0]['status'], 'Completed')

    def test_another_staff_member_cannot_respond_or_receive_editable_work_details(self):
        row = self.create()
        other = {'account': {'id': str(uuid4()), 'full_name': 'Other Staff'}}
        work = staff_ops.staff_villas(other)['data']['reports'][0]
        self.assertFalse(work['assignedToMe'])
        self.assertEqual(work['checklist'], [])
        with patch('maintenance_oncall.service_client', return_value=self.store), self.assertRaises(HTTPException) as caught:
            staff_ops.staff_availability(row['id'], staff_ops.StaffAvailability(expectedUpdatedAt=row['updatedAt'], decision='Accepted', expectedArrival=datetime.now(timezone.utc) + timedelta(hours=1)), other)
        self.assertEqual(caught.exception.status_code, 403)

    def test_staff_availability_rejects_arrival_during_a_guest_booking(self):
        row = self.create()
        from zoneinfo import ZoneInfo
        manila = ZoneInfo('Asia/Manila')
        booked_date = datetime.now(manila).date() + timedelta(days=2)
        arrival = datetime.combine(booked_date, time(16), manila)
        self.store.bookings = [{
            'id': str(uuid4()), 'villa_id': 'villa-1', 'villa_ids': ['villa-1'],
            'check_in_date': booked_date.isoformat(), 'check_out_date': (booked_date + timedelta(days=1)).isoformat(),
            'check_in_time': '15:00', 'check_out_time': '11:00 AM', 'booking_status': 'Confirmed',
        }]
        with patch('maintenance_oncall.service_client', return_value=self.store), self.assertRaises(HTTPException) as caught:
            staff_ops.staff_availability(row['id'], staff_ops.StaffAvailability(
                expectedUpdatedAt=row['updatedAt'], decision='Accepted', expectedArrival=arrival), {'account': self.person})
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn(booked_date.isoformat(), caught.exception.detail)
        self.assertEqual(domain.details(self.store.records[0])['onCall']['state'], 'Awaiting response')

    def test_arrival_before_checkin_is_allowed_and_checkout_day_stays_reserved(self):
        from maintenance_oncall import ensure_arrival_not_booked
        from zoneinfo import ZoneInfo
        manila = ZoneInfo('Asia/Manila')
        booked_date = datetime.now(manila).date() + timedelta(days=2)
        self.store.bookings = [{
            'id': str(uuid4()), 'villa_id': 'villa-1', 'villa_ids': ['villa-1'],
            'check_in_date': booked_date.isoformat(), 'check_out_date': (booked_date + timedelta(days=1)).isoformat(),
            'check_in_time': '15:00', 'booking_status': 'Confirmed',
        }]
        with patch('maintenance_oncall.service_client', return_value=self.store):
            ensure_arrival_not_booked(self.store, 'villa-1', datetime.combine(booked_date, time(14, 59), manila))
            with self.assertRaises(HTTPException):
                ensure_arrival_not_booked(self.store, 'villa-1', datetime.combine(booked_date + timedelta(days=1), time(11), manila))

    def test_price_edits_cannot_set_maintenance_or_reblock_a_verified_villa(self):
        values = dict(title='Villa 1', landing_title='Family Villa', price=5000, capacity=8, details='A comfortable private villa.')
        with self.assertRaises(HTTPException): catalog.update_villa_catalog('villa-1', catalog.VillaCatalogUpdate(**values, status='Under Maintenance'), None)
        request = self.create()
        self.update(request, status='In Progress', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')
        result = catalog.update_villa_catalog('villa-1', catalog.VillaCatalogUpdate(**values), None)
        self.assertEqual(result['data']['status'], 'Under Maintenance')
