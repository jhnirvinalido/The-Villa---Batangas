import ast
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class RenderCheckoutTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / "booking.py").read_text())
        names = {"_public_checkout_urls", "_send_email_message"}
        module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        self.env = {"os": os, "FRONTEND_URL": "http://localhost:5173",
                    "BACKEND_PUBLIC_URL": "", "EmailMessage": object,
                    "SMTP_PORT": 587, "smtplib": Mock()}
        exec(compile(ast.fix_missing_locations(module), "booking.py", "exec"), self.env)

    @patch.dict(os.environ, {"FRONTEND_DIST": "/app/frontend/dist", "RENDER_EXTERNAL_URL": "https://villa.onrender.com"}, clear=True)
    def test_combined_render_checkout_does_not_return_to_localhost(self):
        success, cancel = self.env["_public_checkout_urls"]("booking-id")
        self.assertEqual(success, "https://villa.onrender.com/book?payment=success&booking=booking-id")
        self.assertIn("payment=cancelled", cancel)

    @patch.dict(os.environ, {}, clear=True)
    def test_local_development_keeps_configured_frontend(self):
        self.assertTrue(self.env["_public_checkout_urls"]("id")[0].startswith("http://localhost:5173/book?"))

    @patch.dict(os.environ, {"RENDER": "true"}, clear=True)
    def test_render_smtp_fails_before_opening_blocked_connection(self):
        with self.assertRaisesRegex(RuntimeError, "RESEND_API_KEY"):
            self.env["_send_email_message"](object())
        self.env["smtplib"].SMTP.assert_not_called()
