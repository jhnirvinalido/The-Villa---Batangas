"""Maintenance lifecycle, persistence, evidence and authorization boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import maintenance as module
from live_updates import mutation_tables


class TaskStore:
    def __init__(self):
        self.records = []
        self.people = []
        self.catalog = []
        self.bookings = []
        self.notifications = []
        self.table_name = None
        self.filters = []
        self.changes = None
        self.inserted = None
        self.calls = []
        self.row_range = None

    def table(self, name):
        self.table_name = name
        self.filters = []
        self.changes = None
        self.inserted = None
        self.row_range = None
        self.calls.append(name)
        return self

    def select(self, *_): return self
    def order(self, *_, **__): return self
    def limit(self, *_): return self
    def range(self, start, end): self.row_range = (start, end); return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def is_(self, key, _): self.filters.append((key, None)); return self
    def in_(self, key, values): self.filters.append((key, values)); return self
    def insert(self, value): self.inserted = deepcopy(value); return self
    def upsert(self, value, **_): self.inserted = deepcopy(value); return self
    def update(self, value): self.changes = deepcopy(value); return self

    def execute(self):
        if self.table_name == 'villa_catalog':
            if self.inserted:
                self.catalog = [record for record in self.catalog if record['id'] != self.inserted['id']] + [self.inserted]
            return SimpleNamespace(data=deepcopy([record for record in self.catalog if all(record.get(k) == v for k, v in self.filters)]))
        if self.table_name == 'staff_accounts':
            return SimpleNamespace(data=deepcopy([person for person in self.people if all(person.get(k) in v if isinstance(v, list) else person.get(k) == v for k, v in self.filters)]))
        if self.table_name == 'bookings':
            return SimpleNamespace(data=deepcopy(self.bookings))
        if self.table_name == 'admin_notifications':
            if self.inserted and not any(item['id'] == self.inserted['id'] for item in self.notifications): self.notifications.append(self.inserted)
            return SimpleNamespace(data=[])
        if self.table_name != 'admin_tasks': return SimpleNamespace(data=[])
        if self.inserted is not None:
            record = {**self.inserted, 'id': str(uuid4()), 'created_at': '2026-10-27T01:00:00+00:00', 'updated_at': '2026-10-27T01:00:00+00:00'}
            self.records.append(record)
            return SimpleNamespace(data=[deepcopy(record)])
        found = [record for record in self.records if all(record.get(k) in v if isinstance(v, list) else record.get(k) == v for k, v in self.filters)]
        if self.changes:
            for record in found: record.update(self.changes)
        if self.row_range:
            found = found[self.row_range[0]:self.row_range[1] + 1]
        return SimpleNamespace(data=deepcopy(found))


class MaintenanceTests(TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.staff_id = str(uuid4())
        self.context = {'account': {'id': str(uuid4()), 'full_name': 'Villa Admin'}}
        self.person = {'id': self.staff_id, 'role': 'staff', 'department': 'Maintenance', 'full_name': 'Technician', 'position': 'Technician', 'is_active': True, 'account_status': 'Active', 'email': 'login@example.com', 'personal_email': 'technician@example.com', 'phone': '+639171234567'}
        self.patchers = [patch.object(module, 'service_client', return_value=self.store), patch.object(module, 'fetch_staff', return_value=self.person), patch.object(module, 'emit_table')]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)
        self.payload = dict(title='Water pump repair', description='Pool pump does not turn on.', assignedStaffId=self.staff_id, location='Pool pump room')

    def create(self, **overrides):
        return module.create_maintenance(module.MaintenanceRequest(**{**self.payload, **overrides}), self.context)['data']

    def test_maintenance_assignment_requires_personal_email(self):
        with patch.object(module, 'fetch_staff', return_value={**self.person, 'personal_email': ''}):
            with self.assertRaises(module.HTTPException) as caught:
                module.technician(self.staff_id)
        self.assertEqual(caught.exception.status_code, 422)

    def test_maintenance_admin_serialization_exposes_email_not_phone(self):
        with patch.object(module, 'task_api', return_value={'id': 'maintenance-1'}):
            serialized = module.serialize(
                {'notes': '', 'status_history': []},
                {'email': 'login@example.com', 'personal_email': 'technician@example.com', 'phone': '+639171234567'},
            )
        self.assertEqual(serialized['technicianEmail'], 'technician@example.com')
        self.assertNotIn('technicianPhone', serialized)

    def update(self, row, status, **overrides):
        request = module.MaintenanceUpdate(**{**self.payload, 'status': status, 'expectedUpdatedAt': row['updatedAt'], **overrides})
        return module.update_maintenance(row['id'], request, self.context)['data']

    def accept(self, row):
        return self.update(row, 'Pending', responseAction='Accepted', expectedArrival=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), contactMethod='Phone call')

    def test_start_requires_confirmed_availability(self):
        row = self.create()
        self.assertEqual(row['maintenance']['onCall']['state'], 'Awaiting response')
        self.assertIsNone(row['dueDate'])
        with self.assertRaises(HTTPException) as caught: self.update(row, 'In Progress')
        self.assertEqual(caught.exception.status_code, 409)

    def test_automatic_contact_does_not_need_a_fixed_shift(self):
        self.store.people = [self.person]
        row = self.create(assignedStaffId=None)
        self.assertEqual(row['assignedStaffId'], self.staff_id)
        self.assertEqual(row['maintenance']['onCall']['state'], 'Awaiting response')

    def test_create_persists_request_independently_of_a_booking(self):
        row = self.create(contactMethod='Phone call', contactNotes='Technician called at 10 AM.', equipment='Pump', repairCost='125.50')
        self.assertEqual(row['status'], 'Pending')
        self.assertEqual(row['maintenance']['repairCost'], '125.50')
        self.assertEqual(row['maintenance']['contactMethod'], 'Phone call')
        self.assertTrue(row['maintenance']['contactedAt'])
        self.assertFalse(row['fromBooking'])
        self.assertEqual(self.store.records[0]['source'], module.SOURCE)
        self.assertIsNone(self.store.records[0].get('booking_id'))
        # Re-loading reconstructs metadata from persisted audit events.
        loaded = module.list_maintenance(self.context)['data'][0]
        self.assertEqual(loaded['maintenance']['equipment'], 'Pump')
        self.assertEqual(loaded['maintenance']['contactNotes'], 'Technician called at 10 AM.')

    def test_requires_active_maintenance_technician(self):
        for change in ({'department': 'Housekeeping'}, {'is_active': False}, {'role': 'admin'}, {'account_status': 'Disabled'}):
            with self.subTest(change=change), patch.object(module, 'fetch_staff', return_value={**self.person, **change}):
                with self.assertRaises(HTTPException) as caught: self.create()
                self.assertEqual(caught.exception.status_code, 422)
        self.assertFalse(self.store.records)

    def test_complete_repair_lifecycle_and_lock_verified_record(self):
        row = self.accept(self.create())
        row = self.update(row, 'In Progress', repairNotes='Diagnosing electrical supply.')
        self.assertTrue(row['startedAt'])
        row = self.update(row, 'Pending Review', repairNotes='Replaced failed pump capacitor.')
        self.assertEqual(row['progress'], 100)
        with self.assertRaises(HTTPException): self.update(row, 'Completed', repairNotes='Replaced failed pump capacitor.')
        row = self.update(row, 'Completed', repairNotes='Replaced failed pump capacitor.', verificationNote='Pump tested and working normally.')
        self.assertEqual(row['approvedByStaffId'], self.context['account']['id'])
        self.assertEqual(len(row['statusHistory']), 5)
        self.assertTrue(all(item['done'] for item in row['checklist']))
        with self.assertRaises(HTTPException) as caught: self.update(row, 'In Progress')
        self.assertEqual(caught.exception.status_code, 409)

    def test_no_skipping_review_and_no_review_while_waiting_for_parts(self):
        row = self.create()
        with self.assertRaises(HTTPException): self.update(row, 'Completed', repairNotes='Fixed pump.', verificationNote='Checked pump.')
        row = self.accept(row)
        row = self.update(row, 'In Progress', waitingForParts=True, partsNotes='Waiting for a capacitor.')
        self.assertTrue(row['maintenance']['waitingForParts'])
        with self.assertRaises(HTTPException): self.update(row, 'Pending Review', waitingForParts=True, partsNotes='Waiting for a capacitor.', repairNotes='Still awaiting replacement.')
        self.assertEqual(self.store.records[0]['status'], 'In Progress')

    def test_stale_edit_and_nonmaintenance_id_cannot_be_updated(self):
        row = self.accept(self.create())
        updated = self.update(row, 'In Progress')
        with self.assertRaises(HTTPException) as caught: self.update(row, 'In Progress')
        self.assertEqual(caught.exception.status_code, 409)
        self.store.records[0]['source'] = 'automatic-booking-preparation'
        with self.assertRaises(HTTPException) as caught: self.update(updated, 'Pending Review')
        self.assertEqual(caught.exception.status_code, 404)

    def test_public_and_staff_access_cannot_call_admin_routes(self):
        app = FastAPI()
        app.include_router(module.router)
        with TestClient(app) as client:
            self.assertEqual(client.get('/admin/maintenance').status_code, 401)
            self.assertEqual(client.post('/admin/maintenance', json=self.payload).status_code, 401)
        def deny_staff(): raise HTTPException(status_code=403, detail='Administrator access required.')
        app.dependency_overrides[module.require_admin] = deny_staff
        with TestClient(app) as client:
            self.assertEqual(client.get('/admin/maintenance').status_code, 403)
            self.assertEqual(client.post('/admin/maintenance', json=self.payload).status_code, 403)

    def test_input_guards_for_evidence_contact_and_location(self):
        for overrides in ({'location': '  '}, {'title': '   '}, {'messengerUrl': 'javascript:alert(1)'}, {'messengerUrl': 'https://m.me.evil.test/technician'}, {'messengerUrl': 'https://user:pass@m.me/name'}, {'repairCost': '-1'}, {'waitingForParts': True}, {'photos': [{'name': 'payload.svg', 'url': 'data:image/svg+xml;base64,PHN2Zz4='}]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                module.MaintenanceRequest(**{**self.payload, **overrides})

    def test_maintenance_events_use_existing_scoped_task_channel(self):
        self.assertEqual(mutation_tables('/admin/maintenance'), ['admin_tasks'])
        self.assertEqual(mutation_tables('/admin/maintenance/'+str(uuid4())), ['admin_tasks'])


class MaintenanceEmailContactTests(TestCase):
    def test_email_contact_is_accepted_and_preserved_in_request_history(self):
        data = module.MaintenanceRequest(title='Inspect pool pump', description='The pool pump needs inspection.', villaId='villa-1', contactMethod='Email')
        self.assertEqual(data.contact_method, 'Email')
        self.assertEqual(module.request_snapshot(data)['contactMethod'], 'Email')
