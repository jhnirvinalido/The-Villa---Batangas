from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode
from uuid import UUID
from fastapi.responses import HTMLResponse, JSONResponse

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from person_names import validate_person_name
from villa_catalog import get_villa_catalog_map
from booking_assignments import schedule_prearrival_assignment as _assign_prearrival_staff

if TYPE_CHECKING:
    from supabase import Client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY", ""
).strip()
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")
PAYMONGO_SECRET_KEY = os.getenv(
    "PAYMONGO_SECRET_KEY", ""
).strip()
PAYMONGO_WEBHOOK_SECRET = os.getenv(
    "PAYMONGO_WEBHOOK_SECRET", ""
).strip()

# Booking confirmation email settings.
# Configure these in backend/.env. The booking itself is not rolled back
# if email delivery fails, so a temporary SMTP problem will not lose a
# customer's reservation.
SMTP_HOST = os.getenv(
    "SMTP_HOST",
    "smtp.gmail.com",
).strip()
SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "587",
    ).strip()
    or "587"
)
SMTP_USER = os.getenv(
    "SMTP_USER",
    "",
).strip()
SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD",
    "",
).strip()
SMTP_FROM = os.getenv(
    "SMTP_FROM",
    "",
).strip()
SMTP_FROM_NAME = os.getenv(
    "SMTP_FROM_NAME",
    "The Villa",
).strip()

PAYMONGO_CREATE_CHECKOUT_URL = (
    "https://api.paymongo.com/v2/checkout_sessions"
)
PAYMONGO_RETRIEVE_CHECKOUT_URL = (
    "https://api.paymongo.com/v1/checkout_sessions"
)

# Set to a publicly reachable HTTPS API URL in production, e.g. https://api.example.com
# When unset, admin requests use their FastAPI request origin for checkout callbacks.
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")


logger = logging.getLogger("thevilla.booking")


def _smtp_configured() -> bool:
    """Return True when the required SMTP credentials are configured."""
    if os.getenv("RESEND_API_KEY", "").strip():
        return bool(os.getenv("RESEND_FROM", "").strip())
    return bool(
        SMTP_HOST
        and SMTP_PORT
        and SMTP_USER
        and SMTP_PASSWORD
        and SMTP_FROM
    )


def _send_email_message(
    message: EmailMessage,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    on_sending=None,
    on_accepted=None,
):
    """Use HTTPS email when configured; retain SMTP for local/existing hosts."""
    if os.getenv("RESEND_API_KEY", "").strip() and not any((host, port, username, password)):
        from email_transport import send_resend
        return send_resend(message, on_sending=on_sending, on_accepted=on_accepted)
    if os.getenv("RENDER", "").lower() == "true" and (port or SMTP_PORT) in {25, 465, 587} and os.getenv("RENDER_SERVICE_TYPE", "web") == "web" and os.getenv("SMTP_ALLOW_ON_RENDER", "false").lower() != "true":
        raise RuntimeError("SMTP is disabled on this Render deployment. Configure RESEND_API_KEY and RESEND_FROM, or enable SMTP_ALLOW_ON_RENDER only on a paid service that supports SMTP.")
    with smtplib.SMTP(host or SMTP_HOST, port or SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(username or SMTP_USER, password or SMTP_PASSWORD)
        if on_sending:
            on_sending()
        refused = smtp.send_message(message)
        if on_accepted:
            on_accepted(refused)
        return refused


def _format_email_date(value: Any) -> str:
    """Format a booking date for a guest-facing email."""
    if not value:
        return "Not specified"

    try:
        if isinstance(value, datetime):
            return value.strftime("%B %d, %Y")
        if isinstance(value, date):
            return value.strftime("%B %d, %Y")
        return datetime.strptime(
            str(value)[:10],
            "%Y-%m-%d",
        ).strftime("%B %d, %Y")
    except Exception:
        return str(value)


def _money_text(value: Any) -> str:
    return f"PHP {_money(value):,.2f}"


def _booking_email_logo() -> tuple[str, bytes | None]:
    """Find the real favicon.png for reliable inline display in Gmail.

    Gmail cannot load localhost images, so attach the project's favicon.png
    inside the email. EMAIL_LOGO_PATH can override the automatic lookup.
    An HTTPS URL is used only if a local PNG cannot be found.
    """
    configured = os.getenv("EMAIL_LOGO_PATH", "").strip()
    backend_dir = Path(__file__).resolve().parent
    candidates = ([Path(configured).expanduser()] if configured else []) + [
        backend_dir.parent / "frontend" / "public" / "favicon.png",
        backend_dir / "frontend" / "public" / "favicon.png",
        backend_dir / "public" / "favicon.png",
        backend_dir / "static" / "favicon.png",
        backend_dir / "favicon.png",
    ]

    for candidate in candidates:
        try:
            if candidate.is_file():
                data = candidate.read_bytes()
                if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= 2_000_000:
                    return "cid:thevilla-booking-logo", data
                logger.warning("Email logo is not a valid PNG or is too large: %s", candidate)
        except OSError:
            logger.warning("Unable to read email logo at %s", candidate, exc_info=True)

    # External fallback must be publicly accessible: http://localhost is not.
    image_url = os.getenv("EMAIL_LOGO_URL", "").strip() or f"{FRONTEND_URL}/favicon.png"
    if image_url.startswith("https://"):
        return image_url, None

    logger.warning(
        "Email favicon.png was not found. Place it in frontend/public/favicon.png "
        "or set EMAIL_LOGO_PATH in backend/.env."
    )
    return "", None


def _public_email_verification_hash(email: str, purpose: str) -> str:
    normalized = str(email).strip().lower()
    message = f"public-email-verification:{purpose}:{normalized}".encode()
    return hmac.new(
        SUPABASE_SERVICE_ROLE_KEY.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def _create_public_email_verification_token(email: str, expires_at: datetime) -> str:
    email_hash = _public_email_verification_hash(email, "email")
    expiry = int(expires_at.timestamp())
    nonce = secrets.token_urlsafe(24)
    payload = f"{email_hash}:{expiry}:{nonce}"
    signature = hmac.new(
        SUPABASE_SERVICE_ROLE_KEY.encode(),
        f"public-email-verification:booking-token:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def _valid_public_email_verification_token(
    email: str,
    token: str,
    now: datetime,
) -> bool:
    try:
        email_hash, expiry_text, nonce, signature = str(token).split(":")
        expiry = int(expiry_text)
    except (TypeError, ValueError):
        return False

    if not nonce or expiry <= int(now.timestamp()):
        return False
    expected_email_hash = _public_email_verification_hash(email, "email")
    if not hmac.compare_digest(email_hash, expected_email_hash):
        return False
    payload = f"{email_hash}:{expiry}:{nonce}"
    expected_signature = hmac.new(
        SUPABASE_SERVICE_ROLE_KEY.encode(),
        f"public-email-verification:booking-token:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def _require_verified_public_email(
    service,
    email: str,
    verification_token: str,
) -> None:
    normalized = str(email).strip().lower()
    if not _valid_public_email_verification_token(
        normalized,
        verification_token,
        datetime.now(timezone.utc),
    ):
        raise HTTPException(
            status_code=403,
            detail="Verify your email address before creating a booking.",
        )
    record = _first(
        service.table("public_email_verifications")
        .select("verified_at,expires_at")
        .eq("email_hash", _public_email_verification_hash(normalized, "email"))
        .limit(1)
        .execute()
    )
    if not record or not record.get("verified_at"):
        raise HTTPException(
            status_code=403,
            detail="Verify your email address before creating a booking.",
        )
    expires_at = datetime.fromisoformat(
        str(record["expires_at"]).replace("Z", "+00:00")
    )
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=410,
            detail="Your email verification expired. Verify your email again.",
        )


def _send_booking_confirmation_email(
    booking: dict[str, Any],
    feedback_token: str | None = None,
) -> bool:
    """Send the guest-facing booking acknowledgement (not a paid receipt).

    Keep feedback_token for compatibility with the existing caller, but do
    not include any feedback requests in the guest's booking email.
    """
    recipient = str(booking.get("customer_email") or "").strip()
    if not recipient:
        logger.warning(
            "Booking %s has no customer email. Confirmation email skipped.",
            booking.get("booking_code") or booking.get("id"),
        )
        return False

    if not _smtp_configured():
        logger.warning(
            "SMTP is not configured. Booking confirmation email skipped for booking %s.",
            booking.get("booking_code") or booking.get("id"),
        )
        return False

    booking_code = str(booking.get("booking_code") or booking.get("id") or "Reservation")
    guest_name = str(booking.get("customer_name") or "Guest").strip()
    villa_name = str(booking.get("villa_name") or "Selected villa").strip()
    check_in = _format_email_date(booking.get("check_in_date"))
    check_out = _format_email_date(booking.get("check_out_date"))
    check_in_time = str(booking.get("check_in_time") or "3:00 PM")
    guest_count = booking.get("guest_count", "Not specified")
    payment_choice = str(booking.get("payment_choice") or "half").strip().lower()
    payment_label = "Full payment" if payment_choice == "full" else "50% downpayment"
    payment_method = str(booking.get("payment_method") or "Not selected")
    total_amount = _money_text(booking.get("total_amount"))
    payment_due_amount = _money_text(booking.get("payment_due_amount"))
    booking_status = str(booking.get("booking_status") or "Pending Payment")

    safe_guest = escape(guest_name)
    safe_code = escape(booking_code)
    safe_villa = escape(villa_name)
    safe_check_in = escape(check_in)
    safe_check_out = escape(check_out)
    safe_check_in_time = escape(check_in_time)
    safe_guest_count = escape(str(guest_count))
    safe_payment_label = escape(payment_label)
    safe_payment_method = escape(payment_method)
    safe_total = escape(total_amount)
    safe_due = escape(payment_due_amount)
    safe_status = escape(booking_status)

    logo_src, logo_bytes = _booking_email_logo()
    logo_cell = (
        '<td width="60" style="width:60px;vertical-align:middle;padding:0 14px 0 0;">'
        f'<img src="{escape(logo_src, quote=True)}" alt="The Villa" width="48" height="48" '
        'style="display:block;width:48px;height:48px;border-radius:10px;object-fit:contain;border:1px solid #eee8e3;">'
        '</td>'
        if logo_src else ""
    )

    subject = f"Booking received | {booking_code} | The Villa"

    plain_text = f"""Hello {guest_name},

Thank you for choosing The Villa! We have received your reservation details.

Booking reference: {booking_code}
Villa: {villa_name}
Check-in: {check_in}, {check_in_time}
Check-out: {check_out}
Guests: {guest_count}

Payment option: {payment_label}
Payment method: {payment_method}
Total: {total_amount}
Initial payment due: {payment_due_amount}
Booking status: {booking_status}

We look forward to welcoming you to The Villa! Please keep your booking reference handy and complete the selected payment to secure your stay.

If you have any questions or special requests before your visit, feel free to contact our team.

Warm regards,
The Villa Team
"""

    html_body = f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"></head>
  <body style="margin:0;padding:0;background:#f6f3f0;font-family:Arial,Helvetica,sans-serif;color:#24201d;">
    <div style="max-width:640px;margin:32px auto;background:#ffffff;border:1px solid #e5e0dc;border-radius:14px;overflow:hidden;">
      <div style="padding:24px 32px;border-bottom:1px solid #eee8e3;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;">
          <tr>
            {logo_cell}
            <td style="vertical-align:middle;">
              <div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#7a563f;font-weight:700;">The Villa</div>
              <h1 style="margin:5px 0 3px;font-size:25px;line-height:1.25;color:#24201d;">Booking received</h1>
              <p style="margin:0;color:#6b7280;font-size:14px;line-height:1.5;">Your reservation details have been saved successfully.</p>
            </td>
          </tr>
        </table>
      </div>

      <div style="padding:28px 32px;">
        <p style="margin:0 0 18px;font-size:15px;">Hello {safe_guest},</p>
        <p style="margin:0 0 18px;font-size:14px;line-height:1.6;">Thank you for choosing The Villa! We have received your reservation details.</p>

        <div style="padding:16px 18px;background:#faf7f4;border:1px solid #e7ddd5;border-radius:10px;margin-bottom:22px;">
          <div style="font-size:11px;color:#7a563f;text-transform:uppercase;letter-spacing:.08em;font-weight:700;">Booking reference</div>
          <div style="margin-top:5px;font-size:21px;font-weight:700;color:#5f402e;">{safe_code}</div>
        </div>

        <table role="presentation" style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr><td style="padding:9px 0;color:#6b7280;">Villa</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_villa}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Check-in</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_check_in}, {safe_check_in_time}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Check-out</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_check_out}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Guests</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_guest_count}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Payment option</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_payment_label}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Payment method</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_payment_method}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Total</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_total}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Initial payment due</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_due}</td></tr>
          <tr><td style="padding:9px 0;color:#6b7280;">Status</td><td style="padding:9px 0;text-align:right;font-weight:600;">{safe_status}</td></tr>
        </table>

        <div style="margin-top:22px;padding:16px 18px;background:#edf8f1;border:1px solid #d8ebde;border-radius:10px;color:#285e40;font-size:13px;line-height:1.65;">
          <strong style="display:block;margin-bottom:5px;font-size:14px;">We look forward to welcoming you!</strong>
          Thank you for choosing The Villa. Please keep your booking reference handy and complete your selected payment to secure your stay. We look forward to making your visit comfortable and memorable.
        </div>

        <p style="margin:20px 0 0;color:#6b7280;font-size:13px;line-height:1.65;">
          If you have questions or special requests before your visit, feel free to contact our team.
        </p>
        <p style="margin:18px 0 0;color:#584d44;font-size:13px;line-height:1.6;">Warm regards,<br><strong>The Villa Team</strong></p>
      </div>

      <div style="padding:18px 32px;background:#fafafa;border-top:1px solid #eee8e3;color:#777;font-size:12px;">
        The Villa &middot; We look forward to your stay.
      </div>
    </div>
  </body>
</html>
"""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>" if SMTP_FROM_NAME else SMTP_FROM
    message["To"] = recipient
    message.set_content(plain_text)
    message.add_alternative(html_body, subtype="html")

    if logo_bytes:
        # Use Content-ID rather than a localhost URL. Gmail can show this even
        # when The Villa frontend runs only on the developer's computer.
        html_part = message.get_payload()[-1]
        html_part.add_related(
            logo_bytes,
            maintype="image",
            subtype="png",
            cid="<thevilla-booking-logo>",
            filename="favicon.png",
            disposition="inline",
        )

    try:
        _send_email_message(message)
        logger.info("Booking confirmation email provider acceptance recorded.")
        return True
    except Exception:
        logger.exception("Booking confirmation email could not be sent. Booking=%s", booking_code)
        return False


router = APIRouter(
    prefix="/bookings",
    tags=["Bookings"],
)

# Public booking endpoints used by BookForm.jsx.
# The original /bookings routes remain unchanged for backward compatibility.
public_router = APIRouter(
    prefix="/public-bookings",
    tags=["Public Guest Booking"],
)

PAYMONGO_METHOD_DETAILS: dict[str, dict[str, Any]] = {
    "gcash": {
        "label": "GCash",
        "paymongo_type": "gcash",
        "flow_type": "wallet_redirect",
        "customer_steps": [
            "PayMongo opens the GCash authorization flow.",
            "The customer approves or cancels the payment.",
            "PayMongo returns the customer to The Villa.",
            "The webhook confirms payment before a receipt is released.",
        ],
        "test_instructions": (
            "PayMongo opens a sandbox authorization page. "
            "Choose Authorize or Fail; no real GCash account is required."
        ),
        "live_instructions": (
            "The customer is redirected to GCash and approves the payment "
            "using the normal GCash authorization flow."
        ),
    },
    "maya": {
        "label": "Maya",
        "paymongo_type": "paymaya",
        "flow_type": "wallet_redirect",
        "customer_steps": [
            "PayMongo opens the Maya authorization flow.",
            "The customer approves or cancels the payment.",
            "PayMongo returns the customer to The Villa.",
            "The webhook confirms payment before a receipt is released.",
        ],
        "test_instructions": (
            "PayMongo opens a sandbox authorization page. "
            "Choose Authorize or Fail; no real Maya account is required."
        ),
        "live_instructions": (
            "The customer is redirected to Maya and approves the payment "
            "using the normal Maya authorization flow."
        ),
    },
    "debit": {
        "label": "Credit or Debit Card",
        "paymongo_type": "card",
        "flow_type": "card",
        "customer_steps": [
            "The customer enters card details only on PayMongo.",
            "The issuing bank may request 3D Secure authentication.",
            "PayMongo returns the customer to The Villa.",
            "The webhook confirms payment before a receipt is released.",
        ],
        "test_instructions": (
            "Use a PayMongo test card. The Villa never receives or stores "
            "the card number, expiration date, or CVC."
        ),
        "live_instructions": (
            "Supported Visa or Mastercard credit and debit cards can be used. "
            "The issuing bank may require 3D Secure authentication."
        ),
    },
    "qrph": {
        "label": "QR Ph",
        "paymongo_type": "qrph",
        "flow_type": "qr",
        "customer_steps": [
            "PayMongo generates the QR Ph payment screen.",
            "The customer completes the QR payment flow.",
            "PayMongo returns the customer to The Villa.",
            "The webhook confirms payment before a receipt is released.",
        ],
        "test_instructions": (
            "Use PayMongo's test simulation controls. Do not scan a test QR "
            "with a real bank or wallet application."
        ),
        "live_instructions": (
            "The customer scans the QR using a QR Ph-compatible bank or "
            "wallet application and confirms the payment."
        ),
    },
}

PAYMONGO_METHOD_MAP = {
    method_id: [details["paymongo_type"]]
    for method_id, details in PAYMONGO_METHOD_DETAILS.items()
}

PAYMENT_METHOD_LABELS = {
    "gcash": "GCash",
    "paymaya": "Maya",
    "maya": "Maya",
    "card": "Credit or Debit Card",
    "debit": "Credit or Debit Card",
    "qrph": "QR Ph",
}

VILLA_CATALOG: dict[str, dict[str, Any]] = {
    "villa-1": {
        "name": "Villa 1",
        "price": Decimal("4500.00"),
        "capacity": 8,
        "image": "/family.jpg",
    },
    "villa-2": {
        "name": "Villa 2",
        "price": Decimal("5500.00"),
        "capacity": 8,
        "image": "/couple.jpg",
    },
    "villa-3": {
        "name": "Villa 3",
        "price": Decimal("6500.00"),
        "capacity": 8,
        "image": "/barkada.jpg",
        "operational_status": "under_maintenance",
    },
    "villa-4": {
        "name": "Villa 4",
        "price": Decimal("7500.00"),
        "capacity": 4,
        "image": "/image1.jpg",
    },
}

ALLOWED_CHECK_IN_TIMES = {
    "3:00 PM",
}

MAX_GUEST_COUNT = 32
PUBLIC_BOOKING_HOLD_MINUTES = 30
AVAILABILITY_RELEASE_STATUSES = {
    "cancelled",
    "completed",
    "checked out",
    "checked-out",
    "checked_out",
    "expired",
    "refunded",
}
NON_BLOCKING_CUSTOMER_STATUSES = {
    "cancelled",
    "expired",
    "refunded",
}
COMPLETED_STAY_STATUSES = {
    "completed",
    "checked out",
    "checked-out",
    "checked_out",
}


class BookingCreateRequest(BaseModel):
    villa_id: str = Field(min_length=1, max_length=50)
    check_in_date: date
    check_in_time: str = Field(min_length=1, max_length=20)
    guest_count: int = Field(ge=1, le=8)
    notes: str | None = Field(default=None, max_length=1000)
    payment_choice: Literal["half", "full"] = "half"
    payment_method: Literal[
        "gcash",
        "maya",
        "debit",
        "qrph",
    ] = "gcash"


class CheckoutRequest(BaseModel):
    payment_method: Literal[
        "gcash",
        "maya",
        "debit",
        "qrph",
    ] = "gcash"
    payment_scope: Literal[
        "selected",
        "balance",
    ] = "selected"


class PayMongoDiagnosticRequest(BaseModel):
    payment_method: Literal[
        "gcash",
        "maya",
        "debit",
        "qrph",
    ] = "gcash"


def _attr(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _client(key: str) -> Client:
    if not SUPABASE_URL or not key:
        raise HTTPException(
            status_code=500,
            detail="Supabase booking configuration is incomplete.",
        )
    from supabase import create_client

    return create_client(SUPABASE_URL, key)


TRANSIENT_CONNECTION_MARKERS = (
    "connectionterminated",
    "connection terminated",
    "last_stream_id",
    "remoteprotocolerror",
    "connection reset",
    "connection aborted",
    "server disconnected",
    "timed out",
    "timeout",
)


def _is_transient_error(
    error: Exception,
) -> bool:
    message = str(error).strip().lower()

    return any(
        marker in message
        for marker in TRANSIENT_CONNECTION_MARKERS
    )


def _auth_rest_request(
    method: str,
    endpoint: str,
    *,
    access_token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Call Supabase Auth through requests/HTTP 1.1.

    The previous implementation used supabase.auth.get_user
    for every booking request. A temporary HTTP/2 stream
    termination was then converted into a false 401.
    """

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    if access_token:
        headers["Authorization"] = (
            f"Bearer {access_token}"
        )

    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = requests.request(
                method=method,
                url=endpoint,
                headers=headers,
                json=payload,
                timeout=(5, 20),
            )

        except requests.RequestException as error:
            last_error = error

            if attempt < 2:
                time.sleep(
                    0.3 * (attempt + 1)
                )
                continue

            raise HTTPException(
                status_code=503,
                detail=(
                    "The Villa authentication "
                    "connection was interrupted. "
                    "Please try again."
                ),
            ) from error

        if response.status_code == 200:
            try:
                result = response.json()
            except ValueError as error:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "The authentication service "
                        "returned an unreadable response."
                    ),
                ) from error

            if not isinstance(result, dict):
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "The authentication service "
                        "returned an invalid response."
                    ),
                )

            return result

        if (
            response.status_code
            in {500, 502, 503, 504}
            and attempt < 2
        ):
            time.sleep(
                0.3 * (attempt + 1)
            )
            continue

        if response.status_code in {
            400,
            401,
            403,
        }:
            detail = (
                "Your login session has expired. "
                "Please log in again."
            )

            try:
                body = response.json()
                provider_message = str(
                    body.get(
                        "msg",
                        body.get(
                            "message",
                            "",
                        ),
                    )
                ).strip()

                if provider_message:
                    logger.info(
                        "Supabase rejected a booking token: %s",
                        provider_message,
                    )
            except ValueError:
                pass

            raise HTTPException(
                status_code=401,
                detail=detail,
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "The authentication service rejected "
                "the booking request."
            ),
        )

    raise HTTPException(
        status_code=503,
        detail=(
            "The Villa authentication connection "
            "was interrupted. Please try again."
        ),
    ) from last_error


def _get_auth_user(
    access_token: str,
) -> dict[str, Any]:
    return _auth_rest_request(
        "GET",
        f"{SUPABASE_URL}/auth/v1/user",
        access_token=access_token,
    )


def _refresh_auth_session(
    refresh_token: str,
) -> dict[str, Any]:
    return _auth_rest_request(
        "POST",
        (
            f"{SUPABASE_URL}/auth/v1/token"
            "?grant_type=refresh_token"
        ),
        payload={
            "refresh_token": refresh_token
        },
    )


def _auth(
    request: Request,
) -> tuple[Client, Any, str, str, str]:
    """
    Verify the current customer and refresh the session
    only when the access token has expired.

    Booking requests no longer call set_session() and
    get_user() through the same HTTP/2 client on every
    keystroke. This prevents transient stream shutdowns
    from appearing as false login errors.
    """

    authorization = request.headers.get(
        "Authorization",
        "",
    )

    refresh_token = request.headers.get(
        "X-Refresh-Token",
        "",
    ).strip()

    if not authorization.startswith(
        "Bearer "
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session is missing. "
                "Please log in again."
            ),
        )

    access_token = authorization[
        len("Bearer "):
    ].strip()

    if not access_token or not refresh_token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session is incomplete. "
                "Please log in again."
            ),
        )

    current_access = access_token
    current_refresh = refresh_token

    try:
        user = _get_auth_user(
            current_access
        )

    except HTTPException as error:
        if error.status_code != 401:
            raise

        refreshed = (
            _refresh_auth_session(
                current_refresh
            )
        )

        current_access = str(
            refreshed.get(
                "access_token",
                "",
            )
        ).strip()

        current_refresh = str(
            refreshed.get(
                "refresh_token",
                "",
            )
        ).strip()

        user = refreshed.get(
            "user"
        )

        if (
            not current_access
            or not current_refresh
            or not isinstance(
                user,
                dict,
            )
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Your refreshed login session "
                    "is incomplete. Please log in again."
                ),
            )

    user_id = str(
        _attr(
            user,
            "id",
            "",
        )
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session is no longer "
                "valid. Please log in again."
            ),
        )

    user_metadata = (
        _attr(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    if (
        user_metadata.get(
            "account_status"
        )
        == "pending_deletion"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "This account is pending deletion. "
                "Sign in again using the same account "
                "within 30 days to restore your data."
            ),
        )

    request.state.villa_access_token = (
        current_access
    )

    request.state.villa_refresh_token = (
        current_refresh
    )

    return (
        _service(),
        user,
        user_id,
        current_access,
        current_refresh,
    )



def _service() -> Client:
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "SUPABASE_SERVICE_ROLE_KEY is required "
                "for PayMongo webhooks."
            ),
        )
    from db_pool import service_client_for
    return service_client_for(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _display_name(user: Any) -> str:
    metadata = _attr(user, "user_metadata", {}) or {}
    first_name = str(
        metadata.get("profile_first_name")
        or metadata.get("first_name")
        or metadata.get("given_name")
        or ""
    ).strip()
    last_name = str(
        metadata.get("profile_last_name")
        or metadata.get("last_name")
        or metadata.get("family_name")
        or ""
    ).strip()
    combined = " ".join(
        part for part in [first_name, last_name] if part
    ).strip()
    return (
        combined
        or str(
            metadata.get("profile_full_name")
            or metadata.get("full_name")
            or metadata.get("name")
            or _attr(user, "email", "")
            or _attr(user, "phone", "")
            or "Villa Guest"
        ).strip()
    )


def _clean_text(
    value: Any,
) -> str | None:
    cleaned = str(
        value or ""
    ).strip()

    return cleaned or None


def _required_customer_phone(
    value: Any,
) -> str | None:
    """
    Return a Philippine mobile number in E.164 format.

    Booking is not allowed without a valid mobile number.
    Accepted examples include 09123456789, 9123456789,
    639123456789, and +639123456789.
    """

    digits = "".join(
        character
        for character in str(
            value or ""
        )
        if character.isdigit()
    )

    if (
        len(digits) == 10
        and digits.startswith("9")
    ):
        return f"+63{digits}"

    if (
        len(digits) == 11
        and digits.startswith("09")
    ):
        return f"+63{digits[1:]}"

    if (
        len(digits) == 12
        and digits.startswith("639")
    ):
        return f"+{digits}"

    return None


def _profile_contact_snapshot(
    supabase: Client,
    user: Any,
    user_id: str,
) -> dict[str, Any]:
    """
    Read reservation contact details from public.profiles.

    Auth data is only a fallback when the profile row has
    not been synchronized yet. The booking form never asks
    the customer to enter email or phone again.
    """

    profile: dict[str, Any] = {}

    try:
        response = (
            supabase.table("profiles")
            .select(
                (
                    "id,first_name,last_name,"
                    "full_name,email,phone"
                )
            )
            .eq("id", user_id)
            .limit(1)
            .execute()
        )

        rows = _attr(
            response,
            "data",
            [],
        ) or []

        if (
            isinstance(rows, list)
            and rows
            and isinstance(
                rows[0],
                dict,
            )
        ):
            profile = rows[0]

    except Exception as error:
        logger.warning(
            (
                "Could not load public.profiles "
                "for booking contact. User=%s"
            ),
            user_id,
        )

        if not _is_transient_error(
            error
        ):
            logger.debug(
                "Profile contact lookup error.",
                exc_info=True,
            )

    metadata = (
        _attr(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    profile_first_name = _clean_text(
        profile.get("first_name")
    )

    profile_last_name = _clean_text(
        profile.get("last_name")
    )

    profile_full_name = _clean_text(
        profile.get("full_name")
    )

    customer_name = (
        _clean_text(
            " ".join(
                part
                for part in [
                    profile_first_name,
                    profile_last_name,
                ]
                if part
            )
        )
        or profile_full_name
        or _display_name(user)
    )

    customer_email = (
        _clean_text(
            profile.get("email")
        )
        or _clean_text(
            metadata.get(
                "contact_email"
            )
        )
        or _clean_text(
            _attr(
                user,
                "email",
            )
        )
    )

    customer_phone = (
        _required_customer_phone(
            profile.get("phone")
        )
        or _required_customer_phone(
            metadata.get(
                "contact_phone"
            )
        )
        or _required_customer_phone(
            _attr(
                user,
                "phone",
            )
        )
    )

    return {
        "customer_name": (
            customer_name
            or "Villa Guest"
        ),
        "customer_email": (
            customer_email
        ),
        "customer_phone": (
            customer_phone
        ),
        "source": (
            "public.profiles"
            if profile
            else "authenticated_account"
        ),
        "profile_found": bool(
            profile
        ),
        "phone_ready": bool(
            customer_phone
        ),
        "phone_required": True,
        "contact_ready": bool(
            customer_phone
        ),
    }


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _centavos(value: Decimal) -> int:
    return int(
        (value * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _new_booking_code() -> str:
    return (
        f"TV-{datetime.now().year}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )


def _first(response: Any) -> dict[str, Any] | None:
    rows = _attr(response, "data", [])
    if isinstance(rows, list) and rows:
        return rows[0]
    if isinstance(rows, dict):
        return rows
    return None


def _get_booking(
    supabase: Client,
    booking_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    query = (
        supabase.table("bookings")
        .select("*")
        .eq("id", booking_id)
    )
    if user_id:
        query = query.eq("user_id", user_id)

    booking = _first(query.limit(1).execute())

    if not booking:
        raise HTTPException(
            status_code=404,
            detail="Booking not found.",
        )
    return booking


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _booking_is_fully_paid(booking: dict[str, Any]) -> bool:
    total_amount = _money(booking.get("total_amount"))
    amount_paid = _money(booking.get("amount_paid"))
    balance = _money(booking.get("balance_amount"))
    payment_status = _normalized_status(
        booking.get("payment_status")
    )

    total_covered = (
        total_amount > Decimal("0.00")
        and amount_paid + Decimal("0.01") >= total_amount
    )

    paid_status_with_zero_balance = (
        total_amount > Decimal("0.00")
        and balance <= Decimal("0.01")
        and payment_status == "paid"
    )

    return total_covered or paid_status_with_zero_balance


def _booking_blocks_new_stay(booking: dict[str, Any]) -> bool:
    booking_status = _normalized_status(
        booking.get("booking_status")
    )

    if booking_status in NON_BLOCKING_CUSTOMER_STATUSES:
        return False

    # Payment-only rule: a fully paid booking never blocks a new stay.
    return not _booking_is_fully_paid(booking)


def _confirmed_payment_totals_by_booking(
    supabase: Client,
    user_id: str,
) -> dict[str, Decimal]:
    """
    Sum confirmed booking_payments so an already-recorded
    PayMongo payment can repair a stale bookings row.
    """

    try:
        response = (
            supabase.table("booking_payments")
            .select("booking_id,amount,status")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.warning(
            "Could not reconcile booking_payments totals.",
            exc_info=True,
        )
        return {}

    paid_statuses = {
        "paid",
        "succeeded",
        "success",
        "completed",
        "complete",
    }

    totals: dict[str, Decimal] = {}

    for row in _attr(response, "data", []) or []:
        if not isinstance(row, dict):
            continue

        if _normalized_status(row.get("status")) not in paid_statuses:
            continue

        booking_id = str(row.get("booking_id") or "").strip()

        if not booking_id:
            continue

        totals[booking_id] = (
            totals.get(booking_id, Decimal("0.00"))
            + _money(row.get("amount"))
        )

    return totals


def _reconcile_booking_payment_state(
    supabase: Client,
    booking: dict[str, Any],
    confirmed_payment_total: Decimal | None = None,
) -> dict[str, Any]:
    """
    Make the bookings row match confirmed payments.

    This fixes the case where a PayMongo payment was already
    inserted into booking_payments but the booking update was
    interrupted. Repeated webhook/sync calls remain idempotent.
    """

    booking_id = str(booking.get("id") or "").strip()
    total_amount = _money(booking.get("total_amount"))
    stored_paid = max(
        Decimal("0.00"),
        _money(booking.get("amount_paid")),
    )
    stored_balance = max(
        Decimal("0.00"),
        _money(booking.get("balance_amount")),
    )

    if confirmed_payment_total is None and booking_id:
        user_id = str(booking.get("user_id") or "").strip()
        totals = _confirmed_payment_totals_by_booking(
            supabase,
            user_id,
        ) if user_id else {}
        confirmed_payment_total = totals.get(booking_id)

    confirmed_paid = max(
        Decimal("0.00"),
        _money(confirmed_payment_total or 0),
    )

    effective_paid = min(
        total_amount,
        max(stored_paid, confirmed_paid),
    ) if total_amount > Decimal("0.00") else max(
        stored_paid,
        confirmed_paid,
    )

    computed_balance = max(
        Decimal("0.00"),
        total_amount - effective_paid,
    )

    payment_status = _normalized_status(
        booking.get("payment_status")
    )

    zero_balance_paid_signal = (
        total_amount > Decimal("0.00")
        and stored_balance <= Decimal("0.01")
        and (
            stored_paid > Decimal("0.00")
            or confirmed_paid > Decimal("0.00")
            or payment_status == "paid"
        )
    )

    fully_paid = (
        total_amount > Decimal("0.00")
        and (
            effective_paid + Decimal("0.01") >= total_amount
            or zero_balance_paid_signal
        )
    )

    updates: dict[str, Any] = {}

    if fully_paid:
        normalized_booking_status = _normalized_status(
            booking.get("booking_status")
        )
        booking_needs_confirmation = (
            normalized_booking_status
            in {
                "",
                "pending",
                "pending payment",
                "awaiting payment",
            }
        )
        payment_row_is_stale = (
            abs(stored_paid - total_amount) > Decimal("0.01")
            or stored_balance > Decimal("0.01")
            or payment_status != "paid"
            or not booking.get("paid_at")
            or booking_needs_confirmation
        )

        if payment_row_is_stale:
            now = datetime.now(timezone.utc).isoformat()
            updates = {
                "amount_paid": float(total_amount),
                "balance_amount": 0.0,
                "payment_status": "Paid",
                "payment_message": (
                    "Payment confirmed. The booking is fully paid."
                ),
                "paid_at": booking.get("paid_at") or now,
                "updated_at": now,
            }

            if booking_needs_confirmation:
                updates["booking_status"] = "Confirmed"

    elif confirmed_paid > stored_paid + Decimal("0.01"):
        now = datetime.now(timezone.utc).isoformat()
        updates = {
            "amount_paid": float(effective_paid),
            "balance_amount": float(computed_balance),
            "payment_status": (
                "Partial"
                if effective_paid > Decimal("0.00")
                else booking.get("payment_status") or "Unpaid"
            ),
            "updated_at": now,
        }
        # An interrupted DB write must not leave a verified downpayment
        # marked as an unpaid/unconfirmed reservation.
        if effective_paid > Decimal("0.00") and _normalized_status(
            booking.get("booking_status")
        ) in {"", "pending", "pending payment", "awaiting payment"}:
            updates["booking_status"] = "Confirmed"
            updates["hold_expires_at"] = None

    if updates and booking_id:
        try:
            supabase.table("bookings").update(
                updates
            ).eq("id", booking_id).execute()
        except Exception:
            logger.exception(
                "Could not reconcile booking payment state. Booking=%s",
                booking_id,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "The payment was confirmed, but the booking status "
                    "could not be updated. Please refresh and try again."
                ),
            )

        reconciled = {**booking, **updates}
        _assign_prearrival_staff(reconciled, supabase)
        return reconciled

    _assign_prearrival_staff(booking, supabase)
    return booking


def _reconcile_customer_booking_rows(
    supabase: Client,
    user_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    totals = _confirmed_payment_totals_by_booking(
        supabase,
        user_id,
    )

    reconciled: list[dict[str, Any]] = []

    for row in rows:
        booking_id = str(row.get("id") or "").strip()
        reconciled.append(
            _reconcile_booking_payment_state(
                supabase,
                row,
                totals.get(booking_id),
            )
        )

    return reconciled


def _customer_booking_eligibility_from_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking = next(
        (
            row
            for row in rows
            if _booking_blocks_new_stay(row)
        ),
        None,
    )

    if not blocking:
        return {
            "can_book": True,
            "message": (
                "All existing bookings are fully paid. "
                "You may create another reservation immediately. "
                "No administrator approval is required."
            ),
            "blocking_booking": None,
            "requirements": {
                "payment_settled": True,
                "balance_cleared": True,
            },
        }

    total_amount = _money(blocking.get("total_amount"))
    amount_paid = _money(blocking.get("amount_paid"))
    balance = max(
        Decimal("0.00"),
        min(
            _money(blocking.get("balance_amount")),
            max(Decimal("0.00"), total_amount - amount_paid),
        ) if total_amount > Decimal("0.00") else _money(
            blocking.get("balance_amount")
        ),
    )

    return {
        "can_book": False,
        "message": (
            "Pay the remaining balance before checking "
            "availability for another villa."
        ),
        "blocking_booking": {
            **blocking,
            "balance_amount": float(balance),
        },
        "requirements": {
            "payment_settled": False,
            "balance_cleared": balance <= Decimal("0.01"),
        },
    }


def _customer_booking_eligibility(
    supabase: Client,
    user_id: str,
) -> dict[str, Any]:
    response = (
        supabase.table("bookings")
        .select(
            "id,booking_code,user_id,villa_id,"
            "villa_name,check_in_date,check_out_date,"
            "booking_status,stay_status,payment_status,"
            "total_amount,amount_paid,balance_amount,"
            "paid_at,created_at,updated_at"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    rows = _attr(response, "data", []) or []
    rows = _reconcile_customer_booking_rows(
        supabase,
        user_id,
        rows,
    )

    return _customer_booking_eligibility_from_rows(rows)


def _assert_customer_can_create_booking(
    supabase: Client,
    user_id: str,
) -> None:
    eligibility = _customer_booking_eligibility(
        supabase,
        user_id,
    )

    if eligibility["can_book"]:
        return

    blocking = eligibility.get("blocking_booking") or {}
    booking_code = blocking.get("booking_code") or blocking.get("id")
    balance = _money(blocking.get("balance_amount"))

    raise HTTPException(
        status_code=409,
        detail=(
            f"Booking {booking_code} still has a remaining balance of "
            f"PHP {balance:,.2f}. Pay the balance before creating "
            "another reservation."
        ),
    )


def _availability_blocks_booking(booking: dict[str, Any]) -> bool:
    return _normalized_status(
        booking.get("booking_status")
    ) not in AVAILABILITY_RELEASE_STATUSES


def _active_airbnb_stays(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    try:
        response = (
            supabase.table("airbnb_stays")
            .select("id,check_in_date,check_out_date,guest_count,villa_ids,status,expires_at,created_at")
            .in_("status", ["held", "confirmed"])
            .execute()
        )
    except Exception as error:
        logger.exception("Could not read Airbnb stay holds.")
        raise HTTPException(
            status_code=503,
            detail="Airbnb stay availability is unavailable. Apply the Airbnb stay database migration and retry.",
        ) from error

    now = datetime.now(timezone.utc)
    active = []
    for row in _attr(response, "data", []) or []:
        status_value = str(row.get("status") or "").lower()
        if status_value == "held":
            expires_at = row.get("expires_at")
            if not expires_at or datetime.fromisoformat(
                str(expires_at).replace("Z", "+00:00")
            ) <= now:
                continue
        if start_date and end_date:
            check_in = date.fromisoformat(str(row["check_in_date"])[:10])
            check_out = date.fromisoformat(str(row["check_out_date"])[:10])
            if check_in >= end_date or check_out <= start_date:
                continue
        active.append(row)
    return active


def _expire_stale_public_booking_holds(
    supabase: Client,
) -> int:
    """Release abandoned unpaid guest reservations after the hold window."""

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        response = (
            supabase.table("bookings")
            .select("id,booking_status,payment_status,hold_expires_at")
            .eq("guest_booking", True)
            .eq("booking_status", "Pending Payment")
            .eq("payment_status", "Unpaid")
            .lte("hold_expires_at", now_iso)
            .execute()
        )
    except Exception:
        logger.warning(
            "Could not scan expired public booking holds. "
            "Run the latest public guest booking migration.",
            exc_info=True,
        )
        return 0

    rows = _attr(response, "data", []) or []
    expired_count = 0

    for row in rows:
        booking_id = str(row.get("id") or "").strip()
        if not booking_id:
            continue

        try:
            (
                supabase.table("bookings")
                .update(
                    {
                        "booking_status": "Expired",
                        "paymongo_status": "expired",
                        "payment_message": (
                            "Reservation hold expired before payment was confirmed."
                        ),
                        "updated_at": now_iso,
                    }
                )
                .eq("id", booking_id)
                .eq("booking_status", "Pending Payment")
                .eq("payment_status", "Unpaid")
                .execute()
            )
            expired_count += 1
        except Exception:
            logger.warning(
                "Could not expire stale public booking hold %s.",
                booking_id,
                exc_info=True,
            )

    return expired_count


def _villa_operational(villa: dict[str, Any], on_date: date | None = None) -> bool:
    if on_date is not None and villa.get("maintenance_dates"):
        return (
            villa.get("manual_operational_status", "available") == "available"
            and not villa.get("undated_maintenance", False)
            and on_date.isoformat() not in villa["maintenance_dates"]
        )
    return _normalized_status(
        villa.get("operational_status", "available")
    ) not in {"under maintenance", "maintenance", "disabled"}


def _paymongo_mode() -> str:
    if PAYMONGO_SECRET_KEY.startswith("sk_test_"):
        return "test"
    if PAYMONGO_SECRET_KEY.startswith("sk_live_"):
        return "live"
    return "unconfigured"


def _paymongo_error(
    response: requests.Response,
    payment_method: str | None = None,
) -> str:
    try:
        body = response.json()
    except ValueError:
        return "PayMongo returned an invalid response."

    errors = body.get("errors", []) or []
    codes: list[str] = []
    messages: list[str] = []

    for item in errors:
        if not isinstance(item, dict):
            continue

        code = str(item.get("code") or "").strip()
        detail = str(item.get("detail") or "").strip()

        if code:
            codes.append(code.lower())

        if detail:
            messages.append(detail)

    combined = " ".join(messages).strip()
    combined_lower = combined.lower()

    method_details = PAYMONGO_METHOD_DETAILS.get(
        str(payment_method or "").lower(),
        {},
    )
    method_label = method_details.get(
        "label",
        "The selected payment method",
    )

    if (
        "payment_method_not_allowed" in codes
        or "payment method is not allowed" in combined_lower
        or (
            "not allowed" in combined_lower
            and "payment" in combined_lower
        )
        or (
            "payment_method_types"
            in combined_lower
            and (
                "invalid" in combined_lower
                or "unsupported" in combined_lower
                or "active" in combined_lower
            )
        )
    ):
        return (
            f"{method_label} is not active for this PayMongo account. "
            "Open PayMongo Dashboard → Settings → Payment Methods, "
            "activate the method, or choose another payment option."
        )

    if response.status_code == 401:
        return (
            "PayMongo rejected the API key. Confirm that "
            "PAYMONGO_SECRET_KEY contains the correct sk_test_ or sk_live_ key."
        )

    return (
        combined
        or str(body.get("message") or "").strip()
        or "PayMongo rejected the request."
    )


def _paymongo_request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    payment_method: str | None = None,
) -> dict[str, Any]:
    if _paymongo_mode() == "unconfigured":
        raise HTTPException(
            status_code=503,
            detail=(
                "PayMongo is not configured. "
                "Add PAYMONGO_SECRET_KEY to backend/.env."
            ),
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    if idempotency_key:
        headers["Idempotency-Key"] = (
            idempotency_key[:255]
        )

    last_error: Exception | None = None

    for attempt in range(2):
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=(
                    PAYMONGO_SECRET_KEY,
                    "",
                ),
                headers=headers,
                json=payload,
                timeout=(5, 25),
            )
        except requests.RequestException as error:
            last_error = error

            if attempt == 0:
                time.sleep(0.35)
                continue

            logger.exception(
                "Unable to connect to PayMongo."
            )

            raise HTTPException(
                status_code=502,
                detail=(
                    "The payment service could "
                    "not be reached. Please try again."
                ),
            ) from error

        if (
            response.status_code
            in {500, 502, 503, 504}
            and attempt == 0
        ):
            time.sleep(0.35)
            continue

        if not response.ok:
            logger.error(
                "PayMongo error %s: %s",
                response.status_code,
                response.text[:1000],
            )

            raise HTTPException(
                status_code=502,
                detail=_paymongo_error(
                    response,
                    payment_method=payment_method,
                ),
            )

        try:
            result = response.json()
        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    "PayMongo returned an "
                    "unreadable response."
                ),
            ) from error

        if not isinstance(result, dict):
            raise HTTPException(
                status_code=502,
                detail=(
                    "PayMongo returned an invalid response."
                ),
            )

        return result

    raise HTTPException(
        status_code=502,
        detail=(
            "The payment service could not "
            "be reached. Please try again."
        ),
    ) from last_error


def _checkout_urls(booking_id: str) -> tuple[str, str]:
    success_query = urlencode(
        {"payment": "success", "booking": booking_id}
    )
    cancel_query = urlencode(
        {"payment": "cancelled", "booking": booking_id}
    )
    return (
        f"{FRONTEND_URL}/dashboard?{success_query}",
        f"{FRONTEND_URL}/dashboard?{cancel_query}",
    )


def _payment_method_code(
    payment: dict[str, Any],
) -> str:
    attributes = payment.get("attributes", {}) or {}
    source = attributes.get("source", {}) or {}
    paymongo_type = str(
        source.get("type") or ""
    ).lower()

    return {
        "paymaya": "maya",
        "maya": "maya",
        "card": "debit",
        "gcash": "gcash",
        "qrph": "qrph",
    }.get(
        paymongo_type,
        paymongo_type or "paymongo",
    )


def _method_label(payment: dict[str, Any]) -> str:
    method_code = _payment_method_code(payment)

    details = PAYMONGO_METHOD_DETAILS.get(
        method_code,
        {},
    )

    if details.get("label"):
        return str(details["label"])

    return PAYMENT_METHOD_LABELS.get(
        method_code,
        method_code.replace("_", " ").title() or "PayMongo",
    )


def _session_payments(
    session_data: dict[str, Any],
) -> list[dict[str, Any]]:
    attributes = session_data.get("attributes", {}) or {}
    payments = attributes.get("payments", [])

    if not isinstance(payments, list):
        return []

    return [
        payment
        for payment in payments
        if isinstance(payment, dict)
    ]


def _paid_payment(
    session_data: dict[str, Any],
) -> dict[str, Any] | None:
    for payment in reversed(
        _session_payments(session_data)
    ):
        status = str(
            (payment.get("attributes", {}) or {}).get(
                "status",
                "",
            )
        ).lower()

        if status == "paid":
            return payment

    return None


def _latest_payment(
    session_data: dict[str, Any],
) -> dict[str, Any] | None:
    payments = _session_payments(session_data)
    return payments[-1] if payments else None


def _session_payment_state(
    session_data: dict[str, Any],
) -> dict[str, Any]:
    attributes = session_data.get("attributes", {}) or {}
    paid = _paid_payment(session_data)
    latest = _latest_payment(session_data)

    session_status = str(
        attributes.get("status") or "active"
    ).lower()

    latest_attributes = (
        latest.get("attributes", {})
        if latest
        else {}
    ) or {}

    latest_status = str(
        latest_attributes.get("status") or ""
    ).lower()

    metadata = attributes.get("metadata", {}) or {}
    selected_method = str(
        metadata.get("payment_method") or ""
    ).lower()

    method_code = (
        _payment_method_code(paid)
        if paid
        else (
            _payment_method_code(latest)
            if latest
            else selected_method
        )
    )

    if paid:
        return {
            "state": "paid",
            "paid": True,
            "payment": paid,
            "method_code": method_code,
            "method_label": _method_label(paid),
            "message": "Payment confirmed by PayMongo.",
            "session_status": session_status,
            "latest_payment_status": "paid",
        }

    if session_status == "expired":
        return {
            "state": "expired",
            "paid": False,
            "payment": latest,
            "method_code": method_code,
            "method_label": PAYMONGO_METHOD_DETAILS.get(
                method_code,
                {},
            ).get("label", "PayMongo"),
            "message": (
                "This checkout session is expired. "
                "Create a new secure checkout to continue."
            ),
            "session_status": session_status,
            "latest_payment_status": latest_status,
        }

    if latest_status in {
        "failed",
        "cancelled",
        "canceled",
    }:
        return {
            "state": "failed",
            "paid": False,
            "payment": latest,
            "method_code": method_code,
            "method_label": PAYMONGO_METHOD_DETAILS.get(
                method_code,
                {},
            ).get("label", "PayMongo"),
            "message": (
                "The latest payment attempt was not completed. "
                "The reservation remains saved and can be paid again."
            ),
            "session_status": session_status,
            "latest_payment_status": latest_status,
        }

    return {
        "state": "pending",
        "paid": False,
        "payment": latest,
        "method_code": method_code,
        "method_label": PAYMONGO_METHOD_DETAILS.get(
            method_code,
            {},
        ).get("label", "PayMongo"),
        "message": (
            "Payment has not been confirmed yet. "
            "Complete the PayMongo checkout or wait for webhook verification."
        ),
        "session_status": session_status,
        "latest_payment_status": latest_status,
    }


def _save_checkout_attempt(
    supabase: Client,
    *,
    booking: dict[str, Any],
    checkout_session_id: str,
    reference_number: str | None,
    payment_method_code: str,
    payment_scope: str,
    amount: Decimal,
    status: str,
    checkout_url: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> None:
    try:
        supabase.table(
            "booking_checkout_attempts"
        ).upsert(
            {
                "booking_id": booking["id"],
                "user_id": booking["user_id"],
                "paymongo_checkout_session_id": (
                    checkout_session_id
                ),
                "reference_number": reference_number,
                "payment_method_code": (
                    payment_method_code
                ),
                "payment_method_label": (
                    PAYMONGO_METHOD_DETAILS.get(
                        payment_method_code,
                        {},
                    ).get(
                        "label",
                        payment_method_code,
                    )
                ),
                "payment_scope": payment_scope,
                "amount": float(amount),
                "currency": "PHP",
                "environment": _paymongo_mode(),
                "status": status,
                "checkout_url": checkout_url,
                "raw_payload": raw_payload,
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
            on_conflict="paymongo_checkout_session_id",
        ).execute()
    except Exception:
        logger.warning(
            (
                "Could not update booking_checkout_attempts. "
                "Run the latest bookings.sql migration."
            ),
            exc_info=True,
        )


def _confirmed_amount_for_booking(supabase: Client, booking_id: str) -> Decimal:
    """Payment-ledger total by BOOKING, including anonymous Messenger guests.

    Guest bookings use user_id=NULL, so a lookup filtered by user_id
    cannot repair an interrupted booking update.
    """
    records = _attr(
        supabase.table("booking_payments")
        .select("amount,status")
        .eq("booking_id", booking_id)
        .execute(),
        "data", [],
    ) or []
    paid_states = {"paid", "succeeded", "success", "completed", "complete"}
    return sum(
        (_money(row.get("amount")) for row in records
         if _normalized_status(row.get("status")) in paid_states),
        Decimal("0.00"),
    )


def _apply_payment(
    supabase: Client,
    booking: dict[str, Any],
    session_data: dict[str, Any],
    payment: dict[str, Any],
    *, manual_draft: bool = False, public_draft: bool = False,
) -> dict[str, Any]:
    payment_id = str(payment.get("id") or "").strip()

    if not payment_id:
        raise HTTPException(
            status_code=422,
            detail="PayMongo payment ID is missing.",
        )

    existing = _first(
        supabase.table("booking_payments")
        .select("id,amount,status")
        .eq("paymongo_payment_id", payment_id)
        .limit(1)
        .execute()
    )

    if existing:
        current_booking = _get_booking(
            supabase,
            str(booking["id"]),
            str(booking.get("user_id") or "") or None,
        )
        return _reconcile_booking_payment_state(
            supabase,
            current_booking,
            _confirmed_amount_for_booking(supabase, str(booking["id"])),
        )

    session_attributes = (
        session_data.get("attributes", {}) or {}
    )
    payment_attributes = (
        payment.get("attributes", {}) or {}
    )

    paid_amount = (
        Decimal(
            str(payment_attributes.get("amount", 0))
        )
        / Decimal("100")
    ).quantize(Decimal("0.01"))

    if paid_amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="PayMongo returned an invalid paid amount.",
        )

    total_amount = _money(booking.get("total_amount"))
    previous_paid = _money(booking.get("amount_paid"))
    next_paid = min(
        total_amount,
        previous_paid + paid_amount,
    )
    next_balance = max(
        Decimal("0.00"),
        total_amount - next_paid,
    )

    payment_method_code = _payment_method_code(
        payment
    )
    payment_method = _method_label(payment)

    payment_intent_id = (
        payment_attributes.get("payment_intent_id")
        or (
            session_attributes.get("payment_intent", {})
            or {}
        ).get("id")
    )

    paid_at = datetime.now(
        timezone.utc
    ).isoformat()

    fee_amount = (
        Decimal(
            str(payment_attributes.get("fee", 0))
        )
        / Decimal("100")
    ).quantize(Decimal("0.01"))

    net_amount = (
        Decimal(
            str(
                payment_attributes.get(
                    "net_amount",
                    payment_attributes.get("amount", 0),
                )
            )
        )
        / Decimal("100")
    ).quantize(Decimal("0.01"))

    payment_status = (
        "Paid"
        if next_balance <= 0
        else "Partial"
    )

    receipt_number = (
        booking.get("receipt_number")
        or f"RCPT-{booking['booking_code']}"
    )

    payment_record = {
                "booking_id": booking["id"],
                "user_id": booking["user_id"],
                "paymongo_checkout_session_id": (
                    session_data.get("id")
                ),
                "paymongo_payment_id": payment_id,
                "paymongo_payment_intent_id": payment_intent_id,
                "reference_number": (
                    session_attributes.get("reference_number")
                ),
                "amount": float(paid_amount),
                "currency": payment_attributes.get(
                    "currency",
                    "PHP",
                ),
                "payment_method": payment_method,
                "payment_method_code": payment_method_code,
                "status": payment_attributes.get(
                    "status",
                    "paid",
                ),
                "livemode": bool(
                    payment_attributes.get(
                        "livemode",
                        session_attributes.get(
                            "livemode",
                            _paymongo_mode() == "live",
                        ),
                    )
                ),
                "fee_amount": float(fee_amount),
                "net_amount": float(net_amount),
                "paid_at": paid_at,
                "raw_payload": {
                    "session": session_data,
                    "payment": payment,
                },
            }
    booking_update = {
            "booking_status": "Confirmed",
            "payment_status": payment_status,
            "amount_paid": float(next_paid),
            "balance_amount": float(next_balance),
            "payment_method": payment_method,
            "payment_method_code": payment_method_code,
            "payment_environment": _paymongo_mode(),
            "payment_message": (
                f"Payment confirmed through {payment_method}."
            ),
            "payment_last_checked_at": paid_at,
            "paymongo_status": "paid",
            "paymongo_checkout_session_id": (
                session_data.get("id")
            ),
            "paymongo_payment_id": payment_id,
            "paymongo_payment_intent_id": payment_intent_id,
            "receipt_number": receipt_number,
            "paid_at": paid_at,
            "hold_expires_at": None,
            "updated_at": paid_at,
        }
    if manual_draft or public_draft:
        response = supabase.rpc("finalize_public_booking_checkout" if public_draft else "finalize_manual_booking_checkout", {
            "p_checkout_id": str(booking["id"]),
            "p_booking_update": booking_update,
            "p_payment": payment_record,
        }).execute()
        result = _attr(response, "data", None)
        if not isinstance(result, dict) or not result.get("id"):
            raise HTTPException(status_code=500, detail="Payment verified, but booking finalization must be retried.")
        _assign_prearrival_staff(result, supabase)
        return result

    try:
        supabase.table("booking_payments").insert(
            payment_record
        ).execute()

    except Exception as error:
        message = str(error).lower()
        if any(part in message for part in (
            "duplicate key", "already exists", "unique constraint", "23505"
        )):
            # Webhook and live status polling can race to record the same
            # PayMongo ID. Read the ledger instead of recording twice.
            current = _get_booking(supabase, str(booking["id"]))
            return _reconcile_booking_payment_state(
                supabase, current,
                _confirmed_amount_for_booking(supabase, str(booking["id"])),
            )
        raise

    supabase.table("bookings").update(
        booking_update
    ).eq("id", booking["id"]).execute()

    _save_checkout_attempt(
        supabase,
        booking=booking,
        checkout_session_id=str(
            session_data.get("id") or ""
        ),
        reference_number=session_attributes.get(
            "reference_number"
        ),
        payment_method_code=payment_method_code,
        payment_scope=str(
            (
                session_attributes.get(
                    "metadata",
                    {},
                )
                or {}
            ).get(
                "payment_scope",
                "selected",
            )
        ),
        amount=paid_amount,
        status="paid",
        checkout_url=session_attributes.get(
            "checkout_url"
        ),
        raw_payload={
            "session": session_data,
            "payment": payment,
        },
    )

    updated_booking = _get_booking(
        supabase,
        str(booking["id"]),
        str(booking.get("user_id") or "") or None,
    )

    from feedback_service import queue_feedback_invitation
    queue_feedback_invitation(updated_booking, supabase)

    return _reconcile_booking_payment_state(
        supabase,
        updated_booking,
    )


@router.get("/eligibility")
def booking_eligibility(request: Request):
    supabase, _user, user_id, _access, _refresh = _auth(request)
    return _customer_booking_eligibility(supabase, user_id)


@router.get("/calendar-availability")
def booking_calendar_availability(
    request: Request,
    start_date: date,
    end_date: date,
    guest_count: int = 1,
):
    _auth(request)

    if guest_count < 1 or guest_count > MAX_GUEST_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"Guest count must be between 1 and {MAX_GUEST_COUNT}.",
        )

    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="The calendar end date must be after the start date.",
        )

    range_days = (end_date - start_date).days
    if range_days > 62:
        raise HTTPException(
            status_code=422,
            detail="Calendar availability can be requested for up to 63 days.",
        )

    service = _service()
    active_villa_catalog = (
        get_villa_catalog_map(
            service
        )
    )
    response = (
        service.table("bookings")
        .select(
            """
            villa_id,
            check_in_date,
            check_out_date,
            booking_status
            """
        )
        .execute()
    )

    blocked_by_date: dict[str, set[str]] = {}
    for row in _attr(response, "data", []) or []:
        if not _availability_blocks_booking(row):
            continue
        date_key = str(row.get("check_in_date") or "")
        villa_id = str(row.get("villa_id") or "")
        if date_key and villa_id:
            blocked_by_date.setdefault(date_key, set()).add(villa_id)

    days: dict[str, dict[str, Any]] = {}
    current = start_date
    while current <= end_date:
        date_key = current.isoformat()
        blocked = blocked_by_date.get(date_key, set())
        available_ids: list[str] = []
        booked_ids: list[str] = []
        unavailable_ids: list[str] = []

        for villa_id, villa in active_villa_catalog.items():
            if not _villa_operational(villa, current):
                unavailable_ids.append(villa_id)
                continue
            if villa_id in blocked:
                booked_ids.append(villa_id)
                continue
            if guest_count > int(villa["capacity"]):
                unavailable_ids.append(villa_id)
                continue
            available_ids.append(villa_id)

        days[date_key] = {
            "available_count": len(available_ids),
            "available_villa_ids": available_ids,
            "booked_villa_ids": booked_ids,
            "unavailable_villa_ids": unavailable_ids,
        }
        current += timedelta(days=1)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "guest_count": guest_count,
        "days": days,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

def _villa_date_conflict(
    existing_booking: dict[str, Any],
    requested_check_in: date,
    requested_check_out: date,
) -> bool:
    """
    Check if a villa reservation overlaps another reservation.
    """

    if not _availability_blocks_booking(existing_booking):
        return False

    existing_check_in = existing_booking.get(
        "check_in_date"
    )

    existing_check_out = existing_booking.get(
        "check_out_date"
    )

    if not existing_check_in:
        return False

    existing_start = date.fromisoformat(
        str(existing_check_in)
    )

    if existing_check_out:
        existing_end = date.fromisoformat(
            str(existing_check_out)
        )
    else:
        existing_end = existing_start + timedelta(days=1)

    return (
        existing_start < requested_check_out
        and existing_end > requested_check_in
    )
@router.get("/availability")
def booking_availability(
    request: Request,
    check_in_date: date,
    guest_count: int = 1,
):
    _auth(request)

    if check_in_date < date.today():
        raise HTTPException(
            status_code=422,
            detail="Choose today or a future date.",
        )

    if guest_count < 1 or guest_count > MAX_GUEST_COUNT:
        raise HTTPException(
            status_code=422,
            detail=(
                "Guest count must be between "
                f"1 and {MAX_GUEST_COUNT}."
            ),
        )

    service = _service()
    active_villa_catalog = (
        get_villa_catalog_map(
            service
        )
    )

    response = (
        service.table("bookings")
        .select(
            "villa_id,booking_status"
        )
        .eq(
            "check_in_date",
            check_in_date.isoformat(),
        )
        .execute()
    )

    blocked_villas = {
        str(row.get("villa_id"))
        for row in (
            _attr(
                response,
                "data",
                [],
            )
            or []
        )
        if _availability_blocks_booking(row)
    }

    villas = []

    for villa_id, villa in (
        active_villa_catalog.items()
    ):
        operational = _villa_operational(villa, check_in_date)
        available = (
            operational
            and villa_id not in blocked_villas
            and guest_count <= int(villa["capacity"])
        )

        villas.append(
            {
                "villa_id": villa_id,
                "villa_name": villa["name"],
                "capacity": villa["capacity"],
                "image": villa["image"],
                "price": float(
                    villa["price"]
                ),
                "available": available,
                "reason": (
                    "Available"
                    if available
                    else (
                        "Under Maintenance"
                        if not operational
                        else (
                            "Booked"
                            if villa_id in blocked_villas
                            else "Too Small"
                        )
                    )
                ),
            }
        )

    return {
        "check_in_date": (
            check_in_date.isoformat()
        ),
        "guest_count": guest_count,
        "villas": villas,
        "available_villa_ids": [
            villa["villa_id"]
            for villa in villas
            if villa["available"]
        ],
    }


@router.get("")
def list_bookings(request: Request):
    supabase, _user, user_id, _access, _refresh = _auth(
        request
    )
    response = (
        supabase.table("bookings")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    booking_rows = _attr(response, "data", []) or []
    booking_rows = _reconcile_customer_booking_rows(
        supabase,
        user_id,
        booking_rows,
    )

    return {
        "bookings": booking_rows,
        "eligibility": (
            _customer_booking_eligibility_from_rows(
                booking_rows
            )
        ),
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


@router.get("/profile-contact")
def booking_profile_contact(
    request: Request,
):
    (
        supabase,
        user,
        user_id,
        _access,
        _refresh,
    ) = _auth(request)

    snapshot = (
        _profile_contact_snapshot(
            supabase,
            user,
            user_id,
        )
    )

    return {
        "name": snapshot[
            "customer_name"
        ],
        "email": snapshot[
            "customer_email"
        ],
        "phone": snapshot[
            "customer_phone"
        ],
        "source": snapshot[
            "source"
        ],
        "profile_found": snapshot[
            "profile_found"
        ],
        "phone_ready": snapshot[
            "phone_ready"
        ],
        "phone_required": snapshot[
            "phone_required"
        ],
        "contact_ready": snapshot[
            "contact_ready"
        ],
        "message": (
            "A valid phone number is required before "
            "the customer can create a booking."
        ),
    }


@router.get("/paymongo/status")
def paymongo_status(request: Request):
    _auth(request)

    mode = _paymongo_mode()
    configured = mode != "unconfigured"

    supported_methods = []

    for method_id, details in (
        PAYMONGO_METHOD_DETAILS.items()
    ):
        supported_methods.append(
            {
                "id": method_id,
                "label": details["label"],
                "paymongo_type": (
                    details["paymongo_type"]
                ),
                "flow_type": (
                    details["flow_type"]
                ),
                "customer_steps": (
                    details["customer_steps"]
                ),
                "environment_instructions": (
                    details["test_instructions"]
                    if mode == "test"
                    else details["live_instructions"]
                ),
            }
        )

    return {
        "configured": configured,
        "environment": mode,
        "sandbox": mode == "test",
        "webhook_configured": bool(
            PAYMONGO_WEBHOOK_SECRET
        ),
        "database_webhook_access": bool(
            SUPABASE_SERVICE_ROLE_KEY
        ),
        "supported_methods": supported_methods,
        "receipt_policy": (
            "A receipt becomes available only after "
            "PayMongo confirms a paid payment through "
            "the webhook or a server-side status check."
        ),
        "activation_note": (
            "GCash, Maya, Cards, and QR Ph must each "
            "be Active in the PayMongo owner account."
        ),
        "message": (
            "Secure online payment is ready."
            if configured
            else (
                "Online payment is not configured. "
                "Add PAYMONGO_SECRET_KEY to backend/.env."
            )
        ),
    }


@router.post("/paymongo/test")
def create_paymongo_test_checkout(
    data: PayMongoDiagnosticRequest,
    request: Request,
):
    supabase, user, user_id, _access, _refresh = _auth(
        request
    )

    if _paymongo_mode() != "test":
        raise HTTPException(
            status_code=409,
            detail=(
                "Payment diagnostics are available "
                "only while an sk_test_ key is configured."
            ),
        )

    method_details = PAYMONGO_METHOD_DETAILS[
        data.payment_method
    ]

    profile_contact = _profile_contact_snapshot(
        supabase,
        user,
        user_id,
    )

    reference = (
        "VILLA-CHANNEL-CHECK-"
        + uuid.uuid4().hex[:8].upper()
    )

    attributes: dict[str, Any] = {
        "line_items": [
            {
                "name": (
                    "The Villa payment channel check"
                ),
                "description": (
                    f"Verify {method_details['label']} "
                    "checkout availability."
                ),
                "amount": 10000,
                "currency": "PHP",
                "quantity": 1,
            }
        ],
        "payment_method_types": (
            PAYMONGO_METHOD_MAP[
                data.payment_method
            ]
        ),
        "success_url": (
            f"{FRONTEND_URL}/dashboard?"
            "payment_channel=success"
        ),
        "cancel_url": (
            f"{FRONTEND_URL}/dashboard?"
            "payment_channel=cancelled"
        ),
        "reference_number": reference,
        "show_description": True,
        "show_line_items": True,
        "send_email_receipt": False,
        "metadata": {
            "purpose": "owner_payment_channel_check",
            "payment_method": data.payment_method,
            "user_id": user_id,
        },
    }

    billing: dict[str, Any] = {}

    if profile_contact.get("customer_name"):
        billing["name"] = profile_contact[
            "customer_name"
        ]

    if profile_contact.get("customer_email"):
        billing["email"] = profile_contact[
            "customer_email"
        ]

    if profile_contact.get("customer_phone"):
        billing["phone"] = profile_contact[
            "customer_phone"
        ]

    if billing:
        attributes["billing"] = billing

    result = _paymongo_request(
        "POST",
        PAYMONGO_CREATE_CHECKOUT_URL,
        payload={
            "data": {
                "attributes": attributes
            }
        },
        idempotency_key=(
            f"villa-channel-check-"
            f"{data.payment_method}-{reference}"
        ),
        payment_method=data.payment_method,
    )

    checkout = result.get("data", {})
    checkout_attributes = (
        checkout.get("attributes", {})
        or {}
    )

    checkout_url = checkout_attributes.get(
        "checkout_url"
    )

    if not checkout_url:
        raise HTTPException(
            status_code=502,
            detail=(
                "PayMongo did not return a checkout URL "
                f"for {method_details['label']}."
            ),
        )

    return {
        "configured": True,
        "environment": "test",
        "sandbox": True,
        "payment_method": data.payment_method,
        "payment_method_label": (
            method_details["label"]
        ),
        "flow_type": (
            method_details["flow_type"]
        ),
        "message": (
            f"{method_details['label']} sandbox "
            "checkout was created."
        ),
        "instructions": (
            method_details["test_instructions"]
        ),
        "safety_warning": (
            "Do not scan a sandbox QR with a real "
            "banking or wallet application."
            if data.payment_method == "qrph"
            else None
        ),
        "checkout_session_id": checkout.get("id"),
        "checkout_url": checkout_url,
        "reference_number": reference,
    }


@router.post("")
def create_booking(
    data: BookingCreateRequest,
    request: Request,
):
    supabase, user, user_id, _access, _refresh = _auth(
        request
    )

    active_villa_catalog = (
        get_villa_catalog_map(
            supabase
        )
    )

    villa = (
        active_villa_catalog.get(
            data.villa_id
        )
    )
    if not villa:
        raise HTTPException(
            status_code=422,
            detail="The selected villa does not exist.",
        )

    if data.check_in_date < date.today():
        raise HTTPException(
            status_code=422,
            detail="Choose today or a future booking date.",
        )

    if data.check_in_time not in ALLOWED_CHECK_IN_TIMES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Choose one of the available "
                "check-in times."
            ),
        )

    if data.guest_count < 1 or data.guest_count > MAX_GUEST_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"Choose a guest count from 1 to {MAX_GUEST_COUNT}.",
        )

    if data.guest_count > int(villa["capacity"]):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{villa['name']} accepts up to "
                f"{villa['capacity']} guests."
            ),
        )

    if not _villa_operational(villa, data.check_in_date):
        raise HTTPException(
            status_code=409,
            detail=f"{villa['name']} is currently under maintenance.",
        )

    service = _service()
    _assert_customer_can_create_booking(service, user_id)

    existing_response = (
        service.table("bookings")
        .select("id,booking_status")
        .eq("villa_id", data.villa_id)
        .eq(
            "check_in_date",
            data.check_in_date.isoformat(),
        )
        .execute()
    )

    for row in _attr(existing_response, "data", []) or []:
        if _availability_blocks_booking(row):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This villa is no longer "
                    "available on the selected date."
                ),
            )

    total_amount = _money(villa["price"])
    selected_due = (
        total_amount
        if data.payment_choice == "full"
        else (
            total_amount * Decimal("0.50")
        ).quantize(Decimal("0.01"))
    )

    profile_contact = (
        _profile_contact_snapshot(
            service,
            user,
            user_id,
        )
    )

    if not profile_contact.get(
        "phone_ready"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Add a valid Philippine mobile number "
                "in Guest Profile before booking a villa."
            ),
        )

    check_out_date = (
        data.check_in_date
        + timedelta(days=1)
    )

    row = {
        "booking_code": _new_booking_code(),
        "user_id": user_id,
        "customer_name": profile_contact[
            "customer_name"
        ],
        "customer_email": profile_contact[
            "customer_email"
        ],
        "customer_phone": profile_contact[
            "customer_phone"
        ],
        "villa_id": data.villa_id,
        "villa_name": villa["name"],
        "villa_image": villa["image"],
        "check_in_date": data.check_in_date.isoformat(),
        "check_out_date": check_out_date.isoformat(),
        "check_in_time": data.check_in_time,
        "guest_count": data.guest_count,
        "nights": 1,
        "notes": (
            data.notes.strip() if data.notes else None
        ),
        "total_amount": float(total_amount),
        "payment_choice": data.payment_choice,
        "payment_method": (
            PAYMONGO_METHOD_DETAILS[
                data.payment_method
            ]["label"]
        ),
        "payment_method_code": (
            data.payment_method
        ),
        "payment_environment": (
            _paymongo_mode()
        ),
        "payment_due_amount": float(selected_due),
        "amount_paid": 0,
        "balance_amount": float(total_amount),
        "booking_status": "Pending Payment",
        "stay_status": "Not Checked In",
        "payment_status": "Unpaid",
        "payment_message": (
            "Reservation saved. Secure payment "
            "has not been completed yet."
        ),
        "payment_last_checked_at": None,
        "paymongo_status": "not_started",
    }

    def insert_booking():
        return (
            service.table("bookings")
            .insert(row)
            .execute()
        )

    try:
        response = insert_booking()
    except Exception as error:
        error_message = str(
            error
        ).lower()

        if (
            "unpaid balance" in error_message
            or "fully paid" in error_message
            or "unsettled booking" in error_message
        ):
            # Re-read and reconcile every confirmed payment
            # before deciding that the customer is blocked.
            # This prevents an older database guard from
            # rejecting a booking that is already Paid with
            # a zero balance.
            eligibility = (
                _customer_booking_eligibility(
                    service,
                    user_id,
                )
            )

            if eligibility.get("can_book"):
                try:
                    response = insert_booking()
                except Exception as retry_error:
                    retry_message = str(
                        retry_error
                    ).lower()

                    if (
                        "unpaid balance" in retry_message
                        or "fully paid" in retry_message
                        or "unsettled booking" in retry_message
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Your payment is already settled, but the "
                                "database is still using an older booking "
                                "guard. Run payment_only_rebooking_V23.sql "
                                "in Supabase, then try again."
                            ),
                        ) from retry_error

                    raise
            else:
                blocking = (
                    eligibility.get(
                        "blocking_booking"
                    )
                    or {}
                )
                balance = _money(
                    blocking.get(
                        "balance_amount"
                    )
                )
                booking_code = (
                    blocking.get(
                        "booking_code"
                    )
                    or blocking.get("id")
                    or "current booking"
                )

                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Booking {booking_code} still has a remaining "
                        f"balance of PHP {balance:,.2f}. Pay the balance "
                        "before creating another reservation."
                    ),
                ) from error

        elif (
            "bookings_active_villa_date_unique"
            in error_message
            or "already booked for the selected date"
            in error_message
            or "duplicate key" in error_message
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This villa was just booked "
                    "for the selected date. Choose "
                    "another available villa."
                ),
            ) from error

        else:
            logger.exception(
                "Could not create booking."
            )

            raise HTTPException(
                status_code=400,
                detail=(
                    "The booking could not be stored. "
                    "Confirm the booking SQL and backend "
                    "service-role key, then try again."
                ),
            ) from error

    booking = _first(response)
    if not booking:
        raise HTTPException(
            status_code=500,
            detail="The booking could not be returned.",
        )

    return {
        "message": (
            "Booking saved. Continue to "
            "secure PayMongo checkout."
        ),
        "booking": booking,
    }


@router.post("/{booking_id}/checkout")
def create_booking_checkout(
    booking_id: str,
    data: CheckoutRequest,
    request: Request,
):
    supabase, _user, user_id, _access, _refresh = _auth(
        request
    )

    booking = _get_booking(
        supabase,
        booking_id,
        user_id,
    )
    booking = _reconcile_booking_payment_state(
        supabase,
        booking,
    )

    if str(
        booking.get("booking_status", "")
    ).lower() in {
        "cancelled",
        "completed",
        "expired",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "This booking cannot accept "
                "another payment."
            ),
        )

    method_details = PAYMONGO_METHOD_DETAILS[
        data.payment_method
    ]

    total_amount = _money(
        booking.get("total_amount")
    )
    amount_paid = _money(
        booking.get("amount_paid")
    )
    balance_amount = max(
        Decimal("0.00"),
        total_amount - amount_paid,
    )

    if balance_amount <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This booking is already fully paid."
            ),
        )

    payment_choice = str(
        booking.get(
            "payment_choice",
            "half",
        )
    ).lower()

    initial_target = (
        total_amount
        if payment_choice == "full"
        else (
            total_amount * Decimal("0.50")
        ).quantize(
            Decimal("0.01")
        )
    )

    if data.payment_scope == "balance":
        amount_to_pay = balance_amount
        line_item_name = (
            f"{booking['villa_name']} "
            "remaining balance"
        )
        payment_scope = "balance"
    else:
        amount_to_pay = max(
            Decimal("0.00"),
            min(
                balance_amount,
                initial_target - amount_paid,
            ),
        )

        if amount_to_pay <= 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The required initial payment has "
                    "already been completed. Choose "
                    "Pay Remaining Balance instead."
                ),
            )

        line_item_name = (
            f"{booking['villa_name']} "
            + (
                "full payment"
                if payment_choice == "full"
                else "50% downpayment"
            )
        )
        payment_scope = "selected"

    success_url, cancel_url = _checkout_urls(
        booking_id
    )

    attempt_nonce = (
        uuid.uuid4().hex[:10].upper()
    )

    reference = (
        f"{booking['booking_code']}-"
        f"{payment_scope.upper()}-"
        f"{attempt_nonce}"
    )[:255]

    billing: dict[str, Any] = {}

    if booking.get("customer_name"):
        billing["name"] = (
            booking["customer_name"]
        )

    if booking.get("customer_email"):
        billing["email"] = (
            booking["customer_email"]
        )

    if booking.get("customer_phone"):
        billing["phone"] = (
            booking["customer_phone"]
        )

    attributes: dict[str, Any] = {
        "line_items": [
            {
                "name": line_item_name,
                "description": (
                    "The Villa reservation "
                    f"{booking['booking_code']}"
                ),
                "amount": _centavos(
                    amount_to_pay
                ),
                "currency": "PHP",
                "quantity": 1,
            }
        ],
        # Only the method selected by the customer
        # appears on this hosted checkout.
        "payment_method_types": (
            PAYMONGO_METHOD_MAP[
                data.payment_method
            ]
        ),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "reference_number": reference,
        "show_description": True,
        "show_line_items": True,
        "send_email_receipt": bool(
            booking.get("customer_email")
        ),
        "metadata": {
            "booking_id": str(
                booking["id"]
            ),
            "booking_code": str(
                booking["booking_code"]
            ),
            "user_id": user_id,
            "payment_scope": payment_scope,
            "payment_method": (
                data.payment_method
            ),
            "payment_environment": (
                _paymongo_mode()
            ),
            "attempt_nonce": attempt_nonce,
        },
    }

    if billing:
        attributes["billing"] = billing

    result = _paymongo_request(
        "POST",
        PAYMONGO_CREATE_CHECKOUT_URL,
        payload={
            "data": {
                "attributes": attributes
            }
        },
        idempotency_key=(
            f"booking-{booking_id}-"
            f"{payment_scope}-"
            f"{data.payment_method}-"
            f"{_centavos(amount_to_pay)}-"
            f"{attempt_nonce}"
        ),
        payment_method=data.payment_method,
    )

    checkout = result.get("data", {})
    checkout_attributes = (
        checkout.get("attributes", {})
        or {}
    )
    checkout_url = (
        checkout_attributes.get(
            "checkout_url"
        )
    )
    checkout_session_id = str(
        checkout.get("id") or ""
    ).strip()

    if (
        not checkout_url
        or not checkout_session_id
    ):
        raise HTTPException(
            status_code=502,
            detail=(
                "PayMongo did not return a complete "
                f"{method_details['label']} checkout."
            ),
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    service = _service()

    service.table("bookings").update(
        {
            "payment_method": (
                method_details["label"]
            ),
            "payment_method_code": (
                data.payment_method
            ),
            "payment_environment": (
                _paymongo_mode()
            ),
            "payment_due_amount": float(
                amount_to_pay
            ),
            "payment_message": (
                f"{method_details['label']} checkout "
                "created. Waiting for payment confirmation."
            ),
            "payment_last_checked_at": now,
            "paymongo_checkout_session_id": (
                checkout_session_id
            ),
            "paymongo_checkout_url": (
                checkout_url
            ),
            "paymongo_reference_number": (
                reference
            ),
            "paymongo_status": (
                "checkout_created"
            ),
            "updated_at": now,
        }
    ).eq(
        "id",
        booking_id,
    ).eq(
        "user_id",
        user_id,
    ).execute()

    _save_checkout_attempt(
        service,
        booking=booking,
        checkout_session_id=(
            checkout_session_id
        ),
        reference_number=reference,
        payment_method_code=(
            data.payment_method
        ),
        payment_scope=payment_scope,
        amount=amount_to_pay,
        status="checkout_created",
        checkout_url=checkout_url,
        raw_payload=result,
    )

    return {
        "message": (
            f"Secure {method_details['label']} "
            "checkout is ready."
        ),
        "booking_id": booking_id,
        "booking_code": (
            booking["booking_code"]
        ),
        "amount": float(
            amount_to_pay
        ),
        "payment_scope": payment_scope,
        "payment_method": (
            data.payment_method
        ),
        "payment_method_label": (
            method_details["label"]
        ),
        "flow_type": (
            method_details["flow_type"]
        ),
        "environment": (
            _paymongo_mode()
        ),
        "sandbox": (
            _paymongo_mode() == "test"
        ),
        "environment_instructions": (
            method_details[
                "test_instructions"
            ]
            if _paymongo_mode() == "test"
            else method_details[
                "live_instructions"
            ]
        ),
        "receipt_ready": False,
        "receipt_message": (
            "The receipt is released only after "
            "PayMongo confirms the payment."
        ),
        "checkout_session_id": (
            checkout_session_id
        ),
        "checkout_url": checkout_url,
    }


@router.post("/{booking_id}/sync-payment")
def sync_booking_payment(
    booking_id: str,
    request: Request,
):
    supabase, _user, user_id, _access, _refresh = _auth(
        request
    )

    booking = _get_booking(
        supabase,
        booking_id,
        user_id,
    )
    booking = _reconcile_booking_payment_state(
        supabase,
        booking,
    )

    if _booking_is_fully_paid(booking):
        return {
            "synced": True,
            "state": "paid",
            "receipt_ready": bool(booking.get("receipt_number")),
            "message": (
                "Payment is fully settled. You may book another villa."
            ),
            "booking": booking,
        }

    session_id = str(
        booking.get(
            "paymongo_checkout_session_id"
        )
        or ""
    ).strip()

    if not session_id:
        return {
            "synced": False,
            "state": "not_started",
            "receipt_ready": False,
            "message": (
                "No PayMongo checkout session "
                "is attached yet."
            ),
            "booking": booking,
        }

    result = _paymongo_request(
        "GET",
        (
            f"{PAYMONGO_RETRIEVE_CHECKOUT_URL}"
            f"/{session_id}"
        ),
        payment_method=str(
            booking.get(
                "payment_method_code",
                "",
            )
            or ""
        ),
    )

    session_data = result.get(
        "data",
        {},
    ) or {}

    state = _session_payment_state(
        session_data
    )

    service = _service()

    if state["paid"]:
        updated = _apply_payment(
            service,
            booking,
            session_data,
            state["payment"],
        )

        return {
            "synced": True,
            "state": "paid",
            "receipt_ready": True,
            "message": (
                "Payment confirmed. The booking "
                "history and receipt are ready."
            ),
            "booking": updated,
        }

    now = datetime.now(
        timezone.utc
    ).isoformat()

    paymongo_status = {
        "pending": "pending",
        "failed": "failed",
        "expired": "expired",
    }.get(
        state["state"],
        "pending",
    )

    service.table("bookings").update(
        {
            "paymongo_status": (
                paymongo_status
            ),
            "payment_message": (
                state["message"]
            ),
            "payment_last_checked_at": now,
            "updated_at": now,
        }
    ).eq(
        "id",
        booking_id,
    ).eq(
        "user_id",
        user_id,
    ).execute()

    _save_checkout_attempt(
        service,
        booking=booking,
        checkout_session_id=session_id,
        reference_number=(
            booking.get(
                "paymongo_reference_number"
            )
        ),
        payment_method_code=(
            state.get("method_code")
            or str(
                booking.get(
                    "payment_method_code",
                    "paymongo",
                )
            )
        ),
        payment_scope=str(
            (
                (
                    session_data.get(
                        "attributes",
                        {},
                    )
                    or {}
                ).get(
                    "metadata",
                    {},
                )
                or {}
            ).get(
                "payment_scope",
                "selected",
            )
        ),
        amount=_money(
            booking.get(
                "payment_due_amount"
            )
        ),
        status=paymongo_status,
        checkout_url=(
            booking.get(
                "paymongo_checkout_url"
            )
        ),
        raw_payload=result,
    )

    updated = _get_booking(
        service,
        booking_id,
        user_id,
    )

    return {
        "synced": False,
        "state": state["state"],
        "receipt_ready": False,
        "message": state["message"],
        "booking": updated,
    }


def _verify_paymongo_signature(
    raw_body: bytes,
    signature_header: str,
) -> None:
    if not PAYMONGO_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=500,
            detail=(
                "PAYMONGO_WEBHOOK_SECRET "
                "is not configured."
            ),
        )

    parts: dict[str, str] = {}

    for item in signature_header.split(","):
        if "=" not in item:
            continue

        key, value = item.split(
            "=",
            1,
        )
        parts[
            key.strip().lower()
        ] = value.strip()

    timestamp = parts.get("t", "")

    if not timestamp:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid PayMongo webhook signature."
            ),
        )

    signed_payload = (
        timestamp.encode("utf-8")
        + b"."
        + raw_body
    )

    expected = hmac.new(
        PAYMONGO_WEBHOOK_SECRET.encode(
            "utf-8"
        ),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    mode_signature = (
        parts.get("te")
        if _paymongo_mode() == "test"
        else parts.get("li")
    )

    if (
        not mode_signature
        or not hmac.compare_digest(
            mode_signature,
            expected,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid PayMongo webhook signature."
            ),
        )


@router.post("/paymongo/webhook")
async def paymongo_webhook(
    request: Request,
):
    raw_body = await request.body()

    signature_header = (
        request.headers.get(
            "Paymongo-Signature",
            "",
        )
        or request.headers.get(
            "paymongo-signature",
            "",
        )
        or request.headers.get(
            "X-Paymongo-Signature",
            "",
        )
        or request.headers.get(
            "x-paymongo-signature",
            "",
        )
    ).strip()

    _verify_paymongo_signature(
        raw_body,
        signature_header,
    )

    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook JSON.",
        ) from error

    event = payload.get(
        "data",
        {},
    ) or {}

    event_type = str(
        (
            event.get(
                "attributes",
                {},
            )
            or {}
        ).get(
            "type",
            event.get(
                "type",
                payload.get(
                    "type",
                    "",
                ),
            ),
        )
    )

    if (
        event_type
        != "checkout_session.payment.paid"
    ):
        return {
            "received": True,
            "ignored": True,
            "event_type": event_type,
        }

    session_data = (
        (
            event.get(
                "attributes",
                {},
            )
            or {}
        ).get(
            "data",
        )
        or event.get("data")
        or {}
    )

    session_attributes = (
        session_data.get(
            "attributes",
            {},
        )
        or {}
    )

    metadata = (
        session_attributes.get(
            "metadata",
            {},
        )
        or {}
    )

    booking_id = str(
        metadata.get(
            "booking_id",
            "",
        )
    ).strip()

    if not booking_id:
        return {
            "received": True,
            "ignored": True,
            "reason": (
                "No booking_id metadata."
            ),
        }

    if metadata.get("booking_channel") == "public":
        service = _service()
        draft = _public_checkout_draft(service, booking_id)
        if draft:
            _sync_public_checkout_draft(service, draft)
            return {"received": True}

    if metadata.get("booking_channel") == "manual":
        draft = _manual_checkout_draft(_service(), booking_id)
        if draft:
            sync_manual_checkout_payment(booking_id)
            return {"received": True}

    service = _service()
    event_hash = hashlib.sha256(
        raw_body
    ).hexdigest()

    existing = _first(
        service.table(
            "paymongo_webhook_events"
        )
        .select("id")
        .eq(
            "event_hash",
            event_hash,
        )
        .limit(1)
        .execute()
    )

    if existing:
        return {
            "received": True,
            "duplicate": True,
        }

    service.table(
        "paymongo_webhook_events"
    ).insert(
        {
            "event_hash": event_hash,
            "event_type": event_type,
            "payload": payload,
        }
    ).execute()

    booking = _get_booking(
        service,
        booking_id,
    )

    state = _session_payment_state(
        session_data
    )

    if not state["paid"]:
        _save_checkout_attempt(
            service,
            booking=booking,
            checkout_session_id=str(
                session_data.get("id") or ""
            ),
            reference_number=(
                session_attributes.get(
                    "reference_number"
                )
            ),
            payment_method_code=(
                state.get(
                    "method_code",
                    "paymongo",
                )
            ),
            payment_scope=str(
                metadata.get(
                    "payment_scope",
                    "selected",
                )
            ),
            amount=_money(
                booking.get(
                    "payment_due_amount"
                )
            ),
            status=state["state"],
            checkout_url=(
                session_attributes.get(
                    "checkout_url"
                )
            ),
            raw_payload=payload,
        )

        return {
            "received": True,
            "ignored": True,
            "reason": (
                "The checkout event did not "
                "contain a paid payment."
            ),
        }

    updated = _apply_payment(
        service,
        booking,
        session_data,
        state["payment"],
    )

    return {
        "received": True,
        "updated": True,
        "booking_id": updated["id"],
        "booking_status": (
            updated["booking_status"]
        ),
        "payment_status": (
            updated["payment_status"]
        ),
        "receipt_number": (
            updated.get("receipt_number")
        ),
    }


# =========================================================
# PUBLIC MODERN BOOKING FORM ENDPOINTS
# =========================================================
def validate_public_booking_phone(value: str) -> str:
    phone = str(value or "").strip()
    if not phone or not re.fullmatch(r"[0-9+\s().-]+", phone):
        raise ValueError(
            "Enter a Philippine mobile number using digits only; spaces, +, hyphens, and parentheses are allowed."
        )

    compact = re.sub(r"[\s().-]", "", phone)
    if not re.fullmatch(r"(?:\+?63)?9\d{9}|09\d{9}", compact):
        raise ValueError("Enter a valid Philippine mobile number, such as 09123456789.")
    return phone


class PublicBookingCreateRequest(BaseModel):
    _validate_names = field_validator('first_name', 'last_name')(validate_person_name)
    _validate_phone = field_validator('phone')(validate_public_booking_phone)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    email_verification_token: str = Field(min_length=32, max_length=512)
    phone: str = Field(min_length=10, max_length=20)
    villa_id: str = Field(min_length=1, max_length=50)
    villa_ids: list[str] | None = None
    check_in_date: date
    check_in_time: str = Field(min_length=1, max_length=20)
    guest_count: int = Field(ge=1, le=MAX_GUEST_COUNT)
    notes: str | None = Field(default=None, max_length=1000)
    payment_choice: Literal["half", "full"] = "half"
    payment_method: Literal[
        "gcash",
        "maya",
        "debit",
        "qrph",
    ] = "gcash"


class PublicEmailVerificationRequest(BaseModel):
    email: EmailStr


class PublicEmailVerificationConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


@public_router.post("/email-verification/request")
def request_public_email_verification(
    data: PublicEmailVerificationRequest,
    request: Request,
):
    if not _smtp_configured():
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable. Please contact The Villa.",
        )

    email = str(data.email).strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(timezone.utc)
    try:
        service = _service()
        result = service.rpc("issue_public_email_verification", {
            "p_email_hash": _public_email_verification_hash(email, "email"),
            "p_code_hash": _public_email_verification_hash(
                f"{email}:{code}", "code"
            ),
            "p_ip_hash": _public_email_verification_hash(client_ip, "ip"),
            "p_now": now.isoformat(),
            "p_expires_at": (now + timedelta(minutes=10)).isoformat(),
        }).execute()
    except Exception:
        logger.exception(
            "Public email verification issuance failed. Confirm the email-verification migration is applied."
        )
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable. The verification database may need setup; please contact The Villa.",
        ) from None
    state = _attr(result, "data", None)
    if state in {"cooldown", "email_rate_limited", "ip_rate_limited"}:
        raise HTTPException(
            status_code=429,
            detail="A verification code could not be sent right now. If you recently requested one, check your inbox or wait before trying again.",
        )
    if state != "sent":
        logger.error("Public email verification issuance returned an unexpected result.")
        raise HTTPException(
            status_code=503,
            detail="The verification code could not be sent. Please try again.",
        )

    message = EmailMessage()
    message["Subject"] = "Verify your email | The Villa"
    message["From"] = (
        f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
        if SMTP_FROM
        else SMTP_FROM_NAME
    )
    if os.getenv("RESEND_API_KEY", "").strip():
        message.replace_header(
            "From",
            os.getenv("RESEND_FROM", "").strip(),
        )
    message["To"] = email
    message.set_content(
        f"""Hello,

Your The Villa booking verification code is {code}.

Enter this code in the booking form within 10 minutes. If you did not request it, you can ignore this email.

The Villa"""
    )
    try:
        _send_email_message(message)
    except Exception as error:
        logger.warning(
            "Public email verification delivery failed (%s).",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="We couldn't send the verification email. Check the address or try again later.",
        ) from None

    return {
        "sent": True,
        "message": "A verification code was sent. Check your inbox and spam folder.",
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }


@public_router.post("/email-verification/confirm")
def confirm_public_email_verification(data: PublicEmailVerificationConfirmRequest):
    email = str(data.email).strip().lower()
    now = datetime.now(timezone.utc)
    try:
        service = _service()
        result = service.rpc("verify_public_email_verification", {
            "p_email_hash": _public_email_verification_hash(email, "email"),
            "p_code_hash": _public_email_verification_hash(
                f"{email}:{data.code}", "code"
            ),
            "p_now": now.isoformat(),
        }).execute()
    except Exception:
        logger.exception(
            "Public email verification confirmation RPC failed. Confirm the email-verification migration is applied."
        )
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable. The verification database may need setup; please contact The Villa.",
        ) from None
    state = _attr(result, "data", None)
    if state == "locked":
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect codes were entered. Request a new code.",
        )
    if state == "expired":
        raise HTTPException(
            status_code=410,
            detail="This verification code expired. Request a new code.",
        )
    if state == "verified":
        email_hash = _public_email_verification_hash(email, "email")
        try:
            record = _first(
                service.table("public_email_verifications")
                .select("verified_at,expires_at")
                .eq("email_hash", email_hash)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "Could not load a confirmed public email verification record."
            )
            raise HTTPException(
                status_code=503,
                detail="Email verification could not be completed. Please try again.",
            ) from None
        if record and record.get("verified_at"):
            expires_at = datetime.fromisoformat(
                str(record["expires_at"]).replace("Z", "+00:00")
            )
            if expires_at > now:
                return {
                    "verified": True,
                    "email_verification_token": _create_public_email_verification_token(
                        email, expires_at
                    ),
                    "message": "Email address verified.",
                }
        logger.error("Verified email record was missing or expired after code confirmation.")
        raise HTTPException(
            status_code=503,
            detail="Email verification could not be completed. Request a new code.",
        )
    raise HTTPException(
        status_code=422,
        detail="That code could not be verified. Request a new code and try again.",
    )


class PublicCheckoutRequest(BaseModel):
    payment_method: Literal[
        "gcash",
        "maya",
        "debit",
        "qrph",
    ] = "gcash"
    payment_scope: Literal["selected", "balance"] = "selected"


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", validate_public_booking_phone(value))

    if len(digits) == 10 and digits.startswith("9"):
        return f"+63{digits}"

    if len(digits) == 11 and digits.startswith("09"):
        return f"+63{digits[1:]}"

    if len(digits) == 12 and digits.startswith("639"):
        return f"+{digits}"

    raise HTTPException(
        status_code=422,
        detail=(
            "Enter a valid Philippine mobile number, "
            "for example 09123456789."
        ),
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_public_booking(record):
    return {key:value for key,value in record.items() if key not in {"guest_access_token_hash","feedback_token_hash","feedback_token_expires_at","feedback_token_revoked_at"}}


def _require_booking_token(
    booking_id: str,
    raw_token: str | None,
) -> dict[str, Any]:
    token = str(raw_token or "").strip()

    if len(token) < 32:
        raise HTTPException(
            status_code=401,
            detail="The secure booking token is missing or invalid.",
        )

    booking = _first(
        _service()
        .table("bookings")
        .select("*")
        .eq("id", booking_id)
        .eq("guest_access_token_hash", _token_hash(token))
        .limit(1)
        .execute()
    )

    if not booking:
        draft = _public_checkout_draft(_service(), booking_id)
        payload = draft["booking_payload"] if draft else {}
        if hmac.compare_digest(str(payload.get("guest_access_token_hash") or ""), _token_hash(token)):
            booking = payload
    if not booking:
        raise HTTPException(status_code=403, detail="The secure booking token does not match this reservation.")

    return booking


def _public_checkout_urls(booking_id: str) -> tuple[str, str]:
    # Combined deployments must return to the same origin that stored the
    # guest token. A leftover localhost/custom FRONTEND_URL loses that token.
    origin = FRONTEND_URL
    if os.getenv("FRONTEND_DIST", "").strip():
        origin = (os.getenv("RENDER_EXTERNAL_URL", "").strip() or BACKEND_PUBLIC_URL or FRONTEND_URL).rstrip("/")
    return (
        f"{origin}/book?payment=success&booking={booking_id}",
        f"{origin}/book?payment=cancelled&booking={booking_id}",
    )


@public_router.get("/availability")
def public_booking_availability(
    check_in_date: date,
    guest_count: int = 1,
):
    if check_in_date < date.today():
        raise HTTPException(
            status_code=422,
            detail="Choose today or a future booking date.",
        )

    if guest_count < 1 or guest_count > MAX_GUEST_COUNT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Guest count must be between 1 and {MAX_GUEST_COUNT}."
            ),
        )

    service = _service()
    _expire_stale_public_booking_holds(service)
    catalog = get_villa_catalog_map(service)

    existing_response = (
        service.table("bookings")
        .select(
            """
            villa_id,
            villa_ids,
            check_in_date,
            check_out_date,
            booking_status
            """
        )
        .execute()
    )

    requested_checkout = (
        check_in_date
        + timedelta(days=1)
    )

    blocked_villas = set()

    for row in _attr(existing_response, "data", []) or []:
        if _villa_date_conflict(
            row,
            check_in_date,
            requested_checkout,
        ):
            blocked_villas.update(row.get("villa_ids") or [str(row.get("villa_id"))])

    for stay in _active_airbnb_stays(service, check_in_date, requested_checkout):
        if _villa_date_conflict(
            {
                "villa_ids": stay.get("villa_ids") or [],
                "check_in_date": stay.get("check_in_date"),
                "check_out_date": stay.get("check_out_date"),
                "booking_status": "Confirmed",
            },
            check_in_date,
            requested_checkout,
        ):
            blocked_villas.update(stay.get("villa_ids") or [])

    villas: list[dict[str, Any]] = []

    for villa_id, villa in catalog.items():
        operational = _villa_operational(villa, check_in_date)
        within_capacity = True
        available = (
            operational
            and within_capacity
            and villa_id not in blocked_villas
        )

        villas.append(
            {
                "villa_id": villa_id,
                "villa_name": villa["name"],
                "capacity": villa["capacity"],
                "image": villa["image"],
                "price": float(villa["price"]),
                "available": available,
                "reason": (
                    "Available"
                    if available
                    else (
                        "Under Maintenance"
                        if not operational
                        else (
                            "Booked"
                            if villa_id in blocked_villas
                            else "Too Small"
                        )
                    )
                ),
            }
        )

    return {
        "check_in_date": check_in_date.isoformat(),
        "guest_count": guest_count,
        "villas": villas,
        "available_villa_ids": [
            villa["villa_id"]
            for villa in villas
            if villa["available"]
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@public_router.get("/calendar-availability")
def public_booking_calendar_availability(
    start_date: date,
    end_date: date,
    guest_count: int = 1,
):
    if guest_count < 1 or guest_count > MAX_GUEST_COUNT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Guest count must be between 1 and {MAX_GUEST_COUNT}."
            ),
        )

    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="The calendar end date must be after the start date.",
        )

    if (end_date - start_date).days > 62:
        raise HTTPException(
            status_code=422,
            detail="Calendar availability can be requested for up to 63 days.",
        )

    service = _service()
    _expire_stale_public_booking_holds(service)
    catalog = get_villa_catalog_map(service)

    response = (
        service.table("bookings")
        .select(
            """
            villa_id,
            villa_ids,
            check_in_date,
            check_out_date,
            booking_status
            """
        )
        .execute()
    )

    blocked_by_date: dict[str, set[str]] = {}
    airbnb_blocked_by_date: dict[str, set[str]] = {}

    for row in _attr(response, "data", []) or []:
        if not _availability_blocks_booking(row):
            continue

        row_villa_ids = row.get("villa_ids") or [str(row.get("villa_id") or "")]

        if not any(row_villa_ids):
            continue

        current_day = start_date
        while current_day <= end_date:
            if _villa_date_conflict(
                row,
                current_day,
                current_day + timedelta(days=1),
            ):
                blocked_by_date.setdefault(
                    current_day.isoformat(),
                    set(),
                ).update(row_villa_ids)

            current_day += timedelta(days=1)

    for stay in _active_airbnb_stays(service, start_date, end_date + timedelta(days=1)):
        stay_row = {
            "villa_ids": stay.get("villa_ids") or [],
            "check_in_date": stay.get("check_in_date"),
            "check_out_date": stay.get("check_out_date"),
            "booking_status": "Confirmed",
        }
        current_day = start_date
        while current_day <= end_date:
            if _villa_date_conflict(
                stay_row,
                current_day,
                current_day + timedelta(days=1),
            ):
                airbnb_blocked_by_date.setdefault(
                    current_day.isoformat(),
                    set(),
                ).update(stay.get("villa_ids") or [])
                blocked_by_date.setdefault(
                    current_day.isoformat(),
                    set(),
                ).update(stay.get("villa_ids") or [])
            current_day += timedelta(days=1)

    days: dict[str, dict[str, Any]] = {}
    current = start_date

    while current <= end_date:
        date_key = current.isoformat()
        blocked = blocked_by_date.get(date_key, set())
        airbnb_blocked = airbnb_blocked_by_date.get(date_key, set())
        available_ids: list[str] = []
        booked_ids: list[str] = []
        unavailable_ids: list[str] = []

        for villa_id, villa in catalog.items():
            if not _villa_operational(villa, current):
                unavailable_ids.append(villa_id)
            elif villa_id in blocked:
                booked_ids.append(villa_id)
            else:
                available_ids.append(villa_id)

        days[date_key] = {
            "total_available_capacity": sum(int(catalog[vid]["capacity"]) for vid in available_ids),
            "available_count": len(available_ids),
            "available_villa_ids": available_ids,
            "booked_villa_ids": booked_ids,
            "airbnb_blocked_villa_ids": sorted(airbnb_blocked),
            "unavailable_villa_ids": unavailable_ids,
        }

        current += timedelta(days=1)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "guest_count": guest_count,
        "days": days,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@public_router.post("")
def create_public_booking(data: PublicBookingCreateRequest):
    _require_verified_public_email(
        _service(),
        str(data.email),
        data.email_verification_token,
    )
    creation = _prepare_public_booking(data, draft_only=True)
    booking = creation["booking"]
    _service().table("public_booking_checkouts").insert({
        "id": booking["id"], "booking_payload": booking,
        "expires_at": booking["hold_expires_at"],
    }).execute()
    return {
        "message": "Checkout prepared. Your booking is saved only after verified payment.",
        "booking": _safe_public_booking(booking),
        "booking_access_token": creation["booking_access_token"],
    }


def _prepare_public_booking(data: PublicBookingCreateRequest, *, draft_only: bool = False):
    service = _service()
    _expire_stale_public_booking_holds(service)
    catalog = get_villa_catalog_map(service)
    chosen_ids = data.villa_ids or [data.villa_id]
    if not chosen_ids or len(chosen_ids) != len(set(chosen_ids)) or len(chosen_ids) > len(catalog):
        raise HTTPException(status_code=422, detail="Select distinct villas.")
    if data.villa_id != chosen_ids[0]:
        raise HTTPException(status_code=422, detail="Primary villa must be the first selected villa.")
    chosen_villas = [catalog.get(villa_id) for villa_id in chosen_ids]
    if any(v is None for v in chosen_villas):
        raise HTTPException(status_code=422, detail="A selected villa does not exist.")
    villa = chosen_villas[0]

    if not villa:
        raise HTTPException(
            status_code=422,
            detail="The selected villa does not exist.",
        )

    if data.check_in_date < date.today():
        raise HTTPException(
            status_code=422,
            detail="Choose today or a future booking date.",
        )

    if data.check_in_time not in ALLOWED_CHECK_IN_TIMES:
        raise HTTPException(
            status_code=422,
            detail="Choose one of the available check-in times.",
        )

    if data.guest_count > sum(int(v["capacity"]) for v in chosen_villas):
        raise HTTPException(status_code=422, detail="The selected villas cannot accommodate all guests.")

    if not all(_villa_operational(v, data.check_in_date) for v in chosen_villas):
        raise HTTPException(
            status_code=409,
            detail=f"{villa['name']} is currently under maintenance.",
        )

    requested_check_out = (
        data.check_in_date
        + timedelta(days=1)
    )

    existing_response = (
        service.table("bookings")
        .select(
            """
            id,
            villa_id,
            villa_ids,
            check_in_date,
            check_out_date,
            booking_status
            """
        )
        .execute()
    )


    # Require the fewest villas needed for the actual guest count and open
    # properties. An 8-person villa fits 5 guests alone; 9 guests require more.
    reserved_ids = set()
    for row in _attr(existing_response, "data", []) or []:
        if _villa_date_conflict(row, data.check_in_date, requested_check_out):
            reserved_ids.update(row.get("villa_ids") or [row.get("villa_id")])
    for stay in _active_airbnb_stays(service, data.check_in_date, requested_check_out):
        if _villa_date_conflict(
            {
                "villa_ids": stay.get("villa_ids") or [],
                "check_in_date": stay.get("check_in_date"),
                "check_out_date": stay.get("check_out_date"),
                "booking_status": "Confirmed",
            },
            data.check_in_date,
            requested_check_out,
        ):
            reserved_ids.update(stay.get("villa_ids") or [])
    available_capacities = sorted(
        (int(item["capacity"]) for villa_id, item in catalog.items()
         if _villa_operational(item, data.check_in_date) and villa_id not in reserved_ids),
        reverse=True,
    )
    minimal_count = None
    accumulated_capacity = 0
    for index, size in enumerate(available_capacities, 1):
        accumulated_capacity += size
        if accumulated_capacity >= data.guest_count:
            minimal_count = index
            break
    if minimal_count is None:
        raise HTTPException(status_code=409, detail="Not enough villa capacity is available for this date.")
    if len(chosen_ids) != minimal_count:
        raise HTTPException(status_code=422, detail=f"Choose exactly {minimal_count} villa(s) for {data.guest_count} guests.")

    for row in _attr(existing_response, "data", []) or []:
        if set(row.get("villa_ids") or [row.get("villa_id")]) & set(chosen_ids) and _villa_date_conflict(
            row,
            data.check_in_date,
            requested_check_out,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This villa is already reserved "
                    "for the selected dates."
                ),
            )

    for stay in _active_airbnb_stays(service, data.check_in_date, requested_check_out):
        if set(stay.get("villa_ids") or []) & set(chosen_ids) and _villa_date_conflict(
            {
                "villa_ids": stay.get("villa_ids") or [],
                "check_in_date": stay.get("check_in_date"),
                "check_out_date": stay.get("check_out_date"),
                "booking_status": "Confirmed",
            },
            data.check_in_date,
            requested_check_out,
        ):
            raise HTTPException(
                status_code=409,
                detail="This villa is on hold for an Airbnb stay on the selected dates.",
            )

    total_amount = sum((_money(v["price"]) for v in chosen_villas), Decimal("0"))
    selected_due = (
        total_amount
        if data.payment_choice == "full"
        else (total_amount * Decimal("0.50")).quantize(Decimal("0.01"))
    )

    customer_name = " ".join(
        part.strip()
        for part in [data.first_name, data.last_name]
        if part.strip()
    )
    customer_phone = _normalize_phone(data.phone)
    check_out_date = data.check_in_date + timedelta(days=1)

    raw_token = secrets.token_urlsafe(36)
    feedback_token = secrets.token_urlsafe(36)
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    hold_expires_at = (
        now_dt + timedelta(minutes=PUBLIC_BOOKING_HOLD_MINUTES)
    ).isoformat()

    row = {
        "booking_code": _new_booking_code(),
        "user_id": None,
        "customer_name": customer_name,
        "customer_email": str(data.email).strip().lower(),
        "customer_phone": customer_phone,
        "villa_id": data.villa_id,
        "villa_ids": chosen_ids,
        "villa_name": ", ".join(v["name"] for v in chosen_villas),
        "villa_image": villa["image"],
        "check_in_date": data.check_in_date.isoformat(),
        "check_out_date": check_out_date.isoformat(),
        "check_in_time": data.check_in_time,
        "guest_count": data.guest_count,
        "nights": 1,
        "notes": data.notes.strip() if data.notes else None,
        "total_amount": float(total_amount),
        "payment_choice": data.payment_choice,
        "payment_method": PAYMONGO_METHOD_DETAILS[data.payment_method]["label"],
        "payment_method_code": data.payment_method,
        "payment_environment": _paymongo_mode(),
        "payment_due_amount": float(selected_due),
        "amount_paid": 0,
        "balance_amount": float(total_amount),
        "booking_status": "Pending Payment",
        "stay_status": "Not Checked In",
        "payment_status": "Unpaid",
        "payment_message": (
            "Reservation saved. Secure payment has not been completed yet."
        ),
        "payment_last_checked_at": None,
        "paymongo_status": "not_started",
        "guest_booking": True,
        "guest_access_token_hash": _token_hash(raw_token),
        "feedback_token_hash": _token_hash(feedback_token),
        "hold_expires_at": hold_expires_at,
        "created_at": now,
        "updated_at": now,
    }

    if draft_only:
        row["id"] = str(uuid.uuid4())
        return {"booking": row, "booking_access_token": raw_token}

    try:
        response = service.table("bookings").insert(row).execute()
    except Exception as error:
        message = str(error).lower()

        if (
            "bookings_active_villa_date_unique" in message
            or "duplicate key" in message
            or "already booked" in message
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This villa was just booked for the selected date. "
                    "Choose another available villa."
                ),
            ) from error

        raise HTTPException(
            status_code=400,
            detail=(
                "The booking could not be stored. Run the public guest "
                "booking migration and confirm the Supabase service-role key."
            ),
        ) from error

    booking = _first(response)

    if not booking:
        raise HTTPException(
            status_code=500,
            detail="The booking could not be returned.",
        )

    # Send the booking acknowledgement only after Supabase has
    # successfully stored the reservation. Email failure does not
    # cancel or roll back the reservation.
    email_sent = _send_booking_confirmation_email(
        booking,
        feedback_token,
    )

    safe_booking = {
        key: value
        for key, value in booking.items()
        if key not in {"guest_access_token_hash", "feedback_token_hash", "feedback_token_expires_at", "feedback_token_revoked_at"}
    }

    return {
        "message": "Booking saved. Continue to secure PayMongo checkout.",
        "booking": safe_booking,
        "booking_access_token": raw_token,
        "email_sent": email_sent,
        "email_message": (
            "Booking confirmation email sent."
            if email_sent
            else (
                "Booking saved, but the confirmation email could not "
                "be sent. Check the backend SMTP configuration."
            )
        ),
    }


class GuestFeedbackRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    overall_rating: int = Field(ge=1, le=5)
    cleanliness_rating: int | None = Field(default=None, ge=1, le=5)
    service_rating: int | None = Field(default=None, ge=1, le=5)
    villa_rating: int | None = Field(default=None, ge=1, le=5)
    value_rating: int | None = Field(default=None, ge=1, le=5)
    would_recommend: bool | None = None
    comments: str = Field(min_length=20, max_length=3000)
    hide_identity: bool = False

    @field_validator("comments")
    @classmethod
    def validate_written_feedback(cls, value):
        from feedback_policy import meaningful_comments
        return meaningful_comments(value)
    private_note: str | None = Field(default=None, max_length=3000)


def _require_feedback_booking(
    booking_id: str,
    token: str,
) -> dict[str, Any]:
    if not token or len(token) < 20:
        raise HTTPException(
            status_code=401,
            detail="The feedback link is invalid or incomplete.",
        )

    service = _service()
    result = (
        service.table("bookings")
        .select("*")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    )
    booking = _first(result)

    if not booking:
        raise HTTPException(
            status_code=404,
            detail="The reservation could not be found.",
        )

    expected_hash = str(
        booking.get("feedback_token_hash") or ""
    ).strip()

    if not expected_hash or not hmac.compare_digest(
        expected_hash,
        _token_hash(token),
    ):
        raise HTTPException(
            status_code=401,
            detail="The feedback link is invalid or expired.",
        )

    expiry = booking.get("feedback_token_expires_at")
    if booking.get("feedback_token_revoked_at") or not expiry:
        raise HTTPException(status_code=410, detail="This feedback link was revoked or has expired. Contact The Villa for assistance.")
    try:
        expired = datetime.fromisoformat(str(expiry).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        expired = True
    if expired:
        raise HTTPException(status_code=410, detail="This feedback link has expired. Contact The Villa for assistance.")
    from feedback_service import booking_eligible
    try:
        eligible = booking_eligible(service, booking)
    except Exception:
        raise HTTPException(status_code=503, detail="Feedback eligibility could not be verified. Please try again later.")
    if not eligible:
        raise HTTPException(status_code=403, detail="Feedback is available only after checkout and verified full payment. Cancelled or refunded stays are not eligible.")

    return booking


def _limit_feedback_request(request: Request, booking_id: str):
    key = hmac.new(SUPABASE_SERVICE_ROLE_KEY.encode(), f"feedback:{request.method}:{request.client.host if request.client else 'unknown'}".encode(), hashlib.sha256).hexdigest()
    try:
        allowed = _service().rpc("allow_guest_feedback_request", {"p_key":key, "p_max":12 if request.method == "POST" else 60}).execute().data
    except Exception:
        raise HTTPException(status_code=503, detail="Feedback is temporarily unavailable. Please try again later.")
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many feedback requests. Please wait 10 minutes before trying again.")


@public_router.get("/feedback/reviews")
def get_public_guest_reviews():
    from feedback_analysis import AnalysisFilters, records_for
    from public_feedback import public_reviews
    try:
        return JSONResponse({"data":public_reviews(records_for(_service(),AnalysisFilters()))}, headers={"Cache-Control":"no-store, max-age=0"})
    except Exception:
        logger.warning("Public guest reviews could not be loaded.")
        raise HTTPException(status_code=503,detail="Guest reviews are temporarily unavailable.") from None


@public_router.get("/feedback/summary")
def get_public_feedback_summary():
    try:
        response = _service().rpc(
            "list_verified_guest_feedback",
            {},
        ).execute()
        feedback_rows = getattr(response, "data", None) or []
        ratings = []
        for row in feedback_rows:
            if not isinstance(row, dict):
                continue
            try:
                rating = int(row.get("overall_rating"))
            except (TypeError, ValueError):
                continue
            if 1 <= rating <= 5:
                ratings.append(rating)

        count = len(ratings)
        distribution = {
            str(rating): ratings.count(rating)
            for rating in range(1, 6)
        }
        return {
            "data": {
                "count": count,
                "average": round(sum(ratings) / count, 1) if count else None,
                "distribution": distribution,
            }
        }
    except Exception as error:
        logger.exception("Could not load public guest rating summary.")
        raise HTTPException(
            status_code=503,
            detail="Guest ratings are temporarily unavailable.",
        ) from error


@public_router.get("/{booking_id}/feedback")
def get_guest_feedback_form(
    booking_id: UUID,
    request: Request,
    x_feedback_token: str | None = Header(default=None, alias="X-Feedback-Token"),
):
    booking_id = str(booking_id)
    booking = _require_feedback_booking(booking_id, x_feedback_token or "")
    try:
        existing = _first(_service().table("guest_feedback").select("id").eq("booking_id", booking_id).limit(1).execute())
    except Exception:
        raise HTTPException(status_code=503, detail="The feedback form could not be loaded. Please try again later.")
    return {"submitted":bool(existing), "booking": {
        "villa_name":booking.get("villa_name"),
        "check_in_date":booking.get("check_in_date"),
        "check_out_date":booking.get("check_out_date"),
    }}


@public_router.post("/{booking_id}/feedback")
def submit_guest_feedback(booking_id: UUID, data: GuestFeedbackRequest, request: Request):
    booking_id = str(booking_id)
    _require_feedback_booking(booking_id, data.token)
    values = data.model_dump(exclude={"token"})
    try:
        result = _service().rpc("submit_verified_guest_feedback", {
            "p_booking_id":booking_id, "p_token_hash":_token_hash(data.token), "p_feedback":values,
        }).execute().data
    except Exception:
        # The RPC validates the token and eligibility again while holding a row lock.
        raise HTTPException(status_code=409, detail="Feedback could not be saved. The link or booking may have changed. Refresh the form and try again.")
    if not isinstance(result, dict) or not result.get("submitted"):
        raise HTTPException(status_code=503, detail="Your feedback could not be saved. Please try again.")
    # A pilot failure never loses a verified feedback submission. Do not
    # retrain on incoming predictions or add them to the seed dataset silently.
    if not result.get("duplicate"):
        try:
            saved = _first(_service().table("guest_feedback").select("id,comments,overall_rating,cleanliness_rating,service_rating,villa_rating,value_rating,guest_name,guest_email,booking_code").eq("booking_id",booking_id).limit(1).execute())
            if saved:
                from ml.inference import save_pilot_prediction
                save_pilot_prediction(_service(),saved)
        except Exception:
            logger.warning("Feedback was saved; pilot analysis could not be completed.")
    return {"submitted":True, "message":"Thank you. Your feedback has already been received." if result.get("duplicate") else "Thank you for sharing your experience with The Villa."}


@public_router.post("/{booking_id}/checkout")
def create_public_booking_checkout(
    booking_id: str,
    data: PublicCheckoutRequest,
    x_booking_token: str | None = Header(default=None, alias="X-Booking-Token"),
):
    # Public guest checkouts always go back to BookForm, never to admin.
    booking = _require_booking_token(booking_id, x_booking_token)
    draft = _public_checkout_draft(_service(), booking_id)
    if draft:
        if datetime.fromisoformat(draft["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="This checkout has expired. Please start again.")
        if booking.get("paymongo_checkout_url"):
            return {"checkout_url": booking["paymongo_checkout_url"]}
    result = _create_public_booking_checkout(
        booking_id, data, x_booking_token=x_booking_token,
        draft_booking=booking if draft else None,
    )
    if draft:
        _service().table("public_booking_checkouts").update({
            "booking_payload": booking,
            "paymongo_checkout_session_id": booking.get(
                "paymongo_checkout_session_id"
            ),
            "next_check_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", booking_id).execute()
    return result


def _create_public_booking_checkout(
    booking_id: str,
    data: PublicCheckoutRequest,
    *,
    x_booking_token: str | None,
    manual_return_base_url: str | None = None,
    draft_booking: dict[str, Any] | None = None,
):
    # Only the authenticated admin endpoint supplies manual_return_base_url.
    booking = draft_booking or _require_booking_token(booking_id, x_booking_token)
    service = _service()
    if draft_booking is None:
        booking = _reconcile_booking_payment_state(service, booking)

    if str(booking.get("booking_status", "")).lower() in {
        "cancelled",
        "completed",
        "expired",
    }:
        raise HTTPException(
            status_code=409,
            detail="This booking cannot accept another payment.",
        )

    method_details = PAYMONGO_METHOD_DETAILS[data.payment_method]
    total_amount = _money(booking.get("total_amount"))
    amount_paid = _money(booking.get("amount_paid"))
    balance_amount = max(Decimal("0.00"), total_amount - amount_paid)

    if balance_amount <= 0:
        raise HTTPException(
            status_code=409,
            detail="This booking is already fully paid.",
        )

    payment_choice = str(booking.get("payment_choice", "half")).lower()
    initial_target = (
        total_amount
        if payment_choice == "full"
        else (total_amount * Decimal("0.50")).quantize(Decimal("0.01"))
    )

    if data.payment_scope == "balance":
        amount_to_pay = balance_amount
        line_item_name = f"{booking['villa_name']} remaining balance"
        payment_scope = "balance"
    else:
        amount_to_pay = max(
            Decimal("0.00"),
            min(balance_amount, initial_target - amount_paid),
        )

        if amount_to_pay <= 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The required initial payment is already complete. "
                    "Choose the remaining balance instead."
                ),
            )

        line_item_name = (
            f"{booking['villa_name']} "
            + (
                "full payment"
                if payment_choice == "full"
                else "50% downpayment"
            )
        )
        payment_scope = "selected"

    success_url, cancel_url = (
        _manual_checkout_urls(booking_id, manual_return_base_url)
        if manual_return_base_url
        else _public_checkout_urls(booking_id)
    )
    attempt_nonce = uuid.uuid4().hex[:10].upper()
    reference = (
        f"{booking['booking_code']}-{payment_scope.upper()}-{attempt_nonce}"
    )[:255]

    billing: dict[str, Any] = {}

    if booking.get("customer_name"):
        billing["name"] = booking["customer_name"]
    if booking.get("customer_email"):
        billing["email"] = booking["customer_email"]
    if booking.get("customer_phone"):
        billing["phone"] = booking["customer_phone"]

    attributes: dict[str, Any] = {
        "line_items": [
            {
                "name": line_item_name,
                "description": (
                    f"The Villa reservation {booking['booking_code']}"
                ),
                "amount": _centavos(amount_to_pay),
                "currency": "PHP",
                "quantity": 1,
            }
        ],
        "payment_method_types": PAYMONGO_METHOD_MAP[data.payment_method],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "reference_number": reference,
        "show_description": True,
        "show_line_items": True,
        "send_email_receipt": bool(booking.get("customer_email")),
        "metadata": {
            "booking_id": str(booking["id"]),
            "booking_code": str(booking["booking_code"]),
            "guest_booking": "true",
            "booking_channel": "manual" if manual_return_base_url else "public",
            "payment_scope": payment_scope,
            "payment_method": data.payment_method,
            "payment_environment": _paymongo_mode(),
            "attempt_nonce": attempt_nonce,
        },
    }

    if billing:
        attributes["billing"] = billing

    result = _paymongo_request(
        "POST",
        PAYMONGO_CREATE_CHECKOUT_URL,
        payload={"data": {"attributes": attributes}},
        idempotency_key=(
            f"public-booking-{booking_id}-{payment_scope}-"
            f"{data.payment_method}-{_centavos(amount_to_pay)}-{attempt_nonce}"
        ),
        payment_method=data.payment_method,
    )

    checkout = result.get("data", {})
    checkout_attributes = checkout.get("attributes", {}) or {}
    checkout_url = checkout_attributes.get("checkout_url")
    checkout_session_id = str(checkout.get("id") or "").strip()

    if not checkout_url or not checkout_session_id:
        raise HTTPException(
            status_code=502,
            detail=(
                "PayMongo did not return a complete "
                f"{method_details['label']} checkout."
            ),
        )

    now = datetime.now(timezone.utc).isoformat()

    checkout_update = {
            "payment_method": method_details["label"],
            "payment_method_code": data.payment_method,
            "payment_environment": _paymongo_mode(),
            "payment_due_amount": float(amount_to_pay),
            "payment_message": (
                f"{method_details['label']} checkout created. "
                "Waiting for payment confirmation."
            ),
            "payment_last_checked_at": now,
            "paymongo_checkout_session_id": checkout_session_id,
            "paymongo_checkout_url": checkout_url,
            "paymongo_reference_number": reference,
            "paymongo_status": "checkout_created",
            "updated_at": now,
        }
    if draft_booking is not None:
        booking.update(checkout_update)
    else:
        service.table("bookings").update(
            checkout_update
        ).eq("id", booking_id).execute()
    
        _save_checkout_attempt(
            service,
            booking=booking,
            checkout_session_id=checkout_session_id,
            reference_number=reference,
            payment_method_code=data.payment_method,
            payment_scope=payment_scope,
            amount=amount_to_pay,
            status="checkout_created",
            checkout_url=checkout_url,
            raw_payload=result,
        )

    return {
        "message": f"Secure {method_details['label']} checkout is ready.",
        "booking_id": booking_id,
        "booking_code": booking["booking_code"],
        "amount": float(amount_to_pay),
        "payment_scope": payment_scope,
        "payment_method": data.payment_method,
        "payment_method_label": method_details["label"],
        "flow_type": method_details["flow_type"],
        "environment": _paymongo_mode(),
        "sandbox": _paymongo_mode() == "test",
        "receipt_ready": False,
        "checkout_session_id": checkout_session_id,
        "checkout_url": checkout_url,
    }


@public_router.post("/{booking_id}/cancel")
def cancel_public_booking(
    booking_id: str,
    x_booking_token: str | None = Header(default=None, alias="X-Booking-Token"),
):
    booking = _require_booking_token(booking_id, x_booking_token)
    service = _service()
    draft = _public_checkout_draft(service, booking_id)
    if draft:
        result = _sync_public_checkout_draft(service, draft)
        if result["state"] == "paid":
            raise HTTPException(status_code=409, detail="Payment was confirmed. Your booking is saved; please contact The Villa to cancel.")
        booking = result["booking"]
        booking.update(booking_status="Cancelled", paymongo_status="cancelled")
        service.table("public_booking_checkouts").update({"booking_payload": booking}).eq("id", booking_id).execute()
        return {"cancelled": True, "message": "Payment cancelled. No booking was saved.", "booking": None}
    booking = _reconcile_booking_payment_state(service, booking)

    if _booking_is_fully_paid(booking) or _money(booking.get("amount_paid")) > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This reservation already has a confirmed payment and cannot "
                "be released automatically. Please contact The Villa."
            ),
        )

    current_status = _normalized_status(booking.get("booking_status"))

    if current_status in AVAILABILITY_RELEASE_STATUSES:
        return {
            "cancelled": True,
            "message": "This reservation is already released.",
            "booking": _safe_public_booking(booking),
        }

    now = datetime.now(timezone.utc).isoformat()

    service.table("bookings").update(
        {
            "booking_status": "Cancelled",
            "paymongo_status": "cancelled",
            "payment_message": "Payment was cancelled and the reservation was released.",
            "hold_expires_at": None,
            "updated_at": now,
        }
    ).eq("id", booking_id).execute()

    updated = _first(
        service.table("bookings")
        .select("*")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    ) or booking

    return {
        "cancelled": True,
        "message": "Payment was cancelled and the selected date is available again.",
        "booking": _safe_public_booking(updated),
    }


@public_router.post("/{booking_id}/sync-payment")
def sync_public_booking_payment(
    booking_id: str,
    x_booking_token: str | None = Header(default=None, alias="X-Booking-Token"),
):
    booking = _require_booking_token(booking_id, x_booking_token)
    service = _service()
    draft = _public_checkout_draft(service, booking_id)
    if draft:
        result = _sync_public_checkout_draft(service, draft)
        return {**result, "synced": result["state"] == "paid",
                "receipt_ready": bool(result["booking"].get("receipt_number")),
                "booking": _safe_public_booking(result["booking"])}
    booking = _reconcile_booking_payment_state(service, booking)

    if _booking_is_fully_paid(booking):
        return {
            "synced": True,
            "state": "paid",
            "receipt_ready": bool(booking.get("receipt_number")),
            "message": "Payment is fully settled and the booking is confirmed.",
            "booking": _safe_public_booking(booking),
        }

    session_id = str(
        booking.get("paymongo_checkout_session_id") or ""
    ).strip()

    if not session_id:
        return {
            "synced": False,
            "state": "not_started",
            "receipt_ready": False,
            "message": "No PayMongo checkout session is attached yet.",
            "booking": _safe_public_booking(booking),
        }

    result = _paymongo_request(
        "GET",
        f"{PAYMONGO_RETRIEVE_CHECKOUT_URL}/{session_id}",
        payment_method=str(booking.get("payment_method_code") or ""),
    )

    session_data = result.get("data", {}) or {}
    state = _session_payment_state(session_data)

    if state["paid"]:
        updated = _apply_payment(
            service,
            booking,
            session_data,
            state["payment"],
        )

        return {
            "synced": True,
            "state": "paid",
            "receipt_ready": True,
            "message": (
                "Payment confirmed. Your booking reference and receipt are ready."
            ),
            "booking": _safe_public_booking(updated),
        }

    now = datetime.now(timezone.utc).isoformat()
    paymongo_status = {
        "pending": "pending",
        "failed": "failed",
        "expired": "expired",
    }.get(state["state"], "pending")

    booking_updates = {
        "paymongo_status": paymongo_status,
        "payment_message": state["message"],
        "payment_last_checked_at": now,
        "updated_at": now,
    }

    if state["state"] == "expired":
        booking_updates.update(
            {
                "booking_status": "Expired",
                "hold_expires_at": None,
            }
        )

    service.table("bookings").update(
        booking_updates
    ).eq("id", booking_id).execute()

    _save_checkout_attempt(
        service,
        booking=booking,
        checkout_session_id=session_id,
        reference_number=booking.get("paymongo_reference_number"),
        payment_method_code=str(
            booking.get("payment_method_code") or "paymongo"
        ),
        payment_scope="selected",
        amount=_money(booking.get("payment_due_amount")),
        status=paymongo_status,
        checkout_url=booking.get("paymongo_checkout_url"),
        raw_payload=result,
    )

    updated_booking = _first(
        service.table("bookings")
        .select("*")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    ) or booking

    return {
        "synced": False,
        "state": state["state"],
        "receipt_ready": False,
        "message": state["message"],
        "booking": _safe_public_booking(updated_booking),
    }

# =========================================================
# MANUAL BOOKING — verified checkout status / merchant return
# =========================================================
# The return capability only authorizes a LIMITED receipt-status result.
# It does NOT authorize booking cancellations or access to personal details.
def _manual_return_secret() -> bytes:
    secret = (
        os.getenv("MANUAL_BOOKING_RETURN_SECRET", "").strip()
        or PAYMONGO_WEBHOOK_SECRET
        or SUPABASE_SERVICE_ROLE_KEY
    )
    if not secret:
        raise HTTPException(status_code=503, detail="Manual payment return is not configured.")
    return secret.encode("utf-8")


def _manual_return_token(booking_id: str) -> str:
    valid_until = int(time.time()) + 72 * 3600
    message = f"manual-payment-v1:{booking_id}:{valid_until}".encode("utf-8")
    signature = hmac.new(_manual_return_secret(), message, hashlib.sha256).hexdigest()
    return f"{valid_until}.{signature}"


def _validate_manual_return_token(booking_id: str, token: str) -> None:
    try:
        expiry_text, provided = token.split(".", 1)
        expiry = int(expiry_text)
        UUID(booking_id)
        if expiry < int(time.time()) or expiry > int(time.time()) + 73 * 3600:
            raise ValueError("expired")
        if len(provided) != 64:
            raise ValueError("invalid")
    except (ValueError, AttributeError) as error:
        raise HTTPException(status_code=403, detail="The payment return link is invalid or expired.") from error
    message = f"manual-payment-v1:{booking_id}:{expiry}".encode("utf-8")
    expected = hmac.new(_manual_return_secret(), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="The payment return link is invalid.")


def _manual_checkout_urls(booking_id: str, api_origin: str) -> tuple[str, str]:
    api_origin = (BACKEND_PUBLIC_URL or api_origin).rstrip("/")
    if not api_origin.startswith(("https://", "http://")):
        raise HTTPException(status_code=500, detail="Configure BACKEND_PUBLIC_URL with your backend's public HTTPS URL.")
    token = _manual_return_token(booking_id)
    common = {"booking": booking_id, "token": token}
    return (
        f"{api_origin}/public-bookings/manual-return?{urlencode({**common, 'payment': 'success'})}",
        f"{api_origin}/public-bookings/manual-return?{urlencode({**common, 'payment': 'cancelled'})}",
    )


def _manual_checkout_draft(service: Client, booking_id: str) -> dict[str, Any] | None:
    return _first(service.table("manual_booking_checkouts").select("*")
                  .eq("id", booking_id).limit(1).execute())


def _finalize_manual_checkout(service, draft, session, payment):
    booking = draft["booking_payload"]
    attributes = payment.get("attributes") or {}
    if (str(session.get("id") or "") != str(booking.get("paymongo_checkout_session_id") or "")
            or str(attributes.get("currency") or "").upper() != "PHP"
            or _money(Decimal(str(attributes.get("amount", 0))) / 100) != _money(booking.get("payment_due_amount"))):
        raise HTTPException(status_code=409, detail="Verified payment does not match this checkout's amount, currency, or session.")
    return _apply_payment(service, booking, session, payment, manual_draft=True)


def sync_manual_checkout_payment(booking_id: str) -> dict[str, Any]:
    """Server-to-server verification. Also works when webhooks are delayed locally.

    Payment is NEVER marked paid because the user reached the success URL.
    Only a paid payment from the secret-key PayMongo Checkout API (or the
    existing verified webhook) can confirm a reservation.
    """
    service = _service()
    draft = _manual_checkout_draft(service, booking_id)
    booking = draft["booking_payload"] if draft else _get_booking(service, booking_id)
    paid_amount = _money(booking.get("amount_paid"))
    current_status = _normalized_status(booking.get("booking_status"))
    if paid_amount > 0 and current_status in {"confirmed", "checked in", "completed"}:
        return {"state": "paid", "booking": booking}

    checkout_id = str(booking.get("paymongo_checkout_session_id") or "").strip()
    if not checkout_id:
        return {"state": "pending", "booking": booking}

    result = _paymongo_request(
        "GET", f"{PAYMONGO_RETRIEVE_CHECKOUT_URL}/{checkout_id}",
        payment_method=str(booking.get("payment_method_code") or ""),
    )
    session = result.get("data", {}) or {}
    if str(session.get("id") or "") != checkout_id:
        raise HTTPException(status_code=502, detail="PayMongo returned a mismatched checkout session.")
    state = _session_payment_state(session)
    if state["paid"]:
        updated = (_finalize_manual_checkout(service, draft, session, state["payment"])
                   if draft else _apply_payment(service, booking, session, state["payment"]))
        return {"state": "paid", "booking": updated}

    # Keep the DB status accurate without falsely treating a return as payment.
    update = {
        "paymongo_status": state["state"],
        "payment_message": state["message"],
        "payment_last_checked_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if state["state"] == "expired" and paid_amount == 0:
        update["booking_status"] = "Expired"
        update["hold_expires_at"] = None
    if draft:
        service.table("manual_booking_checkouts").update({
            "booking_payload": {**booking, **update},
        }).eq("id", booking_id).execute()
    else:
        service.table("bookings").update(update).eq("id", booking_id).execute()
    return {"state": state["state"], "booking": {**booking, **update}}


class ManualReturnStatusRequest(BaseModel):
    booking_id: UUID
    token: str = Field(min_length=66, max_length=90)


@public_router.post("/manual-return-status")
def manual_payment_return_status(payload: ManualReturnStatusRequest):
    booking_id = str(payload.booking_id)
    _validate_manual_return_token(booking_id, payload.token)
    result = sync_manual_checkout_payment(booking_id)
    booking = result["booking"]
    # No contact info, private notes, PayMongo IDs, or internal booking tokens.
    return {
        "state": result["state"],
        "booking_code": booking.get("booking_code"),
        "booking_status": booking.get("booking_status"),
        "payment_status": booking.get("payment_status"),
        "amount_paid": float(_money(booking.get("amount_paid"))),
        "balance_amount": float(_money(booking.get("balance_amount"))),
        "total_amount": float(_money(booking.get("total_amount"))),
    }


@public_router.get("/manual-return", response_class=HTMLResponse)
def manual_booking_return_page(
    booking: UUID,
    token: str,
    payment: Literal["success", "cancelled"] = "success",
):
    # Guest-facing, independent of the protected admin React route / BookForm.
    _validate_manual_return_token(str(booking), token)
    # All injected values are JSON data encoded in an inert script context.
    import json
    runtime = json.dumps({"booking_id": str(booking), "token": token, "payment": payment})
    home = escape(FRONTEND_URL + "/", quote=True)
    html = _MANUAL_RETURN_HTML.replace("__PAYMENT_CONFIG__", runtime).replace("__HOME_URL__", home)
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"},
    )


_MANUAL_RETURN_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="referrer" content="no-referrer"/><title>Payment • The Villa</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100dvh;font-family:Inter,system-ui,-apple-system,Arial,sans-serif;color:#31271f;background:radial-gradient(circle at top,#fff8f1,#eee6de 80%);display:grid;place-items:center;padding:24px}
.card{background:#fff;box-shadow:0 22px 70px #49301b20;border:1px solid #e9ded5;border-radius:22px;padding:42px 36px;width:min(470px,100%);text-align:center}
.brand{font-weight:850;letter-spacing:.08em;color:#7b5037;font-size:12px;text-transform:uppercase}.wheel{width:56px;height:56px;margin:28px auto 18px;border:4px solid #e4d4c7;border-top-color:#80583d;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}.wheel.done{animation:none;border:0;background:#e9f8ee;color:#16744d;display:grid;place-items:center;font-size:30px;font-weight:850}.wheel.no{animation:none;border:0;background:#fff0e7;color:#a65f2e;display:grid;place-items:center;font-size:26px}
h1{margin:0;font-size:25px;letter-spacing:-.04em}p{color:#7e7167;font-size:13px;line-height:1.6;margin:12px 0 0}.detail{margin:24px 0;padding:16px;background:#f8f4f0;border-radius:11px;text-align:left;display:none;font-size:13px}.line{display:flex;justify-content:space-between;gap:14px;padding:7px 0}.line strong{text-align:right}.link{display:inline-flex;margin-top:23px;padding:13px 19px;background:#765037;border-radius:10px;color:white;text-decoration:none;font-size:13px;font-weight:750}.foot{margin-top:20px;color:#94887d;font-size:11px}
</style></head><body><main class="card"><div class="brand">THE VILLA · Secure Checkout</div><div id="icon" class="wheel"></div>
<h1 id="heading">Verifying payment</h1><p id="message">Checking your PayMongo payment securely…</p>
<div class="detail" id="details"><div class="line"><span>Booking</span><strong id="reference">—</strong></div><div class="line"><span>Payment</span><strong id="paymentStatus">—</strong></div><div class="line"><span>Amount paid</span><strong id="paid">—</strong></div><div class="line"><span>Remaining</span><strong id="balance">—</strong></div></div>
<a class="link" href="__HOME_URL__">Return to The Villa</a><div class="foot">Payments are confirmed only by PayMongo.</div></main>
<script>const config=__PAYMENT_CONFIG__;
const el=(id)=>document.getElementById(id);const money=(v)=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'}).format(Number(v||0));
function display(data){el('details').style.display='block';el('reference').textContent=data.booking_code||'—';el('paymentStatus').textContent=data.payment_status||'Pending';el('paid').textContent=money(data.amount_paid);el('balance').textContent=money(data.balance_amount);}
let finished=false,checking=false,fallback,streamController;
function final(state){finished=true;clearInterval(fallback);streamController?.abort();el('icon').className='wheel '+(state==='paid'?'done':'no');el('icon').textContent=state==='paid'?'✓':'!';}
async function check(){if(finished||checking)return;checking=true;try{const response=await fetch('/public-bookings/manual-return-status',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({booking_id:config.booking_id,token:config.token}),cache:'no-store'});if(!response.ok)throw new Error('Unable to verify payment');const data=await response.json();display(data);
if(Number(data.amount_paid)>0&&String(data.booking_status||'').toLowerCase()==='confirmed'){final('paid');el('heading').textContent='Payment confirmed';el('message').textContent=String(data.payment_status).toLowerCase()==='partial'?'Your downpayment was received. Please settle the remaining balance according to your booking agreement.':'Your payment was received. Your reservation is confirmed.';return;}
if(data.state==='expired'){final('other');el('heading').textContent='Payment link expired';el('message').textContent='Please contact The Villa for assistance.';return;}
if(config.payment==='cancelled'&&data.state!=='paid'){final('other');el('heading').textContent='Payment not completed';el('message').textContent='You can return to the checkout link to try again.';return;}
el('heading').textContent='Awaiting PayMongo confirmation';el('message').textContent='We are checking your payment. Please keep this page open.';
}catch(err){el('heading').textContent='Awaiting PayMongo confirmation';el('message').textContent='Payment verification is temporarily unavailable. We will keep checking.';}finally{checking=false;}}
async function listen(){while(!finished){try{streamController=new AbortController();const response=await fetch('/live/booking/'+encodeURIComponent(config.booking_id),{headers:{'Accept':'text/event-stream','X-Manual-Booking-Token':config.token},signal:streamController.signal,cache:'no-store'});if(!response.ok||!response.body)throw new Error('Live updates unavailable');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';while(!finished){const part=await reader.read();if(part.done)break;buffer+=decoder.decode(part.value,{stream:true}).replace(/\r\n/g,'\n');let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);if(frame.startsWith('event: change'))check();}}await reader.cancel();}catch(err){if(!finished)await new Promise(resolve=>setTimeout(resolve,1500));}}}
check();listen();fallback=setInterval(check,30000);</script></body></html>"""

def _public_checkout_draft(service, booking_id):
    return _first(service.table("public_booking_checkouts").select("*").eq("id", booking_id).limit(1).execute())


def process_public_checkout_reconciliation(service=None, limit=25):
    service = service or _service()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    next_check_iso = (now + timedelta(minutes=2)).isoformat()
    response = (
        service.table("public_booking_checkouts")
        .select("id,booking_payload,paymongo_checkout_session_id,next_check_at")
        .not_.is_("paymongo_checkout_session_id", "null")
        .lte("next_check_at", now_iso)
        .order("next_check_at")
        .limit(limit)
        .execute()
    )
    drafts = _attr(response, "data", None) or []
    checked = 0

    for candidate in drafts:
        try:
            claimed = (
                service.table("public_booking_checkouts")
                .update({"next_check_at": next_check_iso})
                .eq("id", candidate["id"])
                .eq("next_check_at", candidate["next_check_at"])
                .select("id")
                .execute()
            )
            if not (_attr(claimed, "data", None) or []):
                continue

            draft = _public_checkout_draft(service, candidate["id"])
            if not draft:
                continue
            booking = draft.get("booking_payload") or {}
            if (
                booking.get("paymongo_checkout_session_id")
                != candidate.get("paymongo_checkout_session_id")
            ):
                logger.error(
                    "Public checkout reconciliation found a mismatched session reference."
                )
                continue

            result = _sync_public_checkout_draft(service, draft)
            if result.get("state") == "expired":
                service.table("public_booking_checkouts").update({
                    "paymongo_checkout_session_id": None,
                    "next_check_at": None,
                }).eq("id", candidate["id"]).execute()
            checked += 1
        except HTTPException as error:
            logger.warning(
                "Public checkout reconciliation could not verify a payment (HTTP %s); it will retry.",
                error.status_code,
            )
        except Exception:
            logger.exception(
                "Public checkout reconciliation failed; it will retry."
            )

    return checked


def _sync_public_checkout_draft(service, draft):
    booking = draft["booking_payload"]
    session_id = booking.get("paymongo_checkout_session_id")
    if not session_id:
        return {"state": "not_started", "booking": booking, "message": "Payment has not started. No booking was saved."}
    response = _paymongo_request("GET", f"{PAYMONGO_RETRIEVE_CHECKOUT_URL}/{session_id}",
                                 payment_method=booking.get("payment_method_code"))
    session = response.get("data") or {}
    if session.get("id") != session_id:
        raise HTTPException(status_code=502, detail="PayMongo returned a mismatched checkout session.")
    state = _session_payment_state(session)
    if not state["paid"]:
        return {"state": state["state"], "message": state["message"], "booking": booking}
    payment = state["payment"]
    attributes = payment.get("attributes") or {}
    if (str(attributes.get("currency") or "").upper() != "PHP"
            or _money(Decimal(str(attributes.get("amount", 0))) / 100) != _money(booking.get("payment_due_amount"))):
        raise HTTPException(status_code=409, detail="Verified payment does not match the checkout amount or currency.")
    saved = _apply_payment(service, booking, session, payment, public_draft=True)
    # Only the caller that atomically promoted the draft sends the acknowledgement.
    if saved.pop("_checkout_finalized", False):
        _send_booking_confirmation_email(saved)
    return {"state": "paid", "message": "Payment confirmed. Your booking is saved.", "booking": saved}
