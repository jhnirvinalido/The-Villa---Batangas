import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
import admin
import staff


class FrontDeskPortalTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin.router)
        app.include_router(staff.router)
        self.client = TestClient(app)

    def test_front_desk_loads_its_own_api_without_admin_role(self):
        account = {"id": "front-desk-1", "role": "front_desk"}
        with (
            patch("admin.validate_portal_access_token", return_value=account),
            patch("admin.save_session", return_value={}),
            patch("admin.bootstrap", return_value={"data": {
                "profile": {"id": account["id"], "portalRole": "front_desk"},
                "staff": [{"id": "cleaner", "name": "Ana", "authUserId": "private"}],
                "bookings": [{"id": "incoming"}], "tasks": [],
            }}),
        ):
            response = self.client.get("/front-desk/bootstrap", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["profile"]["portalRole"], "front_desk")
        self.assertEqual(data["bookings"][0]["id"], "incoming")
        self.assertNotIn("authUserId", data["staff"][0])

    def test_front_desk_can_update_only_its_own_profile(self):
        account = {"id": "front-desk-1", "role": "front_desk"}
        saved = {
            "id": account["id"],
            "full_name": "Updated Desk Name",
            "personal_email": "desk@example.com",
            "nickname": "Host",
            "avatar_url": None,
            "role": "front_desk",
            "position": "Front Desk",
        }
        client = MagicMock()
        query = client.table.return_value.update.return_value
        query.eq.return_value.select.return_value.execute.return_value = SimpleNamespace(data=[saved])
        with (
            patch("admin.validate_portal_access_token", return_value=account),
            patch("admin.save_session", return_value={}),
            patch("admin.service_client", return_value=client),
        ):
            response = self.client.patch(
                "/front-desk/profile",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "fullName": "Updated Desk Name",
                    "personalEmail": "DESK@example.com",
                    "nickname": "Host",
                    "avatarUrl": "",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Updated Desk Name")
        query.eq.assert_called_once_with("id", account["id"])
        updates = client.table.return_value.update.call_args.args[0]
        self.assertEqual(updates["updated_by_staff_id"], account["id"])
        self.assertEqual(updates["personal_email"], "desk@example.com")
        self.assertNotIn("role", updates)

    def test_non_front_desk_role_cannot_update_front_desk_profile(self):
        with patch("admin.validate_portal_access_token", return_value={"id": "staff-1", "role": "staff"}):
            response = self.client.patch(
                "/front-desk/profile",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "fullName": "Staff Name",
                    "personalEmail": "staff@example.com",
                    "nickname": "",
                    "avatarUrl": "",
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_open_the_front_desk_api_even_with_legacy_grants(self):
        with patch("admin.validate_portal_access_token", return_value={"id": "staff-1", "role": "staff", "can_create_walk_in_bookings": True, "can_process_front_desk_payments": True}):
            response = self.client.get("/front-desk/bootstrap", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

    def test_guest_operations_are_removed_from_staff_routes(self):
        for method, path in [("GET", "/staff/guest-services/bookings"), ("GET", "/staff/guest-services/availability"), ("POST", "/staff/guest-services/walk-ins"), ("POST", "/staff/guest-services/bookings/00000000-0000-0000-0000-000000000001/check-in")]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path).status_code, 404)

    def test_admin_account_cannot_substitute_for_a_front_desk_account(self):
        with (
            patch("admin.validate_portal_access_token", return_value={"id": "admin-1", "role": "admin"}),
            patch("admin.save_session", return_value={}),
            patch("admin.bootstrap") as bootstrap,
        ):
            response = self.client.get("/front-desk/bootstrap", headers={"Authorization": "Bearer admin-token"})
        self.assertEqual(response.status_code, 403)
        bootstrap.assert_not_called()

    def test_payment_webhook_still_uses_provider_verification_without_a_portal_account(self):
        with patch("admin.verify_paymongo_signature") as verify:
            response = self.client.post("/front-desk/paymongo/webhook", json={"data": {"attributes": {"type": "ignored.event"}}})
        verify.assert_called_once()
        self.assertEqual(response.status_code, 200)

    def test_all_front_desk_actions_require_a_front_desk_session(self):
        paths = [
            ("GET", "/front-desk/bootstrap"), ("GET", "/front-desk/availability"),
            ("POST", "/front-desk/walk-ins"),
            ("POST", "/front-desk/bookings/00000000-0000-0000-0000-000000000001/check-in"),
            ("POST", "/front-desk/bookings/00000000-0000-0000-0000-000000000001/checkout"),
            ("POST", "/front-desk/bookings/00000000-0000-0000-0000-000000000001/cash-settlement"),
        ]
        for method, path in paths:
            with self.subTest(path=path):
                response = self.client.request(method, path)
                self.assertEqual(response.status_code, 401)

    def test_walk_in_availability_uses_the_same_calendar_source_as_admin_manual_bookings(self):
        with (
            patch("admin.validate_portal_access_token", return_value={"id": "front-desk-1", "role": "front_desk"}),
            patch("admin.save_session", return_value={}),
            patch("booking.public_booking_availability", return_value={"villas": [], "updated_at": "2026-11-01T10:00:00Z"}) as availability,
        ):
            manual_booking = admin.manual_booking_availability(
                check_in_date=date(2026, 11, 2),
                context={},
            )
            response = self.client.get(
                "/front-desk/availability?check_in_date=2026-11-02&guest_count=3",
                headers={"Authorization": "Bearer test-token"},
            )

        self.assertEqual(manual_booking["updated_at"], "2026-11-01T10:00:00Z")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_at"], "2026-11-01T10:00:00Z")
        availability.assert_has_calls(
            [
                call(check_in_date=date(2026, 11, 2), guest_count=1),
                call(check_in_date=date(2026, 11, 2), guest_count=3),
            ]
        )
