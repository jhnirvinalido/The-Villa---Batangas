import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

from live_updates import LiveHub, Subscriber, emit_table, mutation_tables, _stream


class StreamHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_reports_database_connection_loss_and_recovery(self):
        hub = LiveHub()
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

        async def timeout(awaitable, timeout):
            awaitable.close()
            raise asyncio.TimeoutError

        with patch('live_updates.hub', hub), patch('live_updates.asyncio.wait_for', timeout):
            stream = _stream(request, 'staff', 'staff-1')
            try:
                ready = await anext(stream)
                self.assertIn('event: ready', ready)
                for connected in (True, False, True):
                    hub.database_connected = connected
                    frame = await anext(stream)
                    self.assertTrue(frame.startswith('event: health\n'))
                    payload = json.loads(frame.split('data: ', 1)[1])
                    self.assertEqual(payload, {'databaseLive': connected})
            finally:
                await stream.aclose()
            self.assertFalse(hub.subscribers)


class BookingLiveUpdateTests(unittest.TestCase):
    def test_booking_invalidations_are_private_and_scoped(self):
        hub = LiveHub()
        guest = Subscriber("booking", booking_id="booking-1")
        other_guest = Subscriber("booking", booking_id="booking-2")
        public = Subscriber("public")
        staff = Subscriber("staff", account_id="staff-1")
        admin = Subscriber("admin", account_id="admin-1")
        hub.subscribers.update({guest, other_guest, public, staff, admin})

        hub._publish(
            {"bookings", "payments", "availability"},
            booking_ids={"booking-1"},
        )

        self.assertEqual(
            guest.queue.get_nowait()["domains"],
            ["bookings", "payments"],
        )
        self.assertTrue(other_guest.queue.empty())
        self.assertEqual(public.queue.get_nowait()["domains"], ["availability"])
        self.assertTrue(staff.queue.empty())
        self.assertEqual(
            admin.queue.get_nowait()["domains"],
            ["availability", "bookings", "payments"],
        )

    def test_booking_and_payment_routes_emit_live_invalidations(self):
        self.assertEqual(
            mutation_tables("/public-bookings/booking-1/sync-payment"),
            ["bookings", "booking_payments"],
        )
        self.assertEqual(
            mutation_tables("/admin/manual-bookings/booking-1/sync-payment"),
            ["bookings", "booking_payments"],
        )

    def test_payment_table_change_is_scoped_to_its_booking(self):
        with patch("live_updates.hub.publish") as publish:
            emit_table("booking_payments", {"booking_id": "booking-1"})

        self.assertEqual(publish.call_args.args[3], {"booking-1"})

    def test_task_updates_still_reach_only_the_assigned_staff(self):
        hub = LiveHub()
        assigned = Subscriber("staff", account_id="staff-1")
        other = Subscriber("staff", account_id="staff-2")
        hub.subscribers.update({assigned, other})

        hub._publish({"tasks", "notifications"}, staff_ids={"staff-1"})

        self.assertEqual(
            assigned.queue.get_nowait()["domains"],
            ["notifications", "tasks"],
        )
        self.assertTrue(other.queue.empty())

    def test_reassignment_refreshes_both_staff_workspaces(self):
        hub = LiveHub()
        old = Subscriber('staff', account_id='old')
        new = Subscriber('staff', account_id='new')
        unrelated = Subscriber('staff', account_id='other')
        hub.subscribers.update({old, new, unrelated})
        with patch('live_updates.hub.publish', side_effect=hub._publish):
            emit_table('admin_tasks', {'assigned_staff_id': 'new'}, {'assigned_staff_id': 'old'})
        self.assertEqual(old.queue.get_nowait()['domains'], ['tasks'])
        self.assertEqual(new.queue.get_nowait()['domains'], ['tasks'])
        self.assertTrue(unrelated.queue.empty())

    def test_notification_event_only_reaches_its_recipient(self):
        hub = LiveHub()
        recipient = Subscriber('staff', account_id='recipient')
        unrelated = Subscriber('staff', account_id='other')
        hub.subscribers.update({recipient, unrelated})
        with patch('live_updates.hub.publish', side_effect=hub._publish):
            emit_table('admin_notifications', {'recipient_staff_account_id': 'recipient'})
        self.assertEqual(recipient.queue.get_nowait()['domains'], ['notifications'])
        self.assertTrue(unrelated.queue.empty())


if __name__ == "__main__":
    unittest.main()


class RealtimeCertificateTests(unittest.TestCase):
    def test_default_bundle_loads_trusted_roots_with_verification_enabled(self):
        import os
        import ssl
        import certifi
        from live_updates import configure_realtime_certificates
        with patch.dict(os.environ, {}, clear=True):
            configure_realtime_certificates()
            self.assertEqual(os.environ['SSL_CERT_FILE'], certifi.where())
            context = ssl.create_default_context()
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertGreater(context.cert_store_stats()['x509_ca'], 0)

    def test_custom_ca_bundle_is_preserved(self):
        import os
        from live_updates import configure_realtime_certificates
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/custom/company-ca.pem'}):
            configure_realtime_certificates()
            self.assertEqual(os.environ['SSL_CERT_FILE'], '/custom/company-ca.pem')
