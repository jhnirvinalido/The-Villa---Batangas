import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class PublicEmailDeliveryConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parents[1] / "booking.py"
        tree = ast.parse(source.read_text())
        names = {"_smtp_configured", "_public_email_delivery_setup_error"}
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
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
        cls.env = {
            "os": os,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "guest",
            "SMTP_PASSWORD": "password",
            "SMTP_FROM": "bookings@example.com",
        }
        exec(
            compile(ast.fix_missing_locations(module), str(source), "exec"),
            cls.env,
        )

    @patch.dict(os.environ, {"RENDER": "true"}, clear=True)
    def test_render_blocked_smtp_has_actionable_configuration_error(self):
        self.assertIn(
            "hosting setup",
            self.env["_public_email_delivery_setup_error"](),
        )

    @patch.dict(
        os.environ,
        {"RENDER": "true", "RESEND_API_KEY": "test-only", "RESEND_FROM": "verified@example.com"},
        clear=True,
    )
    def test_configured_resend_is_available_on_render(self):
        self.assertIsNone(self.env["_public_email_delivery_setup_error"]())

    @patch.dict(
        os.environ,
        {"RENDER": "true", "RESEND_API_KEY": "test-only"},
        clear=True,
    )
    def test_missing_resend_sender_is_reported(self):
        self.assertIn(
            "verified sender",
            self.env["_public_email_delivery_setup_error"](),
        )


if __name__ == "__main__":
    unittest.main()
