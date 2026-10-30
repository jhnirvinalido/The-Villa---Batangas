import ast
import hashlib
import hmac
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from test_manual_checkout import HTTPError


class PublicEmailVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parents[1] / "booking.py"
        tree = ast.parse(source.read_text())
        function_names = {
            "_public_email_verification_hash",
            "_create_public_email_verification_token",
            "_valid_public_email_verification_token",
            "_require_verified_public_email",
        }
        nodes = [
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name in function_names
        ]
        cls.env = {
            "HTTPException": HTTPError,
            "datetime": datetime,
            "timezone": timezone,
            "hashlib": hashlib,
            "hmac": hmac,
            "secrets": secrets,
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "_first": lambda result: next(iter(result.data or []), None),
        }
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                *nodes,
            ],
            type_ignores=[],
        )
        exec(
            compile(ast.fix_missing_locations(module), str(source), "exec"),
            cls.env,
        )

    def setUp(self):
        self.service = MagicMock()
        self.query = self.service.table.return_value.select.return_value
        self.query.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        self.token = self.env["_create_public_email_verification_token"](
            "guest@example.com",
            datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    def test_requires_an_existing_verified_record(self):
        with self.assertRaises(HTTPError) as raised:
            self.env["_require_verified_public_email"](
                self.service, " Guest@Example.com ", self.token
            )
        self.assertEqual(raised.exception.status_code, 403)
        self.query.eq.assert_called_once_with(
            "email_hash",
            self.env["_public_email_verification_hash"]("guest@example.com", "email"),
        )

    def test_rejects_an_expired_verification(self):
        self.query.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            }]
        )
        with self.assertRaises(HTTPError) as raised:
            self.env["_require_verified_public_email"](
                self.service, "guest@example.com", self.token
            )
        self.assertEqual(raised.exception.status_code, 410)

    def test_accepts_a_verified_unexpired_email(self):
        self.query.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            }]
        )
        self.env["_require_verified_public_email"](
            self.service, "guest@example.com", self.token
        )

    def test_verification_token_is_bound_to_email_and_expiry(self):
        valid = self.env["_valid_public_email_verification_token"]
        now = datetime.now(timezone.utc)
        self.assertTrue(valid("guest@example.com", self.token, now))
        self.assertFalse(valid("other@example.com", self.token, now))
        self.assertFalse(valid("guest@example.com", "forged-token", now))


if __name__ == "__main__":
    unittest.main()
