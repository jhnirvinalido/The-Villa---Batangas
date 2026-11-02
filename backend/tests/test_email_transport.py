import os
import unittest
from email.message import EmailMessage
from unittest.mock import Mock, patch

import booking
from email_transport import EmailProviderError, send_resend


class EmailTransportTests(unittest.TestCase):
    @patch.dict(os.environ, {"RESEND_API_KEY": "test-only", "RESEND_FROM": "Villa <bookings@example.com>"})
    @patch("email_transport.requests.post")
    def test_inline_logo_and_both_bodies_are_preserved(self, post):
        post.return_value = Mock(ok=True, json=lambda: {"id": "email-1"})
        message = EmailMessage()
        message["To"] = "guest@example.com"
        message["Subject"] = "Reservation"
        message["Message-ID"] = "<feedback-booking@example.com>"
        message.set_content("Booking confirmed")
        message.add_alternative('<img src="cid:logo">', subtype="html")
        message.get_payload()[-1].add_related(b"image", maintype="image", subtype="png", cid="<logo>", filename="logo.png")
        accepted = Mock()
        self.assertEqual(send_resend(message, on_accepted=accepted), {})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], ["guest@example.com"])
        self.assertEqual(payload["headers"]["Message-ID"], "<feedback-booking@example.com>")
        self.assertIn("Booking confirmed", payload["text"])
        self.assertEqual(payload["attachments"][0]["content_id"], "logo")
        accepted.assert_called_once_with({})

    @patch.dict(os.environ, {"RESEND_API_KEY": "test-only", "RESEND_FROM": "bookings@example.com"})
    @patch("email_transport.requests.post")
    def test_rejected_email_is_not_reported_as_accepted(self, post):
        post.return_value = Mock(ok=False, status_code=403)
        accepted = Mock()
        message = EmailMessage()
        message["To"] = "guest@example.com"
        message.set_content("Test")
        with self.assertRaisesRegex(EmailProviderError, "HTTP 403") as raised:
            send_resend(message, on_accepted=accepted)
        self.assertEqual(raised.exception.status_code, 403)
        accepted.assert_not_called()

    @patch.dict(os.environ, {"RESEND_API_KEY": "test-only", "RESEND_FROM": "bookings@example.com"})
    @patch("email_transport.requests.post")
    def test_invalid_provider_response_is_not_reported_as_accepted(self, post):
        post.return_value = Mock(ok=True, status_code=200, json=lambda: {})
        message = EmailMessage()
        message["To"] = "guest@example.com"
        message.set_content("Test")
        with self.assertRaises(EmailProviderError):
            send_resend(message)

    @patch.dict(os.environ, {"RESEND_API_KEY": "test-only", "RESEND_FROM": "bookings@example.com"})
    @patch("email_transport.requests.post")
    @patch("booking.smtplib.SMTP")
    def test_resend_is_used_even_when_caller_supplies_smtp_settings(self, smtp, post):
        post.return_value = Mock(ok=True, json=lambda: {"id": "email-2"})
        message = EmailMessage()
        message["To"] = "staff@example.com"
        message["Subject"] = "Assignment"
        message.set_content("Review your assignment")

        booking._send_email_message(
            message,
            host="smtp.example.com",
            port=587,
            username="smtp-user",
            password="smtp-password",
        )

        post.assert_called_once()
        smtp.assert_not_called()
        self.assertEqual(post.call_args.kwargs["json"]["from"], "bookings@example.com")
