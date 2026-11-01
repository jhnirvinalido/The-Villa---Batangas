import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
import staff_admin_auth as auth


class FrontDeskAccountTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)
        self.account = {"id": "account-1", "auth_user_id": "auth-1", "email": "desk@example.com", "full_name": "Front Desk User", "role": "front_desk", "is_active": True}
        self.payload = {"access_token": "test-access-token", "refresh_token": "test-refresh-token-long-enough"}

    def login(self, path, role):
        account = {**self.account, "role": role}
        with (
            patch.object(auth, "_password_login", return_value=self.payload),
            patch.object(auth, "get_supabase_user", return_value={"id": "auth-1", "email": account["email"]}),
            patch.object(auth, "_read_staff_account", return_value=account),
            patch.object(auth, "_service_client", return_value=MagicMock()),
        ):
            return self.client.post(path, json={"email": account["email"], "password": "test-password-only"})

    def test_shared_login_accepts_all_four_account_roles(self):
        for role in ("admin", "front_desk", "staff", "maintenance"):
            with self.subTest(role=role):
                response = self.login("/staff-auth/login", role)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["user"]["role"], role)

    def test_old_front_desk_login_is_only_a_compatibility_alias(self):
        for role in ("admin", "front_desk", "staff", "maintenance"):
            with self.subTest(role=role):
                self.assertEqual(self.login("/staff-auth/front-desk/login", role).status_code, 200)

    def test_unknown_account_roles_are_rejected(self):
        response = self.login("/staff-auth/login", "customer")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("access_token", response.json())

    def test_shared_refresh_rechecks_each_account_role(self):
        for role, expected in (("front_desk", 200), ("admin", 200), ("staff", 200), ("maintenance", 200), ("customer", 403)):
            with (
                self.subTest(role=role),
                patch.object(auth, "_refresh_login", return_value=self.payload),
                patch.object(auth, "get_supabase_user", return_value={"id": "auth-1", "email": self.account["email"]}),
                patch.object(auth, "_read_staff_account", return_value={**self.account, "role": role}),
            ):
                response = self.client.post("/staff-auth/refresh", json={"refresh_token": self.payload["refresh_token"]})
                self.assertEqual(response.status_code, expected)

    def test_maintenance_can_use_its_work_api_without_getting_front_desk_access(self):
        import staff
        for role, allowed in (("maintenance", True), ("staff", True), ("admin", False), ("front_desk", False)):
            with (
                self.subTest(role=role),
                patch("staff.bearer_token", return_value="token"),
                patch("staff.validate_portal_access_token", return_value={**self.account, "role": role}),
            ):
                if allowed:
                    self.assertEqual(staff.require_staff(object())["account"]["role"], role)
                else:
                    with self.assertRaises(HTTPException) as raised:
                        staff.require_staff(object())
                    self.assertEqual(raised.exception.status_code, 403)

    def test_native_and_existing_maintenance_accounts_are_eligible_for_maintenance_work(self):
        import maintenance
        for role in ("maintenance", "staff"):
            person = {**self.account, "role": role, "department": "Maintenance", "account_status": "Active", "personal_email": "person@example.com"}
            with self.subTest(role=role), patch("maintenance.fetch_staff", return_value=person):
                self.assertEqual(maintenance.technician(person["id"])["id"], person["id"])
