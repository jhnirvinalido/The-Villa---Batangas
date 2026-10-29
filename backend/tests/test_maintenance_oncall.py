from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fastapi import FastAPI, Response, HTTPException
from fastapi.testclient import TestClient
import maintenance as domain
import maintenance_oncall as oncall
from test_maintenance import MaintenanceTests


class OnCallTests(MaintenanceTests):
    def setUp(self):
        super().setUp()
        self.now = datetime.now(timezone.utc)
        self.store.people = [self.person, {**self.person, 'id': self.context['account']['id'], 'role': 'admin'}]
        for p in [patch.object(oncall, 'service_client', return_value=self.store), patch.object(oncall, 'emit_table'),
                  patch.object(oncall, 'signing_secret', return_value='test-only-secret'), patch.object(oncall, 'utcnow', return_value=self.now)]:
            p.start(); self.addCleanup(p.stop)

    def raw(self): return deepcopy(self.store.records[0])
    def state(self): return domain.details(self.raw())['onCall']
    def tick(self, minutes=0): oncall.process_maintenance_oncall(self.store, self.now + timedelta(minutes=minutes))

    def test_tokens_are_scoped_expire_and_reassignment_replaces_them(self):
        self.create(); row = self.raw(); token = oncall.response_token(row)
        self.assertEqual(oncall.authorize_reply(self.store, row['id'], token)['id'], row['id'])
        for invalid in ['', 'a' * 64]:
            with self.assertRaises(HTTPException): oncall.authorize_reply(self.store, row['id'], invalid)
        row['assigned_staff_id'] = 'different-technician'
        self.assertNotEqual(oncall.response_token(row), token)
        with patch.object(oncall, 'utcnow', return_value=self.now + timedelta(days=2)), self.assertRaises(HTTPException) as caught:
            oncall.authorize_reply(self.store, row['id'], token)
        self.assertEqual(caught.exception.status_code, 410)

    def test_public_get_is_read_only_and_reply_is_explicit_once(self):
        self.create(); row = self.raw(); token = oncall.response_token(row)
        app = FastAPI(); app.include_router(oncall.public_router)
        with TestClient(app) as client:
            path = f"/maintenance-response/{row['id']}"; headers = {'X-Maintenance-Token': token}
            response = client.get(path, headers=headers)
            self.assertEqual(response.status_code, 200)
            for private in ['nonce', 'repairCost', 'technicianPhone', 'technicianEmail', 'statusHistory', 'contactNotes']:
                self.assertNotIn(private, response.json()['data'])
            self.assertEqual(len(self.raw()['status_history']), 1)
            self.assertEqual(client.get(path).status_code, 403)
            result = client.post(path, headers=headers, json={'decision': 'Accepted', 'expectedArrival': (self.now + timedelta(hours=2)).isoformat()})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.state()['state'], 'Accepted')
            self.assertEqual(self.raw()['status'], 'Pending')
            self.assertEqual(client.post(path, headers=headers, json={'decision': 'Unavailable', 'notes': 'Cannot attend'}).status_code, 409)
            self.assertFalse(client.get(path, headers=headers).json()['data']['canRespond'])
        self.assertEqual(len(self.store.notifications), 1)

    def test_reminder_then_backup_are_persisted_and_never_assume_acceptance(self):
        backup = {**self.person, 'id': '00000000-0000-4000-8000-000000000002'}
        self.store.people.append(backup)
        self.create(responseWindowMinutes=10)
        with patch.object(oncall, 'send_notice', return_value=('accepted', 'SMS', '')) as send:
            self.tick(); self.tick(1)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(self.state()['state'], 'Awaiting response')
            self.tick(11); self.tick(11)
            self.assertEqual(send.call_count, 2)
            self.tick(22); self.assertEqual(self.state()['state'], 'No response')
            self.tick(22)
            self.assertEqual(self.raw()['assigned_staff_id'], backup['id'])
            self.assertEqual(self.state()['round'], 2)
            self.assertEqual(self.raw()['status'], 'Pending')

    def test_stale_worker_and_ambiguous_delivery_cannot_send_twice(self):
        self.create(); old = self.raw()
        with patch.object(oncall, 'send_notice', return_value=('uncertain', 'SMS', 'Check provider before resending')) as send:
            self.tick(); oncall.process_one(self.store, old, self.now); self.tick(30)
            self.assertEqual(send.call_count, 1)
        self.assertTrue(self.state()['attentionNeeded'])
        self.assertEqual(self.state()['notification']['state'], 'uncertain')

    def test_expired_worker_lease_is_escalated_without_resending(self):
        self.create(); row = self.raw(); snapshot = domain.details(row)
        snapshot['onCall']['notification'].update(state='sending', lease='old', leaseExpiresAt=(self.now - timedelta(minutes=1)).isoformat())
        oncall.cas(self.store, row, snapshot, 'Test claim', now=self.now)
        with patch.object(oncall, 'send_notice') as send: self.tick(); self.tick(10); send.assert_not_called()
        self.assertEqual(self.state()['notification']['state'], 'uncertain')

    def test_call_reply_cancels_pending_notification_and_proposal_needs_approval(self):
        row = self.create()
        row = self.update(row, 'Pending', responseAction='Proposed time', expectedArrival=(self.now + timedelta(hours=2)).isoformat(), responseNotes='Can attend later', contactMethod='Messenger')
        with patch.object(oncall, 'send_notice') as send: self.tick(); send.assert_not_called()
        with self.assertRaises(HTTPException): self.update(row, 'In Progress')
        row = self.update(row, 'In Progress', responseAction='Accepted', expectedArrival=(self.now + timedelta(hours=2)).isoformat(), contactMethod='Messenger')
        self.assertEqual(row['status'], 'In Progress')
        self.assertEqual(row['maintenance']['onCall']['state'], 'Accepted')

    def test_overdue_arrival_alerts_once_without_reassigning_confirmed_work(self):
        self.accept(self.create())
        self.tick(121); self.tick(122)
        self.assertTrue(self.state()['arrivalAlerted'])
        self.assertEqual(self.state()['state'], 'Accepted')
        self.assertEqual(len(self.store.notifications), 1)

    def test_suggested_maintenance_arrival_can_be_after_fourteen_days(self):
        from booking_assignments import MANILA

        now = datetime(2026, 10, 30, 7, 0, tzinfo=MANILA)
        target_date = (now + timedelta(days=30)).date()
        periods = [{
            'villaId': 'villa-1',
            'bookingId': 'future-booking',
            'checkInDate': target_date.isoformat(),
            'checkOutDate': (target_date + timedelta(days=1)).isoformat(),
            'checkInTime': '3:00 PM',
        }]
        with patch.object(oncall, 'booked_periods', return_value=periods):
            suggestion = oncall.suggest_maintenance_schedule(
                self.store,
                'villa-1',
                now=now,
            )

        self.assertIsNotNone(suggestion['suggestedArrival'])
        self.assertGreater(
            oncall.parse(suggestion['suggestedArrival']),
            now + timedelta(days=14),
        )
        self.assertLess(
            oncall.parse(suggestion['suggestedArrival']),
            oncall.parse(f"{target_date.isoformat()}T15:00:00+08:00"),
        )

    def test_technician_arrival_after_fourteen_days_is_valid(self):
        from maintenance_oncall import arrival_time

        now = self.now
        arrival = now + timedelta(days=30)
        self.assertEqual(arrival_time(arrival, now), arrival.isoformat())

    def test_configuration_and_transport_outcomes(self):
        import booking
        self.create(); row = self.raw()
        with patch.dict('os.environ', {'MAINTENANCE_FRONTEND_URL': 'http://localhost:5173'}), patch.object(booking, '_smtp_configured', return_value=True), patch.object(oncall.smtplib, 'SMTP') as send:
            self.assertEqual(oncall.send_notice(row, self.person)[0], 'blocked'); send.assert_not_called()
        with patch.dict('os.environ', {'MAINTENANCE_FRONTEND_URL': 'https://villa.example', 'HTTPSMS_API_KEY': 'test-key', 'HTTPSMS_FROM': '+639171234568'}), patch.object(booking, '_smtp_configured', return_value=False), patch.object(oncall.smtplib, 'SMTP') as send:
            self.assertEqual(oncall.send_notice(row, self.person)[0], 'blocked'); send.assert_not_called()

    def test_main_registers_admin_link_and_private_public_response_routes(self):
        import main
        client = TestClient(main.app)
        request_id = '00000000-0000-4000-8000-000000000002'
        self.assertEqual(client.get(f'/admin/maintenance/{request_id}/response-link').status_code, 401)
        self.assertEqual(client.get('/staff/villa-operations').status_code, 401)
        response = client.get(f'/maintenance-response/{request_id}')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_smtp_quit_failure_after_acceptance_does_not_cause_resend(self):
        import booking
        self.create()
        with patch.dict('os.environ', {'MAINTENANCE_FRONTEND_URL': 'https://villa.example', 'HTTPSMS_API_KEY': 'test-key', 'HTTPSMS_FROM': '+639171234568'}), patch.object(booking, '_smtp_configured', return_value=True), patch.object(booking, 'SMTP_FROM', 'villa@example.com'), patch.object(oncall.smtplib, 'SMTP') as smtp:
            smtp_instance = smtp.return_value.__enter__.return_value
            smtp_instance.send_message.return_value = {}
            smtp.return_value.__exit__.side_effect = OSError('QUIT failed')
            result = oncall.send_notice(self.raw(), {**self.person, 'personal_email': 'technician@example.com'})
        self.assertEqual(result[:2], ('accepted', 'Email'))
        self.assertEqual(smtp_instance.send_message.call_args.args[0]['To'], 'technician@example.com')

    def test_staff_start_requires_acceptance_and_ignores_fixed_shift_for_confirmed_work(self):
        import staff
        row = self.create()
        context = {'account': self.person}
        with patch.object(staff, 'fetch_task', side_effect=lambda _: self.raw()), patch.object(staff, 'service_client', return_value=self.store), patch.object(staff, 'notify_admins'):
            with self.assertRaises(HTTPException) as caught:
                staff.staff_update_task(row['id'], staff.StaffTaskUpdateRequest(status='In Progress'), context)
            self.assertEqual(caught.exception.status_code, 409)
            row = self.accept(row)
            self.store.records[0]['due_date'] = '2020-01-01'
            result = staff.staff_update_task(row['id'], staff.StaffTaskUpdateRequest(status='In Progress', expectedUpdatedAt=row['updatedAt']), context)
            self.assertEqual(result['data']['status'], 'In Progress')
