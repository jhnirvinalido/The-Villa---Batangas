from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import string
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from person_names import validate_person_name
from villa_catalog import get_villa_catalog_map
from staff_admin_auth import validate_portal_access_token
from feedback_analysis import AnalysisFilters

import requests

if TYPE_CHECKING:
    from supabase import Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PAYMONGO_PUBLIC_KEY = os.getenv("PAYMONGO_PUBLIC_KEY", "").strip()
PAYMONGO_SECRET_KEY = os.getenv("PAYMONGO_SECRET_KEY", "").strip()
PAYMONGO_WEBHOOK_SECRET = os.getenv("PAYMONGO_WEBHOOK_SECRET", "").strip()
PAYMONGO_PAYMENT_INTENTS_URL = "https://api.paymongo.com/v1/payment_intents"

THE_VILLA_TIMEZONE_NAME = os.getenv("THE_VILLA_TIMEZONE", "Asia/Manila").strip() or "Asia/Manila"
try:
    THE_VILLA_TIMEZONE = ZoneInfo(THE_VILLA_TIMEZONE_NAME)
except Exception:
    # Safe deployment fallback when the host does not have tzdata installed.
    THE_VILLA_TIMEZONE = timezone(timedelta(hours=8))


logger = logging.getLogger("thevilla.admin")

router = APIRouter()
admin_router = APIRouter(prefix="/admin", tags=["Admin Database"])
front_desk_router = APIRouter(prefix="/front-desk", tags=["Front Desk Settlement"])

STAFF_SELECT = (
    "id,auth_user_id,employee_code,full_name,email,personal_email,username,phone,role,"
    "department,position,shift,is_active,account_status,must_change_password,"
    "last_login_at,password_reset_at,created_at,updated_at,avatar_url,nickname"
)

TASK_SELECT = (
    "id,task_code,booking_id,booking_code,booking_status,booking_payment_status,"
    "booking_check_in,booking_check_out,villa_name,guest_name,guest_phone,"
    "guest_email,assigned_staff_id,created_by_staff_id,updated_by_staff_id,"
    "assignment_type,title,description,department,assigned_role,priority,"
    "due_date,due_time,status,progress,checklist,attachments,notes,source,"
    "from_booking,status_history,started_at,submitted_at,approved_at,"
    "approved_by_staff_id,created_at,updated_at"
)
MESSAGE_SELECT = (
    "id,staff_account_id,sender_account_id,sender_type,concern,body,task_id,"
    "booking_code,read_by_admin,read_by_staff,created_at,updated_at"
)
NOTIFICATION_SELECT = (
    "id,recipient_staff_account_id,title,message,type,icon,task_id,message_id,"
    "payment_transaction_id,is_read,created_at,read_at"
)
SETTINGS_SELECT = (
    "id,staff_account_id,assignment_alerts,overdue_alerts,message_alerts,"
    "booking_alerts,payment_alerts,auto_open_created_assignment,dark_mode,"
    "created_at,updated_at"
)

BOOKING_SELECT = (
    "id,booking_code,user_id,customer_name,customer_email,customer_phone,"
    "villa_id,villa_name,villa_image,check_in_date,check_out_date,"
    "check_in_time,check_out_time,guest_count,nights,notes,total_amount,"
    "payment_choice,payment_method,payment_method_code,payment_environment,"
    "payment_due_amount,amount_paid,balance_amount,booking_status,stay_status,"
    "payment_status,payment_message,payment_last_checked_at,paymongo_status,"
    "paymongo_checkout_session_id,paymongo_checkout_url,"
    "paymongo_reference_number,paymongo_payment_id,"
    "paymongo_payment_intent_id,receipt_number,paid_at,front_desk_payment_method,"
    "front_desk_reference,front_desk_settled_at,"
    "front_desk_other_charges,front_desk_other_charges_total,"
    "checked_in_at,checked_in_by_staff_id,checked_out_at,"
    "checked_out_by_staff_id,created_at,updated_at"
)

BOOKING_PAYMENT_SELECT = (
    "id,booking_id,user_id,paymongo_checkout_session_id,paymongo_payment_id,"
    "paymongo_payment_intent_id,reference_number,amount,currency,"
    "payment_method,payment_method_code,status,livemode,fee_amount,"
    "net_amount,paid_at,created_at"
)

FRONT_DESK_PAYMENT_SELECT = (
    "id,booking_id,receipt_number,method,amount,room_balance_amount,"
    "other_charges_total,payer_name,reference,cash_tendered,change_given,"
    "cashier_staff_id,status,payment_intent_id,processed_at,notes,created_at"
)

WORKFLOW_EVENT_SELECT = (
    "id,booking_id,event_type,from_status,to_status,actor_type,"
    "actor_staff_id,actor_user_id,description,metadata,created_at"
)



class ApiModel(BaseModel):
    class Config:
        allow_population_by_field_name = True
        extra = "ignore"


class StaffCreateRequest(ApiModel):
    _validate_name = field_validator('full_name')(validate_person_name)
    employee_code: str | None = Field(default=None, alias="employeeCode")
    full_name: str = Field(min_length=3, max_length=120, alias="fullName")
    email: EmailStr
    username: str | None = Field(default=None, min_length=3, max_length=80)
    phone: str | None = Field(default=None, max_length=40)
    role: Literal["admin", "staff"] = "staff"
    department: str = Field(min_length=2, max_length=80)
    position: str = Field(min_length=2, max_length=120)
    shift: str | None = Field(default="8:00 AM – 5:00 PM", max_length=80)
    password: str | None = Field(default=None, min_length=16, max_length=128)
    must_change_password: bool = Field(default=True, alias="mustChangePassword")


class StaffUpdateRequest(ApiModel):
    _validate_name = field_validator('full_name')(validate_person_name)
    employee_code: str | None = Field(default=None, alias="employeeCode")
    full_name: str | None = Field(default=None, min_length=3, max_length=120, alias="fullName")
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=80)
    nickname: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=40)
    avatar_url: str | None = Field(default=None, max_length=180000, alias="avatarUrl")
    role: Literal["admin", "staff"] | None = None
    department: str | None = Field(default=None, min_length=2, max_length=80)
    position: str | None = Field(default=None, min_length=2, max_length=120)
    shift: str | None = Field(default=None, max_length=80)
    must_change_password: bool | None = Field(default=None, alias="mustChangePassword")


class StaffStatusRequest(ApiModel):
    account_status: Literal["Active", "Disabled"] = Field(alias="accountStatus")


class StaffPasswordResetRequest(ApiModel):
    password: str | None = Field(default=None, min_length=16, max_length=128)


class TaskUpdateRequest(ApiModel):
    review_note: str | None = Field(default=None, min_length=5, max_length=2000, alias="reviewNote")
    assigned_staff_id: UUID | None = Field(default=None, alias="assignedStaffId")
    title: str | None = Field(default=None, min_length=5, max_length=180)
    description: str | None = Field(default=None, min_length=15, max_length=5000)
    department: str | None = Field(default=None, min_length=2, max_length=80)
    priority: Literal["High", "Medium", "Low"] | None = None
    due_date: date | None = Field(default=None, alias="dueDate")
    due_time: time | None = Field(default=None, alias="dueTime")
    status: Literal[
        "Pending", "In Progress", "Pending Review", "Completed", "Cancelled"
    ] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    checklist: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    notes: str | None = Field(default=None, max_length=5000)


class MessageCreateRequest(ApiModel):
    staff_account_id: UUID = Field(alias="staffId")
    concern: str = Field(default="Message", min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=5000)
    task_id: UUID | None = Field(default=None, alias="assignmentId")
    booking_code: str | None = Field(default=None, max_length=120, alias="bookingCode")


class SettingsUpdateRequest(ApiModel):
    assignment_alerts: bool | None = Field(default=None, alias="assignmentAlerts")
    overdue_alerts: bool | None = Field(default=None, alias="overdueAlerts")
    message_alerts: bool | None = Field(default=None, alias="messageAlerts")
    booking_alerts: bool | None = Field(default=None, alias="bookingAlerts")
    payment_alerts: bool | None = Field(default=None, alias="paymentAlerts")
    auto_open_created_assignment: bool | None = Field(
        default=None, alias="autoOpenCreatedAssignment"
    )
    dark_mode: bool | None = Field(default=None, alias="darkMode")




class OtherChargeRequest(ApiModel):
    description: str = Field(min_length=2, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class CashSettlementRequest(ApiModel):
    payer_name: str = Field(min_length=2, max_length=160)
    payment_timing: Literal["check_in", "check_out"]
    cash_tendered: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    other_charges: list[OtherChargeRequest] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)


class QrPhSettlementRequest(ApiModel):
    payer_name: str = Field(min_length=2, max_length=160)
    payment_timing: Literal["check_in", "check_out"]
    other_charges: list[OtherChargeRequest] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)


class PaymentTimingPreferenceRequest(ApiModel):
    payment_timing: Literal["check_in", "check_out"]


class ManualBookingRequest(BaseModel):
    _validate_names = field_validator('first_name', 'last_name')(validate_person_name)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    villa_ids: list[str] = Field(min_length=1)
    check_in_date: date
    guest_count: int = Field(ge=1, le=32)
    notes: str | None = Field(default=None, max_length=1000)
    payment_choice: Literal["half", "full"] = "half"
    payment_method: Literal["qrph"] = "qrph"


class AirbnbStayHoldRequest(ApiModel):
    check_in_date: date
    check_out_date: date
    guest_count: int = Field(ge=1, le=32)
    villa_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("villa_ids")
    @classmethod
    def unique_villas(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select each villa only once.")
        return value


class BookingLifecycleRequest(ApiModel):
    notes: str | None = Field(default=None, max_length=2000)



def model_values(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def attr(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def rows(response: Any) -> list[dict[str, Any]]:
    value = attr(response, "data", []) or []
    return value if isinstance(value, list) else []


def safe_table_rows(
    client: Client,
    table_name: str,
    select_columns: str = "*",
    *,
    order_column: str | None = None,
    descending: bool = False,
    limit: int | None = None,
    preserve_failure: bool = False,
) -> list[dict[str, Any]] | None:
    """
    Read an optional operational table without preventing the whole
    Admin Dashboard from loading when that later migration has not
    been installed yet. Booking rows are loaded separately and remain
    mandatory because they are the source of truth for reservations.
    """

    try:
        query = client.table(table_name).select(select_columns)
        if order_column:
            query = query.order(order_column, desc=descending)
        if limit is not None:
            query = query.limit(limit)
        from db_pool import read_with_retry
        return rows(read_with_retry(query.execute))
    except Exception as error:
        logger.warning(
            "Optional admin table %s could not be loaded: %s",
            table_name,
            error,
        )
        return None if preserve_failure else []


def load_booking_rows(client: Client) -> list[dict[str, Any]]:
    """Load every customer booking using the real database columns."""

    try:
        from db_pool import read_with_retry
        return rows(
            read_with_retry(client.table("bookings")
            .select("*")
            .order("created_at", desc=True)
            .limit(3000)
            .execute)
        )
    except Exception as error:
        logger.exception("Administrator booking query failed.")
        raise HTTPException(
            status_code=500,
            detail=(
                "Booking updates are temporarily unavailable. Retry in a moment. "
                "Previously loaded bookings are still displayed."
            ),
        ) from error


def load_bootstrap_bookings(client: Client) -> dict[str, Any]:
    try:
        return {"data": load_bookings_with_payments(client), "error": ""}
    except HTTPException as error:
        logger.warning(
            "Admin bootstrap continuing without booking data: %s",
            error.detail,
        )
        return {"data": [], "error": str(error.detail)}


def load_bookings_with_payments(client: Client) -> list[dict[str, Any]]:
    booking_rows = load_booking_rows(client)
    payment_rows = safe_table_rows(
        client,
        "booking_payments",
        BOOKING_PAYMENT_SELECT,
        order_column="paid_at",
        descending=True,
        limit=5000,
    )

    payments_by_booking: dict[str, list[dict[str, Any]]] = {}
    for payment in payment_rows:
        booking_id = str(payment.get("booking_id") or "")
        if booking_id:
            payments_by_booking.setdefault(booking_id, []).append(payment)

    enriched: list[dict[str, Any]] = []
    for booking in booking_rows:
        item = dict(booking)
        item["payment_history"] = payments_by_booking.get(
            str(booking.get("id") or ""),
            [],
        )
        enriched.append(item)

    return enriched


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_environment() -> None:
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", SUPABASE_URL),
            ("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY),
            ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=500,
            detail="Missing backend configuration: " + ", ".join(missing),
        )


def public_client() -> Client:
    require_environment()

    from supabase import create_client

    return create_client(
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
    )


def service_client() -> Client:
    require_environment()

    from db_pool import service_client_for
    return service_client_for(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def supabase_admin_headers() -> dict[str, str]:
    """
    Headers for Supabase Auth Admin REST calls.

    The service-role key stays on the backend and is never returned to React.
    """

    require_environment()

    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def supabase_admin_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """
    Call Supabase Auth Admin directly.

    This avoids compatibility problems in supabase-py's admin Auth methods
    while preserving Supabase Auth as the password source of truth.
    """

    url = (
        f"{SUPABASE_URL.rstrip('/')}"
        f"{path}"
    )

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=supabase_admin_headers(),
            json=payload,
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Supabase Auth could not be reached."
            ),
        ) from error

    if response.status_code == 204:
        return {}

    try:
        body = response.json()
    except ValueError:
        body = {}

    if not response.ok:
        detail = str(
            body.get("msg")
            or body.get("message")
            or body.get("error_description")
            or body.get("error")
            or (
                "Supabase Auth rejected "
                "the administrator request."
            )
        )

        raise HTTPException(
            status_code=(
                409
                if response.status_code
                in {400, 409, 422}
                else response.status_code
            ),
            detail=detail,
        )

    if not body and not allow_empty:
        raise HTTPException(
            status_code=502,
            detail=(
                "Supabase Auth returned "
                "an empty response."
            ),
        )

    return (
        body
        if isinstance(body, dict)
        else {}
    )


def list_supabase_auth_users() -> list[dict[str, Any]]:
    payload = supabase_admin_request(
        "GET",
        "/auth/v1/admin/users"
        "?page=1&per_page=1000",
    )

    users = payload.get("users", [])

    return (
        users
        if isinstance(users, list)
        else []
    )


def find_supabase_auth_user(
    email: str,
) -> dict[str, Any] | None:
    normalized_email = (
        str(email or "")
        .strip()
        .lower()
    )

    for user in list_supabase_auth_users():
        if (
            str(user.get("email") or "")
            .strip()
            .lower()
            == normalized_email
        ):
            return user

    return None


def create_or_repair_portal_auth_user(
    *,
    email: str,
    password: str,
    full_name: str,
    employee_code_value: str,
    role: str,
) -> tuple[dict[str, Any], bool]:
    """
    Create a new Supabase Auth user, or repair an existing unlinked Auth user.

    Returning the existing user allows a previously interrupted staff-account
    creation to be completed instead of leaving an account that cannot log in.
    """

    values = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {
            "full_name": full_name,
            "employee_code":
                employee_code_value,
            "role": role,
            "portalRole": role,
        },
        "app_metadata": {
            "role": role,
            "portalRole": role,
        },
    }

    existing = find_supabase_auth_user(
        email
    )

    if existing:
        user_id = str(
            existing.get("id") or ""
        ).strip()

        if not user_id:
            raise HTTPException(
                status_code=502,
                detail=(
                    "The existing Supabase "
                    "Auth user has no ID."
                ),
            )

        repaired = supabase_admin_request(
            "PUT",
            (
                "/auth/v1/admin/users/"
                f"{user_id}"
            ),
            payload=values,
        )

        return (
            repaired.get("user")
            or repaired,
            False,
        )

    created = supabase_admin_request(
        "POST",
        "/auth/v1/admin/users",
        payload=values,
    )

    return (
        created.get("user")
        or created,
        True,
    )


def update_portal_auth_user(
    auth_user_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    user_id = str(
        auth_user_id or ""
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "The staff record is not "
                "connected to Supabase Auth."
            ),
        )

    response = supabase_admin_request(
        "PUT",
        (
            "/auth/v1/admin/users/"
            f"{user_id}"
        ),
        payload=values,
    )

    return (
        response.get("user")
        or response
    )


def delete_portal_auth_user(
    auth_user_id: str,
) -> None:
    user_id = str(
        auth_user_id or ""
    ).strip()

    if not user_id:
        return

    supabase_admin_request(
        "DELETE",
        (
            "/auth/v1/admin/users/"
            f"{user_id}"
        ),
        allow_empty=True,
    )


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin login session is missing.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Admin login session is missing.")
    return token


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        timestamp = int(decoded.get("exp", 0))
        return (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp > 0
            else None
        )
    except Exception:
        return None


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def strong_password(
    length: int = 24,
) -> str:
    """
    Generate a recognizable but still random temporary password.

    Example:
    TheVilla@2026-Q7mP4xK9
    """

    if length < 16:
        raise ValueError(
            "Password length must be "
            "at least 16 characters."
        )

    year = datetime.now().strftime(
        "%Y"
    )

    symbols = "!@#$"
    random_characters = (
        string.ascii_letters
        + string.digits
    )

    random_length = max(
        8,
        length - len("TheVilla") - 7,
    )

    suffix = "".join(
        secrets.choice(
            random_characters
        )
        for _ in range(
            random_length
        )
    )

    password = (
        "TheVilla"
        + secrets.choice(symbols)
        + year
        + "-"
        + suffix
    )

    return password[:128]


def normalize_username(value: str) -> str:
    normalized = "".join(
        character
        for character in value.strip().lower()
        if character.isalnum() or character in "._-"
    )
    if len(normalized) < 3:
        raise HTTPException(status_code=422, detail="Username must have at least 3 characters.")
    return normalized


def employee_code(role: str) -> str:
    prefix = "ADMIN" if role == "admin" else "ST"
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{secrets.randbelow(9000) + 1000}"


def task_code() -> str:
    return f"ASSIGN-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def fetch_staff_by_auth(auth_user_id: str) -> dict[str, Any] | None:
    response = (
        service_client()
        .table("staff_accounts")
        .select(STAFF_SELECT)
        .eq("auth_user_id", auth_user_id)
        .limit(1)
        .execute()
    )
    result = rows(response)
    return result[0] if result else None


def fetch_staff(staff_id: str) -> dict[str, Any]:
    response = (
        service_client()
        .table("staff_accounts")
        .select(STAFF_SELECT)
        .eq("id", staff_id)
        .limit(1)
        .execute()
    )
    result = rows(response)
    if not result:
        raise HTTPException(status_code=404, detail="Staff account was not found.")
    return result[0]


def fetch_task(task_id: str) -> dict[str, Any]:
    response = (
        service_client()
        .table("admin_tasks")
        .select(TASK_SELECT)
        .eq("id", task_id)
        .limit(1)
        .execute()
    )
    result = rows(response)
    if not result:
        raise HTTPException(status_code=404, detail="Task was not found.")
    return result[0]


def save_session(
    request: Request,
    token: str,
    account: dict[str, Any],
) -> dict[str, Any]:
    """
    Return safe session metadata without creating another database session table.

    Supabase Auth remains the only session source of truth. The raw access token
    is never written to public tables.
    """

    return {
        "staff_account_id": account.get("id"),
        "ip_address": client_ip(request),
        "user_agent": request.headers.get("User-Agent", "")[:500],
        "last_seen_at": now_iso(),
        "expires_at": token_expiry(token),
    }


def require_admin(
    request: Request,
) -> dict[str, Any]:
    token = bearer_token(
        request
    )

    account = (
        validate_portal_access_token(
            token,
            required_role="admin",
        )
    )

    return {
        "token": token,
        "account": account,
        "session": save_session(
            request,
            token,
            account,
        ),
    }


def staff_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "authUserId": row.get("auth_user_id"),
        "employeeCode": row.get("employee_code"),
        "name": row.get("full_name"),
        "fullName": row.get("full_name"),
        "avatarUrl": row.get("avatar_url"),
        "nickname": row.get("nickname"),
        "email": row.get("email"),
        "personalEmail": row.get("personal_email"),
        "username": row.get("username"),
        "phone": row.get("phone"),
        "role": row.get("position") or row.get("role"),
        "portalRole": row.get("role"),
        "department": row.get("department"),
        "position": row.get("position"),
        "shift": row.get("shift"),
        "online": False,
        "isActive": bool(row.get("is_active")),
        "accountStatus": row.get("account_status")
        or ("Active" if row.get("is_active") else "Disabled"),
        "mustChangePassword": bool(row.get("must_change_password")),
        "lastLogin": row.get("last_login_at"),
        "passwordResetAt": row.get("password_reset_at"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def maintenance_on_call(row):
    if row.get("source") == "manual-maintenance-request":
        for event in reversed(row.get("status_history") or []):
            value = (event.get("maintenance") or {}).get("onCall") if isinstance(event, dict) else None
            if value:
                maintenance = event["maintenance"]
                return {
                    **{key: value.get(key) for key in ("state", "expectedArrival", "attentionNeeded", "attentionReason")},
                    "villaId": maintenance.get("villaId"),
                    "scheduleApproved": not maintenance.get("villaId") or bool(maintenance.get("blocksBooking")),
                }
    return None


def task_api(row: dict[str, Any], staff: dict[str, Any] | None = None, creator: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "id": row.get("id"),
        "taskCode": row.get("task_code"),
        **({"assignedBy": "System", "assignedByAvatarUrl": None, "assignedByNickname": None}
           if row.get("source") == "automatic-booking-preparation" else
           ({"assignedBy": creator.get("full_name"), "assignedByAvatarUrl": creator.get("avatar_url"),
             "assignedByNickname": creator.get("nickname")} if creator else {})),
        "bookingId": row.get("booking_id"),
        "bookingCode": row.get("booking_code"),
        "bookingStatus": row.get("booking_status"),
        "bookingPaymentStatus": row.get("booking_payment_status"),
        "bookingCheckIn": row.get("booking_check_in"),
        "bookingCheckOut": row.get("booking_check_out"),
        "villaName": row.get("villa_name"),
        "villa": row.get("villa_name"),
        "guestName": row.get("guest_name"),
        "guest": row.get("guest_name"),
        "contact": row.get("guest_phone"),
        "guestEmail": row.get("guest_email"),
        "assignedStaffId": row.get("assigned_staff_id"),
        "assignedTo": staff.get("full_name") if staff else None,
        "assignedStaffAvatarUrl": staff.get("avatar_url") if staff else None,
        "assignedStaffNickname": staff.get("nickname") if staff else None,
        "assignedRole": row.get("assigned_role")
        or (staff.get("position") if staff else None),
        "createdByStaffId": row.get("created_by_staff_id"),
        "updatedByStaffId": row.get("updated_by_staff_id"),
        "assignmentType": row.get("assignment_type"),
        "title": row.get("title"),
        "description": row.get("description"),
        "category": row.get("department"),
        "department": row.get("department"),
        "priority": row.get("priority"),
        "dueDate": row.get("due_date"),
        "dueTime": row.get("due_time"),
        "status": row.get("status"),
        "progress": row.get("progress") or 0,
        "checklist": row.get("checklist") or [],
        "attachments": row.get("attachments") or [],
        "notes": row.get("notes"),
        "source": row.get("source"),
        "fromBooking": bool(row.get("from_booking")),
        "statusHistory": row.get("status_history") or [],
        "startedAt": row.get("started_at"),
        "submittedAt": row.get("submitted_at"),
        "approvedAt": row.get("approved_at"),
        "approvedByStaffId": row.get("approved_by_staff_id"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }
    on_call = maintenance_on_call(row) if row.get("source") == "manual-maintenance-request" else None
    if on_call:
        arrival = datetime.fromisoformat(on_call["expectedArrival"].replace("Z", "+00:00")).astimezone(THE_VILLA_TIMEZONE) if on_call.get("expectedArrival") else None
        result.update(maintenanceOnCall=on_call, dueDate=arrival.date().isoformat() if arrival else None,
                      dueTime=arrival.strftime("%H:%M:%S") if arrival else None)
    return result


def message_api(
    row: dict[str, Any],
    staff: dict[str, Any] | None = None,
    sender: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "staffId": row.get("staff_account_id"),
        "staffName": staff.get("full_name") if staff else None,
        "senderId": row.get("sender_account_id"),
        "senderName": sender.get("full_name") if sender else None,
        "senderType": row.get("sender_type"),
        "concern": row.get("concern"),
        "body": row.get("body"),
        "assignmentId": row.get("task_id"),
        "assignmentTitle": task.get("title") if task else None,
        "bookingCode": row.get("booking_code"),
        "readByAdmin": bool(row.get("read_by_admin")),
        "readByStaff": bool(row.get("read_by_staff")),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def notification_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "recipientStaffId": row.get("recipient_staff_account_id"),
        "title": row.get("title"),
        "message": row.get("message"),
        "type": row.get("type"),
        "icon": row.get("icon"),
        "taskId": row.get("task_id"),
        "messageId": row.get("message_id"),
        "paymentTransactionId": row.get("payment_transaction_id"),
        "unread": not bool(row.get("is_read")),
        "timestamp": row.get("created_at"),
        "readAt": row.get("read_at"),
    }


def settings_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "assignmentAlerts": bool(row.get("assignment_alerts", True)),
        "overdueAlerts": bool(row.get("overdue_alerts", True)),
        "messageAlerts": bool(row.get("message_alerts", True)),
        "bookingAlerts": bool(row.get("booking_alerts", True)),
        "paymentAlerts": bool(row.get("payment_alerts", True)),
        "autoOpenCreatedAssignment": bool(
            row.get("auto_open_created_assignment", True)
        ),
        "darkMode": bool(row.get("dark_mode", False)),
    }


def load_settings(account_id: str) -> dict[str, Any]:
    result = rows(
        service_client()
        .table("admin_settings")
        .select(SETTINGS_SELECT)
        .eq("staff_account_id", account_id)
        .limit(1)
        .execute()
    )
    if result:
        return result[0]

    created = rows(
        service_client()
        .table("admin_settings")
        .insert({"staff_account_id": account_id})
        .select(SETTINGS_SELECT)
        .execute()
    )
    return created[0] if created else {}


@admin_router.post("/session")
@admin_router.get("/session")
def get_or_create_session(context: dict[str, Any] = Depends(require_admin)):
    return {
        "authenticated": True,
        "user": staff_api(context["account"]),
        "session": context["session"],
    }


@admin_router.delete("/session")
def logout_session(context: dict[str, Any] = Depends(require_admin)):
    """
    Sign out through Supabase Auth.

    The browser must also clear theVillaPortalAuth, theVillaAuthToken, and
    theVillaRefreshToken after this request succeeds.
    """

    try:
        requests.post(
            f"{SUPABASE_URL}/auth/v1/logout",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {context['token']}",
                "Accept": "application/json",
            },
            timeout=(5, 20),
        )
    except requests.RequestException:
        logger.info("Supabase logout request could not be completed.")

    return {"message": "Admin session signed out successfully."}


@admin_router.get("/profile")
def get_current_admin_profile(context: dict[str, Any] = Depends(require_admin)):
    return {"data": staff_api(fetch_staff(str(context["account"]["id"])))}


@admin_router.get("/bootstrap")
def bootstrap(context: dict[str, Any] = Depends(require_admin)):
    client = service_client()

    from read_batches import parallel_reads

    def notifications():
        try:
            from db_pool import read_with_retry
            return rows(read_with_retry(service_client().table("admin_notifications").select(NOTIFICATION_SELECT)
                        .eq("recipient_staff_account_id", context["account"]["id"])
                        .order("created_at", desc=True).limit(1000).execute))
        except Exception:
            logger.warning("Admin notifications could not be loaded.")
            return None

    loaded = parallel_reads({
        "staff": lambda: safe_table_rows(service_client(), "staff_accounts", STAFF_SELECT, order_column="full_name", preserve_failure=True),
        "tasks": lambda: safe_table_rows(service_client(), "admin_tasks", TASK_SELECT, order_column="created_at", descending=True, limit=2000, preserve_failure=True),
        "notifications": notifications,
        "booking_result": lambda: load_bootstrap_bookings(service_client()),
        "payments": lambda: safe_table_rows(service_client(), "front_desk_payments", FRONT_DESK_PAYMENT_SELECT, order_column="processed_at", descending=True, limit=3000, preserve_failure=True),
        "events": lambda: safe_table_rows(service_client(), "booking_workflow_events", WORKFLOW_EVENT_SELECT, order_column="created_at", descending=True, limit=1000),
        "timing": lambda: load_payment_timing_events(service_client()),
    })
    staff_rows, task_rows = loaded["staff"] or [], loaded["tasks"] or []
    staff_map = {str(item["id"]): item for item in staff_rows}
    notification_rows, front_desk_rows, workflow_rows = loaded["notifications"] or [], loaded["payments"] or [], loaded["events"]
    booking_result = loaded["booking_result"]
    enriched_bookings = apply_payment_timing_preferences(booking_result["data"], loaded["timing"])
    booking_map = {str(item["id"]): item for item in enriched_bookings}
    # Batch charge lines, instead of querying each payment's booking, cashier
    # and items separately (formerly three database round trips per receipt).
    payment_items_failed = False
    try:
        items_by_payment = load_front_desk_items_map(client, [str(item["id"]) for item in front_desk_rows]) if front_desk_rows else {}
    except Exception:
        logger.warning("Payment items could not be refreshed; preserving the previous payment snapshot.")
        items_by_payment = {}
        payment_items_failed = True

    payment_transactions = []
    for item in front_desk_rows:
        try:
            payment_transactions.append(front_desk_payment_api(
                item, client=client,
                booking=booking_map.get(str(item.get("booking_id")), {}),
                cashier=staff_map.get(str(item.get("cashier_staff_id")), {}),
                charge_rows=items_by_payment.get(str(item["id"]), []),
            ))
        except Exception as error:
            logger.warning(
                "Front-desk payment %s could not be expanded: %s",
                item.get("id"),
                error,
            )

    return {
        "data": {
            # Auth omits the avatar; use the persisted profile on refresh.
            "profile": None if loaded["staff"] is None else staff_api(staff_map.get(str(context["account"]["id"]))
                                 or fetch_staff(str(context["account"]["id"]))),
            "session": context["session"],
            "bookings": enriched_bookings,
            "bookingError": booking_result["error"],
            "staff": None if loaded["staff"] is None else [staff_api(item) for item in staff_rows],
            "tasks": None if loaded["tasks"] is None else [
                task_api(item, staff_map.get(str(item.get("assigned_staff_id"))))
                for item in task_rows
            ],
            "notifications": None if loaded["notifications"] is None else [notification_api(item) for item in notification_rows],
            "paymentTransactions": None if loaded["payments"] is None or payment_items_failed else payment_transactions,
            "snapshotErrors": [name for name in ("staff", "tasks", "notifications", "payments") if loaded[name] is None] + (["payment items"] if payment_items_failed else []),
            "workflowEvents": workflow_rows,
        }
    }



@admin_router.get("/staff")
def list_staff(
    include_disabled: bool = Query(default=True, alias="includeDisabled"),
    context: dict[str, Any] = Depends(require_admin),
):
    query = service_client().table("staff_accounts").select(STAFF_SELECT)
    if not include_disabled:
        query = query.eq("is_active", True)
    result = rows(query.order("full_name").execute())
    return {"data": [staff_api(item) for item in result]}


@admin_router.get("/staff/{staff_id}")
def get_staff(staff_id: UUID, context: dict[str, Any] = Depends(require_admin)):
    return {"data": staff_api(fetch_staff(str(staff_id)))}


@admin_router.post(
    "/staff",
    status_code=status.HTTP_201_CREATED,
)
def create_staff(
    data: StaffCreateRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    client = service_client()

    email = str(
        data.email
    ).strip().lower()

    username = normalize_username(
        data.username
        or email.split("@", 1)[0]
    )

    code = (
        data.employee_code
        .strip()
        .upper()
        if data.employee_code
        else employee_code(
            data.role
        )
    )

    password = (
        data.password
        or strong_password()
    )

    duplicate = rows(
        client.table(
            "staff_accounts"
        )
        .select("id")
        .or_(
            (
                f"email.eq.{email},"
                f"username.eq.{username},"
                f"employee_code.eq.{code}"
            )
        )
        .limit(1)
        .execute()
    )

    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=(
                "A staff account already "
                "uses this email, username, "
                "or employee code."
            ),
        )

    auth_user_id = ""
    auth_user_was_created = False

    try:
        (
            auth_user,
            auth_user_was_created,
        ) = create_or_repair_portal_auth_user(
            email=email,
            password=password,
            full_name=(
                data.full_name
                .strip()
            ),
            employee_code_value=code,
            role=data.role,
        )

        auth_user_id = str(
            auth_user.get("id")
            or ""
        ).strip()

        if not auth_user_id:
            raise RuntimeError(
                "Supabase did not return "
                "the Auth user ID."
            )

        result = rows(
            client.table(
                "staff_accounts"
            )
            .insert({
                "auth_user_id":
                    auth_user_id,

                "employee_code":
                    code,

                "full_name":
                    data.full_name
                    .strip(),

                "email":
                    email,

                "username":
                    username,

                "phone":
                    (
                        data.phone
                        or ""
                    ).strip()
                    or None,

                "role":
                    data.role,

                "department":
                    data.department
                    .strip(),

                "position":
                    data.position
                    .strip(),

                "shift":
                    (
                        data.shift
                        or ""
                    ).strip()
                    or None,

                "is_active":
                    True,

                "account_status":
                    "Active",

                "must_change_password":
                    data.must_change_password,

                "created_by_staff_id":
                    context[
                        "account"
                    ]["id"],

                "updated_by_staff_id":
                    context[
                        "account"
                    ]["id"],
            })
            .select(STAFF_SELECT)
            .execute()
        )

        if not result:
            raise RuntimeError(
                "The staff directory "
                "record was not created."
            )

        return {
            "message": (
                "Staff account created "
                "successfully."
            ),

            "data":
                staff_api(
                    result[0]
                ),

            "temporaryPassword":
                password,

            "passwordGenerated":
                data.password is None,

            "passwordCopied":
                False,
        }

    except HTTPException:
        if (
            auth_user_id
            and auth_user_was_created
        ):
            try:
                delete_portal_auth_user(
                    auth_user_id
                )
            except Exception:
                logger.exception(
                    (
                        "Could not remove "
                        "incomplete Auth user %s"
                    ),
                    auth_user_id,
                )

        raise

    except Exception as error:
        if (
            auth_user_id
            and auth_user_was_created
        ):
            try:
                delete_portal_auth_user(
                    auth_user_id
                )
            except Exception:
                logger.exception(
                    (
                        "Could not remove "
                        "incomplete Auth user %s"
                    ),
                    auth_user_id,
                )

        logger.exception(
            "Staff account creation failed."
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to create the "
                "staff account."
            ),
        ) from error


@admin_router.patch("/staff/{staff_id}")
def update_staff(
    staff_id: UUID,
    data: StaffUpdateRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    client = service_client()
    current = fetch_staff(str(staff_id))
    supplied = model_values(data)
    if not supplied:
        return {"message": "No changes supplied.", "data": staff_api(current)}

    db_updates: dict[str, Any] = {}
    auth_updates: dict[str, Any] = {}
    metadata = {
        "full_name": current.get("full_name"),
        "employee_code": current.get("employee_code"),
        "role": current.get("role"),
    }

    if data.employee_code is not None:
        db_updates["employee_code"] = data.employee_code.strip().upper()
        metadata["employee_code"] = db_updates["employee_code"]
    if data.full_name is not None:
        db_updates["full_name"] = data.full_name.strip()
        metadata["full_name"] = db_updates["full_name"]
    if data.email is not None:
        db_updates["email"] = str(data.email).strip().lower()
        auth_updates.update({"email": db_updates["email"], "email_confirm": True})
    if data.username is not None:
        db_updates["username"] = normalize_username(data.username)
    if data.nickname is not None:
        db_updates["nickname"] = data.nickname.strip() or None
    if data.phone is not None:
        db_updates["phone"] = data.phone.strip() or None
    if data.avatar_url is not None:
        avatar = data.avatar_url.strip()
        if avatar:
            import base64
            import binascii
            try:
                prefix, encoded = avatar.split(",", 1)
                image = base64.b64decode(encoded, validate=True)
                if prefix != "data:image/jpeg;base64" or not image.startswith(b"\xff\xd8\xff"):
                    raise ValueError("Invalid image")
            except (ValueError, binascii.Error):
                raise HTTPException(status_code=422, detail="Choose a valid profile picture using the photo picker.") from None
        db_updates["avatar_url"] = avatar or None
    if data.role is not None:
        db_updates["role"] = data.role
        metadata["role"] = data.role
        auth_updates["app_metadata"] = {"role": data.role}
    if data.department is not None:
        db_updates["department"] = data.department.strip()
    if data.position is not None:
        db_updates["position"] = data.position.strip()
    if data.shift is not None:
        db_updates["shift"] = data.shift.strip() or None
    if data.must_change_password is not None:
        db_updates["must_change_password"] = data.must_change_password

    duplicate_filters = [
        f"{field}.eq.{db_updates[field]}"
        for field in ("email", "username", "employee_code")
        if db_updates.get(field)
    ]
    if duplicate_filters:
        duplicate = rows(
            client.table("staff_accounts")
            .select("id")
            .or_(",".join(duplicate_filters))
            .neq("id", str(staff_id))
            .limit(1)
            .execute()
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Another account already uses the email, username, or employee code.",
            )

    auth_updates["user_metadata"] = metadata

    if current.get(
        "auth_user_id"
    ):
        update_portal_auth_user(
            str(
                current[
                    "auth_user_id"
                ]
            ),
            auth_updates,
        )

    db_updates.update(
        {
            "updated_by_staff_id": context["account"]["id"],
            "updated_at": now_iso(),
        }
    )
    result = rows(
        client.table("staff_accounts")
        .update(db_updates)
        .eq("id", str(staff_id))
        .select(STAFF_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Staff account was not found.")

    return {"message": "Staff account updated successfully.", "data": staff_api(result[0])}


@admin_router.patch("/staff/{staff_id}/status")
def staff_status(
    staff_id: UUID,
    data: StaffStatusRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    if str(staff_id) == str(context["account"]["id"]) and data.account_status == "Disabled":
        raise HTTPException(
            status_code=400,
            detail="You cannot disable the administrator account currently in use.",
        )

    client = service_client()
    active = data.account_status == "Active"
    result = rows(
        client.table("staff_accounts")
        .update(
            {
                "account_status": data.account_status,
                "is_active": active,
                "updated_by_staff_id": context["account"]["id"],
                "updated_at": now_iso(),
            }
        )
        .eq("id", str(staff_id))
        .select(STAFF_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Staff account was not found.")


    return {
        "message": f"Account is now {data.account_status.lower()}.",
        "data": staff_api(result[0]),
    }


@admin_router.post(
    "/staff/{staff_id}/reset-password"
)
def reset_password(
    staff_id: UUID,
    data: StaffPasswordResetRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    client = service_client()

    current = fetch_staff(
        str(staff_id)
    )

    password = (
        data.password
        or strong_password()
    )

    if not current.get(
        "auth_user_id"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "This staff record is "
                "not connected to "
                "Supabase Auth."
            ),
        )

    update_portal_auth_user(
        str(
            current[
                "auth_user_id"
            ]
        ),
        {
            "password":
                password,

            "email_confirm":
                True,

            "user_metadata": {
                "full_name":
                    current.get(
                        "full_name"
                    ),

                "employee_code":
                    current.get(
                        "employee_code"
                    ),

                "role":
                    current.get(
                        "role"
                    ),

                "portalRole":
                    current.get(
                        "role"
                    ),
            },

            "app_metadata": {
                "role":
                    current.get(
                        "role"
                    ),

                "portalRole":
                    current.get(
                        "role"
                    ),
            },
        },
    )

    current_time = now_iso()

    result = rows(
        client.table(
            "staff_accounts"
        )
        .update({
            "must_change_password":
                True,

            "password_reset_at":
                current_time,

            "updated_at":
                current_time,

            "updated_by_staff_id":
                context[
                    "account"
                ]["id"],
        })
        .eq(
            "id",
            str(staff_id),
        )
        .select(STAFF_SELECT)
        .execute()
    )

    return {
        "message": (
            "A The Villa temporary "
            "password was created."
        ),

        "data":
            staff_api(
                result[0]
                if result
                else current
            ),

        "temporaryPassword":
            password,

        "passwordGenerated":
            data.password is None,

        "passwordCopied":
            False,
    }


@admin_router.get("/tasks")
def list_tasks(
    staff_id: UUID | None = Query(default=None, alias="staffId"),
    task_status: str | None = Query(default=None, alias="status"),
    booking_id: str | None = Query(default=None, alias="bookingId"),
    context: dict[str, Any] = Depends(require_admin),
):
    query = service_client().table("admin_tasks").select(TASK_SELECT)
    if staff_id:
        query = query.eq("assigned_staff_id", str(staff_id))
    if task_status:
        query = query.eq("status", task_status)
    if booking_id:
        query = query.eq("booking_id", booking_id)

    task_rows = rows(query.order("created_at", desc=True).limit(2000).execute())
    staff_ids = {
        str(item.get("assigned_staff_id"))
        for item in task_rows
        if item.get("assigned_staff_id")
    }
    staff_map = {}
    if staff_ids:
        staff_rows = rows(
            service_client()
            .table("staff_accounts")
            .select(STAFF_SELECT)
            .in_("id", list(staff_ids))
            .execute()
        )
        staff_map = {str(item["id"]): item for item in staff_rows}

    return {
        "data": [
            task_api(item, staff_map.get(str(item.get("assigned_staff_id"))))
            for item in task_rows
        ]
    }


@admin_router.get("/tasks/{task_id}")
def get_task(task_id: UUID, context: dict[str, Any] = Depends(require_admin)):
    task = fetch_task(str(task_id))
    return {"data": task_api(task, fetch_staff(str(task["assigned_staff_id"])))}


@admin_router.patch("/tasks/{task_id}")
def update_task(
    task_id: UUID,
    data: TaskUpdateRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    client = service_client()
    current = fetch_task(str(task_id))
    if current.get("source") == "manual-maintenance-request":
        raise HTTPException(status_code=409, detail="Open Villas & Pricing to update or verify this villa operation.")
    if current.get("status") == "Completed":
        raise HTTPException(status_code=409, detail="An approved assignment cannot be edited.")
    supplied = model_values(data)

    if not supplied:
        staff = fetch_staff(str(current["assigned_staff_id"]))
        return {"message": "No changes supplied.", "data": task_api(current, staff)}

    staff = fetch_staff(str(data.assigned_staff_id or current["assigned_staff_id"]))
    if not staff.get("is_active"):
        raise HTTPException(status_code=400, detail="The selected staff account is disabled.")

    updates: dict[str, Any] = {}
    if data.assigned_staff_id is not None:
        updates.update(
            {
                "assigned_staff_id": str(data.assigned_staff_id),
                "assigned_role": staff.get("position"),
                "department": staff.get("department"),
            }
        )
    if data.title is not None:
        updates["title"] = data.title.strip()
    if data.description is not None:
        updates["description"] = data.description.strip()
    if data.department is not None:
        if staff.get("department") != data.department:
            raise HTTPException(
                status_code=400,
                detail="The selected staff member does not belong to the chosen department.",
            )
        updates["department"] = data.department.strip()
    if data.priority is not None:
        updates["priority"] = data.priority
    if data.due_date is not None:
        updates["due_date"] = data.due_date.isoformat()
    if data.due_time is not None:
        updates["due_time"] = data.due_time.isoformat()
    if data.progress is not None:
        updates["progress"] = data.progress
    if data.checklist is not None:
        updates["checklist"] = data.checklist
    if data.attachments is not None:
        updates["attachments"] = data.attachments
    if data.notes is not None:
        updates["notes"] = data.notes

    status_changed = data.status is not None and data.status != current.get("status")
    if data.status is not None:
        current_status = str(current.get("status") or "Pending")
        allowed_transitions = {
            "Pending": {"Pending", "In Progress", "Cancelled"},
            "In Progress": {"In Progress", "Pending Review", "Completed", "Cancelled"},
            "Pending Review": {"Pending Review", "In Progress", "Completed", "Cancelled"},
            "Completed": {"Completed"},
            "Cancelled": {"Cancelled", "Pending"},
        }
        if data.status not in allowed_transitions.get(current_status, {current_status}):
            raise HTTPException(
                status_code=409,
                detail=f"Assignment cannot move from {current_status} to {data.status}.",
            )

        updates["status"] = data.status
        if data.status == "Completed":
            checklist_for_approval = updates.get("checklist", current.get("checklist") or [])
            if checklist_for_approval and not all(
                bool(item.get("done")) for item in checklist_for_approval
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Complete every checklist item before approving the assignment.",
                )
            updates.update(
                {
                    "progress": 100,
                    "approved_at": now_iso(),
                    "approved_by_staff_id": context["account"]["id"],
                }
            )
        elif data.status in {"In Progress", "Pending", "Cancelled"}:
            updates["approved_at"] = None
            updates["approved_by_staff_id"] = None

    if status_changed:
        history = current.get("status_history") or []
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "id": f"AUDIT-{secrets.token_hex(6)}",
                "status": data.status,
                "actor": context["account"]["full_name"],
                "actorStaffId": context["account"]["id"],
                "note": (f"Returned for correction: {data.review_note.strip()}" if data.review_note and data.status == "In Progress" else f"Status changed to {data.status}."),
                "timestamp": now_iso(),
            }
        )
        updates["status_history"] = history

    updates.update(
        {
            "updated_by_staff_id": context["account"]["id"],
            "updated_at": now_iso(),
        }
    )
    result = rows(
        client.table("admin_tasks")
        .update(updates)
        .eq("id", str(task_id))
        .select(TASK_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task was not found.")

    if status_changed and current.get("booking_id"):
        record_booking_event(
            str(current["booking_id"]),
            "staff_assignment_status_changed",
            (
                f"{context['account']['full_name']} changed assignment "
                f"{current.get('task_code') or task_id} from "
                f"{current.get('status')} to {data.status}."
            ),
            from_status=str(current.get("booking_status") or ""),
            to_status=str(current.get("booking_status") or ""),
            actor_type="admin",
            actor_staff_id=context["account"]["id"],
            metadata={
                "task_id": str(task_id),
                "task_code": current.get("task_code"),
                "assignment_from_status": current.get("status"),
                "assignment_to_status": data.status,
            },
        )

    if status_changed:
        client.table("admin_notifications").insert(
            {
                "recipient_staff_account_id": result[0]["assigned_staff_id"],
                "title": "Assignment Approved"
                if data.status == "Completed"
                else "Assignment Updated",
                "message": f"“{result[0]['title']}” is now {data.status}.",
                "type": "assignment-status",
                "icon": "task",
                "task_id": result[0]["id"],
                "is_read": False,
            }
        ).execute()

    if str(current.get("assigned_staff_id")) != str(result[0].get("assigned_staff_id")):
        create_notification(
            str(result[0]["assigned_staff_id"]), "New Assignment",
            f"You were assigned “{result[0]['title']}”. Review your checklist and schedule in the staff portal.",
            notification_type="assignment", icon="task", task_id=str(result[0]["id"]),
        )

    return {"message": "Assignment updated successfully.", "data": task_api(result[0], staff)}


@admin_router.delete("/tasks/{task_id}")
def delete_task(task_id: UUID, context: dict[str, Any] = Depends(require_admin)):
    current = fetch_task(str(task_id))
    if current.get("source") == "manual-maintenance-request":
        raise HTTPException(status_code=409, detail="Open Villas & Pricing to update or verify this villa operation.")
    if current.get("status") == "Completed":
        raise HTTPException(status_code=409, detail="An approved assignment cannot be deleted.")
    (
        service_client()
        .table("admin_tasks")
        .delete()
        .eq("id", str(task_id))
        .execute()
    )
    return {
        "message": f"“{current['title']}” was deleted successfully.",
        "deletedTaskId": str(task_id),
    }


@admin_router.get("/messages")
def list_messages(
    staff_id: UUID | None = Query(default=None, alias="staffId"),
    context: dict[str, Any] = Depends(require_admin),
):
    query = service_client().table("staff_messages").select(MESSAGE_SELECT)
    if staff_id:
        query = query.eq("staff_account_id", str(staff_id))
    message_rows = rows(query.order("created_at").limit(3000).execute())

    staff_ids = {
        str(value)
        for item in message_rows
        for value in (item.get("staff_account_id"), item.get("sender_account_id"))
        if value
    }
    task_ids = {
        str(item.get("task_id"))
        for item in message_rows
        if item.get("task_id")
    }

    staff_map = {}
    task_map = {}
    if staff_ids:
        staff_rows = rows(
            service_client()
            .table("staff_accounts")
            .select(STAFF_SELECT)
            .in_("id", list(staff_ids))
            .execute()
        )
        staff_map = {str(item["id"]): item for item in staff_rows}
    if task_ids:
        task_rows = rows(
            service_client()
            .table("admin_tasks")
            .select(TASK_SELECT)
            .in_("id", list(task_ids))
            .execute()
        )
        task_map = {str(item["id"]): item for item in task_rows}

    return {
        "data": [
            message_api(
                item,
                staff_map.get(str(item.get("staff_account_id"))),
                staff_map.get(str(item.get("sender_account_id"))),
                task_map.get(str(item.get("task_id"))),
            )
            for item in message_rows
        ]
    }


@admin_router.post("/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    data: MessageCreateRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    client = service_client()
    staff = fetch_staff(str(data.staff_account_id))
    if not staff.get("is_active"):
        raise HTTPException(
            status_code=400,
            detail="Enable the staff account before sending a message.",
        )

    task = fetch_task(str(data.task_id)) if data.task_id else None
    if task and str(task.get("assigned_staff_id")) != str(data.staff_account_id):
        raise HTTPException(
            status_code=400,
            detail="The selected task is assigned to a different staff account.",
        )

    result = rows(
        client.table("staff_messages")
        .insert(
            {
                "staff_account_id": str(data.staff_account_id),
                "sender_account_id": context["account"]["id"],
                "sender_type": "admin",
                "concern": data.concern.strip(),
                "body": data.body.strip(),
                "task_id": str(data.task_id) if data.task_id else None,
                "booking_code": data.booking_code
                or (task.get("booking_code") if task else None),
                "read_by_admin": True,
                "read_by_staff": False,
            }
        )
        .select(MESSAGE_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=500, detail="The staff message was not saved.")
    message = result[0]

    notification = rows(
        client.table("admin_notifications")
        .insert(
            {
                "recipient_staff_account_id": str(data.staff_account_id),
                "title": "New message from Villa Administrator",
                "message": data.body.strip(),
                "type": "admin-message",
                "icon": "message",
                "task_id": str(data.task_id) if data.task_id else None,
                "message_id": message["id"],
                "is_read": False,
            }
        )
        .select(NOTIFICATION_SELECT)
        .execute()
    )

    return {
        "message": f"Message sent to {staff['full_name']}.",
        "data": message_api(message, staff, context["account"], task),
        "notification": notification_api(notification[0]) if notification else None,
    }


@admin_router.patch("/messages/{message_id}/read")
def read_message(
    message_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    result = rows(
        service_client()
        .table("staff_messages")
        .update({"read_by_admin": True, "updated_at": now_iso()})
        .eq("id", str(message_id))
        .select(MESSAGE_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Message was not found.")
    return {"message": "Message marked as read.", "data": result[0]}


@admin_router.get("/notifications")
def list_notifications(
    unread_only: bool = Query(default=False, alias="unreadOnly"),
    context: dict[str, Any] = Depends(require_admin),
):
    query = (
        service_client()
        .table("admin_notifications")
        .select(NOTIFICATION_SELECT)
        .eq("recipient_staff_account_id", context["account"]["id"])
    )
    if unread_only:
        query = query.eq("is_read", False)
    result = rows(query.order("created_at", desc=True).limit(1000).execute())
    return {"data": [notification_api(item) for item in result]}


@admin_router.patch("/notifications/{notification_id}/read")
def read_notification(
    notification_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    result = rows(
        service_client()
        .table("admin_notifications")
        .update({"is_read": True, "read_at": now_iso()})
        .eq("id", str(notification_id))
        .eq("recipient_staff_account_id", context["account"]["id"])
        .select(NOTIFICATION_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Notification was not found.")
    return {"message": "Notification marked as read.", "data": notification_api(result[0])}


@admin_router.patch("/notifications/read-all")
def read_all_notifications(context: dict[str, Any] = Depends(require_admin)):
    (
        service_client()
        .table("admin_notifications")
        .update({"is_read": True, "read_at": now_iso()})
        .eq("recipient_staff_account_id", context["account"]["id"])
        .eq("is_read", False)
        .execute()
    )
    return {"message": "All notifications were marked as read."}


@admin_router.get("/settings")
def get_settings(context: dict[str, Any] = Depends(require_admin)):
    return {"data": settings_api(load_settings(context["account"]["id"]))}


@admin_router.put("/settings")
def update_settings(
    data: SettingsUpdateRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    values = model_values(data)
    if not values:
        return {
            "message": "No settings changes supplied.",
            "data": settings_api(load_settings(context["account"]["id"])),
        }

    values.update(
        {
            "staff_account_id": context["account"]["id"],
            "updated_at": now_iso(),
        }
    )
    result = rows(
        service_client()
        .table("admin_settings")
        .upsert(values, on_conflict="staff_account_id")
        .select(SETTINGS_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=500, detail="Admin settings were not saved.")

    return {
        "message": "Administrator settings saved successfully.",
        "data": settings_api(result[0]),
    }

# ============================================================
# SHARED PORTAL / BOOKING / PAYMENT HELPERS
# ============================================================

def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def centavos(value: Decimal) -> int:
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fetch_booking(booking_id: str) -> dict[str, Any]:
    result = rows(
        service_client()
        .table("bookings")
        .select("*")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Booking was not found.")
    return result[0]


def booking_initial_payment_required(booking: dict[str, Any]) -> Decimal:
    total = money(booking.get("total_amount"))
    return total if str(booking.get("payment_choice", "half")).lower() == "full" else (
        total * Decimal("0.50")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def booking_initial_payment_verified(booking: dict[str, Any]) -> bool:
    return money(booking.get("amount_paid")) >= booking_initial_payment_required(booking)


def active_admin_accounts() -> list[dict[str, Any]]:
    return rows(
        service_client()
        .table("staff_accounts")
        .select(STAFF_SELECT)
        .eq("role", "admin")
        .eq("is_active", True)
        .eq("account_status", "Active")
        .execute()
    )


def create_notification(
    recipient_staff_id: str,
    title: str,
    message: str,
    *,
    notification_type: str = "general",
    icon: str = "bell",
    task_id: str | None = None,
    message_id: str | None = None,
    payment_transaction_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        result = rows(
            service_client()
            .table(
                "admin_notifications"
            )
            .insert({
                "recipient_staff_account_id":
                    recipient_staff_id,

                "title":
                    title,

                "message":
                    message,

                "type":
                    notification_type,

                "icon":
                    icon,

                "task_id":
                    task_id,

                "message_id":
                    message_id,

                "payment_transaction_id":
                    payment_transaction_id,

                "is_read":
                    False,
            })
            .select(
                NOTIFICATION_SELECT
            )
            .execute()
        )

        return (
            result[0]
            if result
            else None
        )

    except Exception as error:
        logger.warning(
            (
                "Notification could not "
                "be stored: %s"
            ),
            error,
        )

        return None


def notify_admins(
    title: str,
    message: str,
    *,
    notification_type: str = "general",
    icon: str = "bell",
    task_id: str | None = None,
    message_id: str | None = None,
    payment_transaction_id: str | None = None,
) -> None:
    for admin in active_admin_accounts():
        create_notification(
            str(admin["id"]),
            title,
            message,
            notification_type=notification_type,
            icon=icon,
            task_id=task_id,
            message_id=message_id,
            payment_transaction_id=payment_transaction_id,
        )


def record_booking_event(
    booking_id: str,
    event_type: str,
    description: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_type: str = "system",
    actor_staff_id: str | None = None,
    actor_user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Record an audit event without breaking the primary operation when the
    optional workflow table has not been installed yet.
    """

    try:
        (
            service_client()
            .table(
                "booking_workflow_events"
            )
            .insert({
                "booking_id":
                    booking_id,

                "event_type":
                    event_type,

                "from_status":
                    from_status,

                "to_status":
                    to_status,

                "actor_type":
                    actor_type,

                "actor_staff_id":
                    actor_staff_id,

                "actor_user_id":
                    actor_user_id,

                "description":
                    description,

                "metadata":
                    metadata or {},
            })
            .execute()
        )
    except Exception as error:
        logger.warning(
            (
                "Booking workflow event "
                "could not be stored: %s"
            ),
            error,
        )


def load_front_desk_items_map(client, payment_ids):
    result = {}
    for start in range(0, len(payment_ids), 100):
        offset = 0
        while True:
            batch = rows(client.table("front_desk_payment_items")
                         .select("id,front_desk_payment_id,description,amount,created_at")
                         .in_("front_desk_payment_id", payment_ids[start:start + 100])
                         .order("id").range(offset, offset + 999).execute())
            for row in batch:
                result.setdefault(str(row["front_desk_payment_id"]), []).append(row)
            if len(batch) < 1000:
                break
            offset += 1000
    return result


def front_desk_payment_items(payment_id: str, client: Client | None = None) -> list[dict[str, Any]]:
    active_client = client or service_client()
    return rows(
        active_client.table("front_desk_payment_items")
        .select("id,description,amount,created_at")
        .eq("front_desk_payment_id", payment_id)
        .order("created_at")
        .execute()
    )



def villa_business_today() -> date:
    """Return the current business date using the configured Villa timezone."""
    return datetime.now(THE_VILLA_TIMEZONE).date()


def booking_lifecycle_date(
    booking: dict[str, Any],
    field_name: str,
) -> date:
    raw_value = str(booking.get(field_name) or "").strip()
    if not raw_value:
        label = "check-in" if field_name == "check_in_date" else "check-out"
        raise HTTPException(
            status_code=409,
            detail=f"This booking has no valid {label} date. Update the booking before continuing.",
        )

    try:
        return date.fromisoformat(raw_value[:10])
    except ValueError as error:
        label = "check-in" if field_name == "check_in_date" else "check-out"
        raise HTTPException(
            status_code=409,
            detail=f"This booking has an invalid {label} date. Update the booking before continuing.",
        ) from error


def enforce_booking_lifecycle_date(
    booking: dict[str, Any],
    action: Literal["check_in", "check_out"],
) -> None:
    """Keep the arrival-date rule; allow checkout testing on any date.

    Checkout and checkout-balance collection still validate checked-in state,
    verified payments, the remaining balance, and pending QRPh settlements.
    """
    if action == "check_out":
        return

    today = villa_business_today()
    booked_date = booking_lifecycle_date(booking, "check_in_date")
    if today != booked_date:
        detail = (
            f"Check-in is not available yet. This booking is scheduled for {booked_date.isoformat()}."
            if today < booked_date
            else f"Check-in is not allowed today. This booking was scheduled for {booked_date.isoformat()}."
        )
        raise HTTPException(status_code=409, detail=detail)


PAYMENT_TIMING_LABELS = {
    "check_in": "Check-in",
    "check_out": "Check-out",
}

PAYMENT_TIMING_NOTE_PREFIX = "[Payment timing: "
PAYMENT_TIMING_SELECTION_EVENT = "balance_payment_timing_selected"


def normalize_payment_timing(value: Any, *, default: str = "check_in") -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in PAYMENT_TIMING_LABELS:
        return normalized
    if default == "" or default in PAYMENT_TIMING_LABELS:
        return default
    return "check_in"


def payment_timing_from_event(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    metadata = event.get("metadata") or {}
    timing = normalize_payment_timing(
        metadata.get("payment_timing"),
        default="",
    )
    return timing or None


def load_payment_timing_events(
    client: Client | None = None,
) -> list[dict[str, Any]]:
    active_client = client or service_client()
    try:
        return rows(
            active_client.table("booking_workflow_events")
            .select(WORKFLOW_EVENT_SELECT)
            .eq("event_type", PAYMENT_TIMING_SELECTION_EVENT)
            .order("created_at", desc=True)
            .limit(3000)
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Balance payment timing events could not be loaded: %s",
            error,
        )
        return []


def payment_timing_map_from_events(
    workflow_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Workflow rows are normally newest-first. The first timing-selection event
    found for each booking is therefore the active customer choice.
    """
    result: dict[str, str] = {}
    for event in workflow_rows:
        if str(event.get("event_type") or "") != PAYMENT_TIMING_SELECTION_EVENT:
            continue
        booking_id = str(event.get("booking_id") or "")
        if not booking_id or booking_id in result:
            continue
        timing = payment_timing_from_event(event)
        if timing:
            result[booking_id] = timing
    return result


def apply_payment_timing_preferences(
    booking_rows: list[dict[str, Any]],
    workflow_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    timing_map = payment_timing_map_from_events(workflow_rows)
    enriched: list[dict[str, Any]] = []
    for row in booking_rows:
        item = dict(row)
        item["front_desk_balance_timing"] = timing_map.get(
            str(item.get("id") or ""),
            "",
        )
        enriched.append(item)
    return enriched


def latest_payment_timing_for_booking(
    booking_id: str,
    client: Client | None = None,
) -> str | None:
    active_client = client or service_client()
    try:
        event_rows = rows(
            active_client.table("booking_workflow_events")
            .select(WORKFLOW_EVENT_SELECT)
            .eq("booking_id", str(booking_id))
            .eq("event_type", PAYMENT_TIMING_SELECTION_EVENT)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Balance payment timing could not be loaded for booking %s: %s",
            booking_id,
            error,
        )
        return None

    return payment_timing_from_event(event_rows[0] if event_rows else None)


def attach_payment_timing(
    booking: dict[str, Any],
    client: Client | None = None,
) -> dict[str, Any]:
    item = dict(booking)
    item["front_desk_balance_timing"] = (
        latest_payment_timing_for_booking(str(item.get("id") or ""), client)
        or item.get("front_desk_balance_timing")
        or ""
    )
    return item


def save_payment_timing_preference(
    *,
    booking: dict[str, Any],
    cashier: dict[str, Any],
    payment_timing: str,
) -> str:
    timing = normalize_payment_timing(payment_timing, default="")
    if timing not in PAYMENT_TIMING_LABELS:
        raise HTTPException(
            status_code=422,
            detail="Choose Pay at Check-in or Pay at Check-out.",
        )

    if str(booking.get("payment_choice") or "").strip().lower() != "half":
        raise HTTPException(
            status_code=409,
            detail="This timing choice is only used for bookings with a remaining 50% balance.",
        )

    if not booking_initial_payment_verified(booking):
        raise HTTPException(
            status_code=409,
            detail="The original customer downpayment must be verified first.",
        )

    if money(booking.get("balance_amount")) <= 0:
        raise HTTPException(
            status_code=409,
            detail="This booking has no remaining balance to schedule.",
        )

    stay_status = str(
        booking.get("stay_status")
        or booking.get("booking_status")
        or ""
    ).strip().lower()

    if stay_status in {"checked out", "completed"}:
        raise HTTPException(
            status_code=409,
            detail="This stay is already completed.",
        )

    label = PAYMENT_TIMING_LABELS[timing]
    try:
        (
            service_client()
            .table("booking_workflow_events")
            .insert(
                {
                    "booking_id": str(booking["id"]),
                    "event_type": PAYMENT_TIMING_SELECTION_EVENT,
                    "from_status": str(
                        booking.get("stay_status")
                        or booking.get("booking_status")
                        or ""
                    ),
                    "to_status": str(
                        booking.get("stay_status")
                        or booking.get("booking_status")
                        or ""
                    ),
                    "actor_type": "admin",
                    "actor_staff_id": str(cashier.get("id") or "") or None,
                    "actor_user_id": None,
                    "description": (
                        f"Guest selected Pay at {label} for the remaining balance."
                    ),
                    "metadata": {
                        "payment_timing": timing,
                        "payment_timing_label": label,
                        "source": "front_desk_booking_summary",
                    },
                }
            )
            .execute()
        )
    except Exception as error:
        logger.exception(
            "Balance payment timing could not be saved for booking %s.",
            booking.get("id"),
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The guest payment timing could not be saved. "
                "Confirm that booking_workflow_events is installed."
            ),
        ) from error

    return timing


def encode_settlement_notes(notes: str | None, payment_timing: str) -> str:
    timing = normalize_payment_timing(payment_timing)
    label = PAYMENT_TIMING_LABELS[timing]
    clean_notes = str(notes or "").strip()
    prefix = f"{PAYMENT_TIMING_NOTE_PREFIX}{label}]"
    return f"{prefix}\n{clean_notes}" if clean_notes else prefix


def decode_settlement_notes(notes: Any) -> tuple[str | None, str]:
    raw = str(notes or "").strip()
    if not raw.startswith(PAYMENT_TIMING_NOTE_PREFIX):
        return None, raw

    closing = raw.find("]")
    if closing < 0:
        return None, raw

    label = raw[len(PAYMENT_TIMING_NOTE_PREFIX):closing].strip().lower()
    timing = "check_out" if "out" in label else "check_in"
    clean_notes = raw[closing + 1:].lstrip("\n ")
    return timing, clean_notes


def validate_payment_timing_for_booking(
    booking: dict[str, Any],
    payment_timing: str,
) -> str:
    timing = normalize_payment_timing(payment_timing, default="")
    if timing not in PAYMENT_TIMING_LABELS:
        raise HTTPException(
            status_code=422,
            detail="Choose Pay at Check-in or Pay at Check-out before collecting payment.",
        )

    # Preserve the arrival-date rule for check-in payments. Checkout collection
    # can be tested on any date after the guest has checked in.
    enforce_booking_lifecycle_date(booking, timing)

    saved_timing = latest_payment_timing_for_booking(str(booking.get("id") or ""))
    if saved_timing and saved_timing != timing:
        raise HTTPException(
            status_code=409,
            detail=(
                "The payment timing no longer matches the saved guest choice. "
                "Return to Booking Summary and confirm the timing again."
            ),
        )

    stay_status = str(
        booking.get("stay_status")
        or booking.get("booking_status")
        or ""
    ).strip().lower()

    if timing == "check_out" and stay_status != "checked in":
        raise HTTPException(
            status_code=409,
            detail=(
                "This guest chose Pay at Check-out. "
                "Check the guest in first, then collect the balance during checkout."
            ),
        )

    if stay_status in {"checked out", "completed"}:
        raise HTTPException(
            status_code=409,
            detail="This stay is already completed.",
        )

    return timing


def record_payment_timing_event(
    *,
    booking: dict[str, Any],
    cashier: dict[str, Any],
    payment: dict[str, Any] | None,
    payment_timing: str,
    method: str,
) -> None:
    timing = normalize_payment_timing(payment_timing)
    label = PAYMENT_TIMING_LABELS[timing]
    record_booking_event(
        str(booking.get("id")),
        f"balance_paid_at_{timing}",
        f"Remaining balance was collected at {label.lower()} through {method}.",
        from_status=str(booking.get("stay_status") or booking.get("booking_status") or ""),
        to_status=str(booking.get("stay_status") or booking.get("booking_status") or ""),
        actor_type="admin",
        actor_staff_id=str(cashier.get("id") or "") or None,
        metadata={
            "payment_timing": timing,
            "payment_timing_label": label,
            "payment_method": method,
            "payment_id": str((payment or {}).get("id") or "") or None,
        },
    )


def front_desk_payment_api(
    payment: dict[str, Any],
    *,
    booking: dict[str, Any] | None = None,
    cashier: dict[str, Any] | None = None,
    client: Client | None = None,
    charge_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_client = client if client is not None else service_client()
    resolved_booking = booking if booking is not None else fetch_booking(str(payment["booking_id"]))
    resolved_cashier = cashier if cashier is not None else fetch_staff(str(payment["cashier_staff_id"]))
    if charge_rows is None:
        charge_rows = front_desk_payment_items(str(payment["id"]), active_client)
    payment_timing, clean_notes = decode_settlement_notes(payment.get("notes"))
    charges = [
        {
            "id": item.get("id"),
            "description": item.get("description"),
            "amount": float(money(item.get("amount"))),
        }
        for item in charge_rows
    ]
    return {
        "id": payment.get("id"),
        "receiptNumber": payment.get("receipt_number"),
        "bookingId": payment.get("booking_id"),
        "bookingCode": resolved_booking.get("booking_code"),
        "guestName": resolved_booking.get("customer_name"),
        "payerName": payment.get("payer_name"),
        "villaName": resolved_booking.get("villa_name"),
        "stage": "Remaining 50% Balance",
        "source": "front-desk",
        "method": payment.get("method"),
        "amount": float(money(payment.get("amount"))),
        "roomBalance": float(money(payment.get("room_balance_amount"))),
        "otherCharges": charges,
        "otherChargesTotal": float(money(payment.get("other_charges_total"))),
        "reference": payment.get("reference"),
        "cashTendered": float(money(payment.get("cash_tendered"))),
        "changeGiven": float(money(payment.get("change_given"))),
        "cashierId": payment.get("cashier_staff_id"),
        "cashierName": resolved_cashier.get("full_name"),
        "processedAt": payment.get("processed_at") or payment.get("created_at"),
        "paymentTiming": payment_timing,
        "paymentTimingLabel": PAYMENT_TIMING_LABELS.get(payment_timing or "", ""),
        "notes": clean_notes,
        "status": payment.get("status"),
        "paymentIntentId": payment.get("payment_intent_id"),
    }


def paymongo_request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if not PAYMONGO_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="PAYMONGO_SECRET_KEY is not configured in backend/.env.",
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:255]

    try:
        response = requests.request(
            method=method,
            url=url,
            auth=(PAYMONGO_SECRET_KEY, ""),
            headers=headers,
            json=payload,
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="The PayMongo service could not be reached.",
        ) from error

    if not response.ok:
        try:
            body = response.json()
            detail = (
                (body.get("errors") or [{}])[0].get("detail")
                or body.get("message")
                or "PayMongo rejected the request."
            )
        except Exception:
            detail = "PayMongo rejected the request."
        raise HTTPException(status_code=502, detail=detail)

    try:
        result = response.json()
    except ValueError as error:
        raise HTTPException(status_code=502, detail="PayMongo returned invalid JSON.") from error

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="PayMongo returned an invalid response.")
    return result


def payment_intent_state(intent: dict[str, Any]) -> dict[str, Any]:
    attributes = intent.get("attributes", {}) or {}
    status_value = str(attributes.get("status") or "awaiting_payment").lower()
    payments = attributes.get("payments") or []
    paid_payment = None
    if isinstance(payments, list):
        for payment in reversed(payments):
            if str((payment.get("attributes") or {}).get("status", "")).lower() == "paid":
                paid_payment = payment
                break
    return {
        "status": status_value,
        "paid": status_value == "succeeded" or paid_payment is not None,
        "payment": paid_payment,
    }


def verify_paymongo_signature(raw_body: bytes, signature_header: str) -> None:
    if not PAYMONGO_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="PAYMONGO_WEBHOOK_SECRET is not configured.")

    parts: dict[str, str] = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip().lower()] = value.strip()

    timestamp = parts.get("t", "")
    if not timestamp:
        raise HTTPException(status_code=401, detail="Invalid PayMongo webhook signature.")

    try:
        timestamp_value = int(timestamp)
    except ValueError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid PayMongo webhook timestamp.",
        ) from error

    if abs(int(time_module.time()) - timestamp_value) > 300:
        raise HTTPException(
            status_code=401,
            detail="Expired PayMongo webhook signature.",
        )

    expected = hmac.new(
        PAYMONGO_WEBHOOK_SECRET.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()

    signature = parts.get("te") if PAYMONGO_SECRET_KEY.startswith("sk_test_") else parts.get("li")
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid PayMongo webhook signature.")


def manual_front_desk_settlement(
    *,
    booking: dict[str, Any],
    cashier: dict[str, Any],
    method: Literal[
        "Cash",
        "QRPh",
    ],
    payer_name: str,
    other_charges: list[
        dict[str, Any]
    ],
    reference: str | None,
    cash_tendered: Decimal,
    change_given: Decimal,
    payment_intent_id: str | None,
    notes: str | None,
) -> dict[str, Any]:
    """
    Compatible fallback when the database RPC has not been installed yet.

    The included SQL migration remains recommended because it provides a real
    database transaction.
    """

    client = service_client()

    latest_booking = fetch_booking(
        str(booking["id"])
    )

    room_balance = money(
        latest_booking.get(
            "balance_amount"
        )
    )

    if room_balance <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This booking has no "
                "remaining balance."
            ),
        )

    charges_total = sum(
        (
            money(
                item.get("amount")
            )
            for item in other_charges
        ),
        Decimal("0.00"),
    )

    total_received = (
        room_balance
        + charges_total
    )

    receipt_number = (
        "TV-FD-"
        + datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        )
        + "-"
        + secrets.token_hex(
            2
        ).upper()
    )

    payment_id = ""

    try:
        payment_rows = rows(
            client.table(
                "front_desk_payments"
            )
            .insert({
                "booking_id":
                    str(
                        latest_booking[
                            "id"
                        ]
                    ),

                "receipt_number":
                    receipt_number,

                "method":
                    method,

                "amount":
                    float(
                        total_received
                    ),

                "room_balance_amount":
                    float(
                        room_balance
                    ),

                "other_charges_total":
                    float(
                        charges_total
                    ),

                "payer_name":
                    payer_name,

                "reference":
                    reference,

                "cash_tendered":
                    float(
                        cash_tendered
                    ),

                "change_given":
                    float(
                        change_given
                    ),

                "cashier_staff_id":
                    str(
                        cashier["id"]
                    ),

                "status":
                    "Paid",

                "payment_intent_id":
                    payment_intent_id,

                "processed_at":
                    now_iso(),

                "notes":
                    notes,
            })
            .select(
                FRONT_DESK_PAYMENT_SELECT
            )
            .execute()
        )

        if not payment_rows:
            raise RuntimeError(
                "The front-desk payment "
                "record was not created."
            )

        payment = payment_rows[0]

        payment_id = str(
            payment.get("id")
            or ""
        )

        charge_values = [
            {
                "front_desk_payment_id":
                    payment_id,

                "description":
                    str(
                        charge.get(
                            "description"
                        )
                        or ""
                    ).strip(),

                "amount":
                    float(
                        money(
                            charge.get(
                                "amount"
                            )
                        )
                    ),
            }
            for charge in other_charges
            if str(
                charge.get(
                    "description"
                )
                or ""
            ).strip()
        ]

        if charge_values:
            (
                client.table(
                    "front_desk_payment_items"
                )
                .insert(
                    charge_values
                )
                .execute()
            )

        current_paid = money(
            latest_booking.get(
                "amount_paid"
            )
        )

        total_amount = money(
            latest_booking.get(
                "total_amount"
            )
        )

        accommodation_paid = min(
            total_amount,
            current_paid
            + room_balance,
        )

        updated_rows = rows(
            client.table("bookings")
            .update({
                "amount_paid":
                    float(
                        accommodation_paid
                    ),

                "balance_amount":
                    0,

                "payment_status":
                    "Paid",

                "payment_message":
                    (
                        "Remaining balance "
                        "settled at the "
                        "front desk."
                    ),

                "front_desk_payment_method":
                    method,

                "front_desk_reference":
                    reference
                    or receipt_number,

                "front_desk_settled_at":
                    now_iso(),

                "front_desk_other_charges":
                    other_charges,

                "front_desk_other_charges_total":
                    float(
                        charges_total
                    ),

                "updated_at":
                    now_iso(),
            })
            .eq(
                "id",
                str(
                    latest_booking["id"]
                ),
            )
            .select("*")
            .execute()
        )

        if not updated_rows:
            raise RuntimeError(
                "The booking balance "
                "was not updated."
            )

        from feedback_service import queue_feedback_invitation
        queue_feedback_invitation(updated_rows[0], client)

        return {
            "booking":
                updated_rows[0],

            "payment":
                front_desk_payment_api(
                    payment,
                    booking=(
                        updated_rows[0]
                    ),
                    cashier=cashier,
                    client=client,
                ),
        }

    except HTTPException:
        raise

    except Exception as error:
        if payment_id:
            try:
                (
                    client.table(
                        "front_desk_payment_items"
                    )
                    .delete()
                    .eq(
                        "front_desk_payment_id",
                        payment_id,
                    )
                    .execute()
                )

                (
                    client.table(
                        "front_desk_payments"
                    )
                    .delete()
                    .eq(
                        "id",
                        payment_id,
                    )
                    .execute()
                )
            except Exception:
                logger.exception(
                    (
                        "Could not clean up "
                        "an incomplete "
                        "settlement."
                    )
                )

        logger.exception(
            (
                "Manual front-desk "
                "settlement failed."
            )
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "The settlement tables "
                "are not ready. Run "
                "database/"
                "the_villa_portal_"
                "operations.sql in "
                "Supabase SQL Editor."
            ),
        ) from error


def complete_front_desk_settlement(
    *,
    booking: dict[str, Any],
    cashier: dict[str, Any],
    method: Literal[
        "Cash",
        "QRPh",
    ],
    payer_name: str,
    other_charges: list[
        dict[str, Any]
    ],
    reference: str | None,
    cash_tendered: Decimal = Decimal(
        "0.00"
    ),
    change_given: Decimal = Decimal(
        "0.00"
    ),
    payment_intent_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    room_balance = money(
        booking.get(
            "balance_amount"
        )
    )

    charges_total = sum(
        (
            money(
                item.get("amount")
            )
            for item in other_charges
        ),
        Decimal("0.00"),
    )

    total_received = (
        room_balance
        + charges_total
    )

    payload = None

    try:
        result = (
            service_client()
            .rpc(
                (
                    "complete_front_"
                    "desk_settlement"
                ),
                {
                    "p_booking_id":
                        str(
                            booking["id"]
                        ),

                    "p_cashier_staff_id":
                        str(
                            cashier["id"]
                        ),

                    "p_method":
                        method,

                    "p_payer_name":
                        payer_name,

                    "p_amount":
                        float(
                            total_received
                        ),

                    "p_room_balance":
                        float(
                            room_balance
                        ),

                    "p_other_charges":
                        other_charges,

                    "p_reference":
                        reference,

                    "p_cash_tendered":
                        float(
                            cash_tendered
                        ),

                    "p_change_given":
                        float(
                            change_given
                        ),

                    "p_payment_intent_id":
                        payment_intent_id,

                    "p_notes":
                        notes,
                },
            )
            .execute()
        )

        payload = attr(
            result,
            "data",
            None,
        )

        if (
            isinstance(
                payload,
                list,
            )
            and payload
        ):
            payload = payload[0]

    except Exception as error:
        message = str(
            error
        ).lower()

        missing_rpc = any(
            marker in message
            for marker in (
                "pgrst202",
                "schema cache",
                "could not find",
                "does not exist",
                "undefined function",
            )
        )

        if not missing_rpc:
            logger.exception(
                (
                    "Database settlement "
                    "transaction failed."
                )
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "The settlement "
                    "transaction failed."
                ),
            ) from error

        logger.warning(
            (
                "Settlement RPC is not "
                "installed; using the "
                "compatible fallback."
            )
        )

        return manual_front_desk_settlement(
            booking=booking,
            cashier=cashier,
            method=method,
            payer_name=payer_name,
            other_charges=(
                other_charges
            ),
            reference=reference,
            cash_tendered=(
                cash_tendered
            ),
            change_given=(
                change_given
            ),
            payment_intent_id=(
                payment_intent_id
            ),
            notes=notes,
        )

    if not isinstance(
        payload,
        dict,
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "Settlement transaction "
                "returned no result."
            ),
        )

    updated_booking = payload.get(
        "booking"
    )

    payment = payload.get(
        "payment"
    )

    if (
        not isinstance(
            updated_booking,
            dict,
        )
        or not isinstance(
            payment,
            dict,
        )
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "Settlement transaction "
                "was incomplete."
            ),
        )

    from feedback_service import queue_feedback_invitation
    queue_feedback_invitation(updated_booking)

    notify_admins(
        (
            "Front Desk Payment "
            "Completed"
        ),
        (
            f"{updated_booking.get('customer_name')} "
            f"paid {float(total_received):,.2f} "
            f"through {method} for "
            f"{updated_booking.get('booking_code')}."
        ),
        notification_type=(
            "front-desk-payment"
        ),
        icon="payment",
        payment_transaction_id=str(
            payment.get("id")
        ),
    )

    return {
        "booking":
            updated_booking,

        "payment":
            front_desk_payment_api(
                payment,
                booking=(
                    updated_booking
                ),
                cashier=cashier,
            ),
    }


# ============================================================
# ADMIN BOOKING LIFECYCLE
# ============================================================

@admin_router.get("/bookings")
def list_admin_bookings(context: dict[str, Any] = Depends(require_admin)):
    client = service_client()
    booking_rows = load_bookings_with_payments(client)
    payment_timing_rows = load_payment_timing_events(client)
    return {
        "data": apply_payment_timing_preferences(
            booking_rows,
            payment_timing_rows,
        )
    }


def booking_stay_state(booking: dict[str, Any]) -> str:
    """
    Resolve the operational stay state without assuming every deployment has
    exactly the same lifecycle columns.

    `stay_status` is preferred when available. Older deployments can still
    fall back to `booking_status`.
    """
    raw = str(
        booking.get("stay_status")
        or booking.get("booking_status")
        or ""
    ).strip().lower()

    if raw in {
        "checked in",
        "checked-in",
        "check in",
        "check-in",
        "checkin",
    }:
        return "Checked In"

    if raw in {
        "checked out",
        "checked-out",
        "check out",
        "check-out",
        "checkout",
        "completed",
    }:
        return "Checked Out"

    return "Not Checked In"


def update_booking_lifecycle(
    *,
    booking_id: str,
    booking_status: str,
    stay_status: str,
    timestamp_field: str,
    actor_field: str,
    actor_staff_id: str | None,
) -> dict[str, Any]:
    """
    Update the booking lifecycle while remaining compatible with deployments
    that may not yet have every optional lifecycle/audit column.

    The function tries the richest payload first, then progressively falls
    back to the core status fields. A missing optional column must not turn a
    valid check-in/check-out into an HTTP 500.
    """
    client = service_client()
    now = now_iso()

    attempts: list[dict[str, Any]] = [
        {
            "booking_status": booking_status,
            "stay_status": stay_status,
            timestamp_field: now,
            actor_field: actor_staff_id,
            "updated_at": now,
        },
        {
            "booking_status": booking_status,
            "stay_status": stay_status,
            timestamp_field: now,
            "updated_at": now,
        },
        {
            "booking_status": booking_status,
            "stay_status": stay_status,
            "updated_at": now,
        },
        {
            "stay_status": stay_status,
            timestamp_field: now,
            "updated_at": now,
        },
        {
            "booking_status": booking_status,
            timestamp_field: now,
            "updated_at": now,
        },
        {
            "stay_status": stay_status,
            "updated_at": now,
        },
        {
            "booking_status": booking_status,
            "updated_at": now,
        },
    ]

    unique_attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in attempts:
        clean_payload = {
            key: value
            for key, value in payload.items()
            if value is not None
        }
        signature = json.dumps(clean_payload, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        unique_attempts.append(clean_payload)

    last_error: Exception | None = None

    for index, payload in enumerate(unique_attempts, start=1):
        try:
            result = rows(
                client.table("bookings")
                .update(payload)
                .eq("id", booking_id)
                .select("*")
                .execute()
            )

            updated = result[0] if result else fetch_booking(booking_id)

            logger.info(
                "Booking %s lifecycle updated on compatibility attempt %s.",
                booking_id,
                index,
            )
            return updated

        except Exception as error:
            last_error = error
            logger.warning(
                "Booking %s lifecycle update attempt %s failed with fields %s: %s",
                booking_id,
                index,
                ",".join(payload.keys()),
                error,
            )

    raise HTTPException(
        status_code=500,
        detail=(
            "The booking stay status could not be updated. "
            "Check the backend terminal and confirm the bookings table supports "
            "booking_status or stay_status."
        ),
    ) from last_error


def sync_booking_tasks_after_lifecycle(
    *,
    booking_id: str,
    booking_status: str,
    payment_status: Any,
    now: str,
) -> None:
    """
    Assignment synchronization is helpful but must never make the actual guest
    lifecycle action fail. Some deployments do not have admin_tasks installed
    yet or may have an older task schema.
    """
    try:
        (
            service_client()
            .table("admin_tasks")
            .update(
                {
                    "booking_status": booking_status,
                    "booking_payment_status": payment_status,
                    "updated_at": now,
                }
            )
            .eq("booking_id", booking_id)
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Booking %s was updated, but related admin tasks could not be synced: %s",
            booking_id,
            error,
        )


@admin_router.post("/bookings/{booking_id}/check-in")
def check_in_booking(
    booking_id: UUID,
    data: BookingLifecycleRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    booking_id_value = str(booking_id)
    booking = fetch_booking(booking_id_value)
    current_booking_status = str(booking.get("booking_status") or "")
    current_stay_state = booking_stay_state(booking)

    if current_stay_state == "Checked Out":
        raise HTTPException(
            status_code=409,
            detail="This stay has already been checked out.",
        )

    if current_stay_state == "Checked In":
        return {
            "message": "The guest is already checked in.",
            "data": attach_payment_timing(booking),
        }

    if current_booking_status and current_booking_status not in {
        "Confirmed",
        "Checked In",
    }:
        raise HTTPException(
            status_code=409,
            detail="Only a confirmed booking can be checked in.",
        )

    if not booking_initial_payment_verified(booking):
        raise HTTPException(
            status_code=409,
            detail="The required customer payment must be verified before check-in.",
        )

    # Server-side restriction: check-in is allowed only on the booked check-in
    # date, even if the frontend request is manually forged.
    enforce_booking_lifecycle_date(booking, "check_in")

    updated = update_booking_lifecycle(
        booking_id=booking_id_value,
        booking_status="Checked In",
        stay_status="Checked In",
        timestamp_field="checked_in_at",
        actor_field="checked_in_by_staff_id",
        actor_staff_id=str(context["account"].get("id") or "") or None,
    )

    now = str(
        updated.get("checked_in_at")
        or updated.get("updated_at")
        or now_iso()
    )

    sync_booking_tasks_after_lifecycle(
        booking_id=booking_id_value,
        booking_status="Checked In",
        payment_status=updated.get("payment_status"),
        now=now,
    )

    record_booking_event(
        booking_id_value,
        "guest_checked_in",
        f"{updated.get('customer_name')} checked in to {updated.get('villa_name')}.",
        from_status=current_booking_status or current_stay_state,
        to_status="Checked In",
        actor_type="admin",
        actor_staff_id=str(context["account"].get("id") or "") or None,
        metadata={"notes": data.notes},
    )

    return {
        "message": "Guest check-in completed.",
        "data": attach_payment_timing(updated),
    }


def choose_turnover_staff() -> dict[str, Any] | None:
    """
    Turnover assignment is secondary to checkout. If staff/task tables are not
    available, checkout still succeeds and the warning is logged.
    """
    client = service_client()

    try:
        housekeeping = rows(
            client.table("staff_accounts")
            .select(STAFF_SELECT)
            .eq("role", "staff")
            .eq("department", "Housekeeping")
            .eq("is_active", True)
            .eq("account_status", "Active")
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Housekeeping staff could not be loaded for automatic turnover: %s",
            error,
        )
        return None

    if not housekeeping:
        return None

    try:
        active_tasks = rows(
            client.table("admin_tasks")
            .select("assigned_staff_id,status")
            .in_("status", ["Pending", "In Progress", "Pending Review"])
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Task workload could not be loaded for automatic turnover: %s",
            error,
        )
        active_tasks = []

    workload: dict[str, int] = {}
    for task in active_tasks:
        key = str(task.get("assigned_staff_id"))
        workload[key] = workload.get(key, 0) + 1

    return min(
        housekeeping,
        key=lambda item: workload.get(str(item["id"]), 0),
    )


def pending_front_desk_intents(booking_id: str) -> list[dict[str, Any]]:
    try:
        return rows(
            service_client()
            .table("front_desk_payment_intents")
            .select("id")
            .eq("booking_id", booking_id)
            .in_("status", ["awaiting_payment", "processing"])
            .limit(1)
            .execute()
        )
    except Exception as error:
        logger.warning(
            "Pending QRPh intents could not be checked for booking %s: %s",
            booking_id,
            error,
        )
        return []


def create_checkout_turnover_task(
    *,
    booking_id: str,
    updated: dict[str, Any],
    context: dict[str, Any],
    notes: str | None,
    now: str,
) -> dict[str, Any] | None:
    housekeeping_staff = choose_turnover_staff()
    if not housekeeping_staff:
        return None

    try:
        code = task_code()
        checklist = [
            {"id": f"{code}-1", "label": "Collect used linens and towels", "done": False},
            {"id": f"{code}-2", "label": "Deep-clean bedrooms and bathrooms", "done": False},
            {"id": f"{code}-3", "label": "Clean kitchen and dining areas", "done": False},
            {"id": f"{code}-4", "label": "Inspect guest-use items and report damage", "done": False},
            {"id": f"{code}-5", "label": "Restock supplies and prepare the villa", "done": False},
        ]

        task_result = rows(
            service_client()
            .table("admin_tasks")
            .insert(
                {
                    "task_code": code,
                    "booking_id": booking_id,
                    "booking_code": updated.get("booking_code"),
                    "booking_status": updated.get("booking_status"),
                    "booking_payment_status": updated.get("payment_status"),
                    "booking_check_in": updated.get("check_in_date"),
                    "booking_check_out": updated.get("check_out_date"),
                    "villa_name": updated.get("villa_name"),
                    "guest_name": updated.get("customer_name"),
                    "guest_phone": updated.get("customer_phone"),
                    "guest_email": updated.get("customer_email"),
                    "assigned_staff_id": housekeeping_staff["id"],
                    "created_by_staff_id": context["account"]["id"],
                    "updated_by_staff_id": context["account"]["id"],
                    "assignment_type": "housekeeping-turnover",
                    "title": f"Post-checkout turnover – {updated.get('villa_name')}",
                    "description": (
                        "Complete the post-checkout villa turnover, document damages, "
                        "and prepare the villa for the next reservation."
                    ),
                    "department": "Housekeeping",
                    "assigned_role": housekeeping_staff.get("position"),
                    "priority": "High",
                    "due_date": updated.get("check_out_date") or date.today().isoformat(),
                    "due_time": "14:00:00",
                    "status": "Pending",
                    "progress": 0,
                    "checklist": checklist,
                    "attachments": [],
                    "notes": notes,
                    "source": "automatic-checkout-turnover",
                    "from_booking": True,
                    "status_history": [
                        {
                            "id": f"AUDIT-{secrets.token_hex(6)}",
                            "status": "Pending",
                            "actor": context["account"]["full_name"],
                            "actorStaffId": context["account"]["id"],
                            "note": "Turnover assignment created automatically after checkout.",
                            "timestamp": now,
                        }
                    ],
                }
            )
            .select(TASK_SELECT)
            .execute()
        )

        if not task_result:
            return None

        turnover_task = task_api(task_result[0], housekeeping_staff)

        try:
            create_notification(
                str(housekeeping_staff["id"]),
                "Post-checkout Turnover",
                (
                    f"Prepare {updated.get('villa_name')} after "
                    f"{updated.get('booking_code')} checkout."
                ),
                notification_type="assignment",
                icon="task",
                task_id=str(task_result[0]["id"]),
            )
        except Exception as error:
            logger.warning(
                "Checkout succeeded but turnover notification could not be created: %s",
                error,
            )

        return turnover_task

    except Exception as error:
        logger.warning(
            "Checkout succeeded but the automatic turnover task could not be created: %s",
            error,
        )
        return None


@admin_router.post("/bookings/{booking_id}/checkout")
def checkout_booking(
    booking_id: UUID,
    data: BookingLifecycleRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    booking_id_value = str(booking_id)
    booking = fetch_booking(booking_id_value)
    current_booking_status = str(booking.get("booking_status") or "")
    current_stay_state = booking_stay_state(booking)

    if current_stay_state == "Checked Out" or current_booking_status == "Completed":
        from feedback_service import queue_feedback_invitation
        queue_feedback_invitation(booking)
        return {
            "message": "The booking is already checked out.",
            "data": attach_payment_timing(booking),
        }

    if current_stay_state != "Checked In":
        raise HTTPException(
            status_code=409,
            detail="The guest must be checked in before checkout.",
        )

    # Checkout dates are unrestricted for testing; lifecycle and payment checks remain.
    enforce_booking_lifecycle_date(booking, "check_out")

    if money(booking.get("balance_amount")) > 0:
        raise HTTPException(
            status_code=409,
            detail="Settle the remaining booking balance before checkout.",
        )

    if pending_front_desk_intents(booking_id_value):
        raise HTTPException(
            status_code=409,
            detail="A QRPh settlement is still pending for this booking.",
        )

    updated = update_booking_lifecycle(
        booking_id=booking_id_value,
        booking_status="Completed",
        stay_status="Checked Out",
        timestamp_field="checked_out_at",
        actor_field="checked_out_by_staff_id",
        actor_staff_id=str(context["account"].get("id") or "") or None,
    )

    now = str(
        updated.get("checked_out_at")
        or updated.get("updated_at")
        or now_iso()
    )

    sync_booking_tasks_after_lifecycle(
        booking_id=booking_id_value,
        booking_status="Completed",
        payment_status=updated.get("payment_status"),
        now=now,
    )

    from feedback_service import queue_feedback_invitation
    queue_feedback_invitation(updated)

    turnover_task = create_checkout_turnover_task(
        booking_id=booking_id_value,
        updated=updated,
        context=context,
        notes=data.notes,
        now=now,
    )

    record_booking_event(
        booking_id_value,
        "guest_checked_out",
        f"{updated.get('customer_name')} checked out from {updated.get('villa_name')}.",
        from_status=current_booking_status or current_stay_state,
        to_status="Completed",
        actor_type="admin",
        actor_staff_id=str(context["account"].get("id") or "") or None,
        metadata={
            "notes": data.notes,
            "turnover_task_id": turnover_task.get("id") if turnover_task else None,
        },
    )

    return {
        "message": "Guest checkout completed.",
        "data": attach_payment_timing(updated),
        "turnoverTask": turnover_task,
    }


# ============================================================
# FRONT DESK SETTLEMENT ENDPOINTS
# ============================================================

@front_desk_router.put("/bookings/{booking_id}/payment-timing")
def set_front_desk_payment_timing(
    booking_id: UUID,
    data: PaymentTimingPreferenceRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    booking = fetch_booking(str(booking_id))
    timing = save_payment_timing_preference(
        booking=booking,
        cashier=context["account"],
        payment_timing=data.payment_timing,
    )

    updated = dict(booking)
    updated["front_desk_balance_timing"] = timing

    return {
        "message": (
            f"Remaining balance scheduled for "
            f"{PAYMENT_TIMING_LABELS[timing]}."
        ),
        "data": {
            "booking": updated,
            "paymentTiming": timing,
            "paymentTimingLabel": PAYMENT_TIMING_LABELS[timing],
        },
    }


@front_desk_router.get("/payments")
def list_front_desk_payments(context: dict[str, Any] = Depends(require_admin)):
    client = service_client()
    payment_rows = rows(
        client.table("front_desk_payments")
        .select(FRONT_DESK_PAYMENT_SELECT)
        .order("processed_at", desc=True)
        .limit(3000)
        .execute()
    )
    from read_batches import parallel_reads
    def records_by_ids(table, columns, ids):
        client = service_client()
        found = {}
        ids = sorted(set(ids))
        for start in range(0, len(ids), 100):
            for item in rows(client.table(table).select(columns).in_("id", ids[start:start + 100]).execute()):
                found[str(item["id"])] = item
        return found
    loaded = parallel_reads({
        "bookings": lambda: records_by_ids("bookings", "id,booking_code,customer_name,villa_name", [str(p["booking_id"]) for p in payment_rows]),
        "staff": lambda: records_by_ids("staff_accounts", "id,full_name", [str(p["cashier_staff_id"]) for p in payment_rows if p.get("cashier_staff_id")]),
        "items": lambda: load_front_desk_items_map(service_client(), [str(p["id"]) for p in payment_rows]),
    })
    return {"data": [front_desk_payment_api(
        item, client=client, booking=loaded["bookings"].get(str(item.get("booking_id")), {}),
        cashier=loaded["staff"].get(str(item.get("cashier_staff_id")), {}),
        charge_rows=loaded["items"].get(str(item["id"]), []),
    ) for item in payment_rows]}



@front_desk_router.post("/bookings/{booking_id}/cash-settlement")
def cash_settlement(
    booking_id: UUID,
    data: CashSettlementRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    booking = fetch_booking(str(booking_id))
    payment_timing = validate_payment_timing_for_booking(booking, data.payment_timing)
    if str(booking.get("payment_choice", "")).lower() != "half":
        raise HTTPException(status_code=409, detail="Front-desk settlement is for 50% downpayment bookings.")
    if not booking_initial_payment_verified(booking):
        raise HTTPException(status_code=409, detail="The customer downpayment has not been verified.")

    room_balance = money(booking.get("balance_amount"))
    if room_balance <= 0:
        raise HTTPException(status_code=409, detail="This booking has no remaining balance.")

    charges = [
        {"description": item.description.strip(), "amount": float(money(item.amount))}
        for item in data.other_charges
    ]
    charges_total = sum((money(item["amount"]) for item in charges), Decimal("0.00"))
    amount_due = room_balance + charges_total
    cash_tendered = money(data.cash_tendered)
    if cash_tendered < amount_due:
        raise HTTPException(
            status_code=409,
            detail=f"Cash is insufficient by PHP {float(amount_due - cash_tendered):,.2f}.",
        )

    receipt_reference = f"CASH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"
    result = complete_front_desk_settlement(
        booking=booking,
        cashier=context["account"],
        method="Cash",
        payer_name=data.payer_name.strip(),
        other_charges=charges,
        reference=receipt_reference,
        cash_tendered=cash_tendered,
        change_given=cash_tendered - amount_due,
        notes=encode_settlement_notes(data.notes, payment_timing),
    )
    record_payment_timing_event(
        booking=result.get("booking") or booking,
        cashier=context["account"],
        payment=result.get("payment"),
        payment_timing=payment_timing,
        method="Cash",
    )
    return {"message": "Cash settlement completed.", "data": result}


@front_desk_router.post("/bookings/{booking_id}/qrph-intent")
def create_qrph_intent(
    booking_id: UUID,
    data: QrPhSettlementRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    if not PAYMONGO_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="PAYMONGO_PUBLIC_KEY is not configured.")

    booking = fetch_booking(str(booking_id))
    payment_timing = validate_payment_timing_for_booking(booking, data.payment_timing)
    if str(booking.get("payment_choice", "")).lower() != "half":
        raise HTTPException(status_code=409, detail="Front-desk settlement is for 50% downpayment bookings.")
    if not booking_initial_payment_verified(booking):
        raise HTTPException(status_code=409, detail="The customer downpayment has not been verified.")

    room_balance = money(booking.get("balance_amount"))
    if room_balance <= 0:
        raise HTTPException(status_code=409, detail="This booking has no remaining balance.")

    charges = [
        {"description": item.description.strip(), "amount": float(money(item.amount))}
        for item in data.other_charges
    ]
    charges_total = sum((money(item["amount"]) for item in charges), Decimal("0.00"))
    amount_due = room_balance + charges_total
    nonce = secrets.token_hex(6).upper()
    reference = f"{booking.get('booking_code')}-FD-{nonce}"[:255]

    result = paymongo_request(
        "POST",
        PAYMONGO_PAYMENT_INTENTS_URL,
        payload={
            "data": {
                "attributes": {
                    "amount": centavos(amount_due),
                    "payment_method_allowed": ["qrph"],
                    "currency": "PHP",
                    "capture_type": "automatic",
                    "description": f"The Villa front desk settlement {booking.get('booking_code')}",
                    "statement_descriptor": "THE VILLA",
                    "metadata": {
                        "booking_id": str(booking_id),
                        "booking_code": booking.get("booking_code"),
                        "cashier_staff_id": str(context["account"]["id"]),
                        "reference": reference,
                        "purpose": "front_desk_settlement",
                        "payment_timing": payment_timing,
                    },
                }
            }
        },
        idempotency_key=f"front-desk-{booking_id}-{centavos(amount_due)}-{nonce}",
    )

    intent = result.get("data", {}) or {}
    attributes = intent.get("attributes", {}) or {}
    intent_id = str(intent.get("id") or "").strip()
    client_key = str(attributes.get("client_key") or "").strip()
    if not intent_id or not client_key:
        raise HTTPException(status_code=502, detail="PayMongo returned an incomplete Payment Intent.")

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    service_client().table("front_desk_payment_intents").insert(
        {
            "booking_id": str(booking_id),
            "cashier_staff_id": context["account"]["id"],
            "payment_intent_id": intent_id,
            "client_key": client_key,
            "reference": reference,
            "payer_name": data.payer_name.strip(),
            "room_balance_amount": float(room_balance),
            "other_charges": charges,
            "other_charges_total": float(charges_total),
            "expected_amount": float(amount_due),
            "currency": "PHP",
            "status": str(attributes.get("status") or "awaiting_payment"),
            "expires_at": expires_at,
            "notes": encode_settlement_notes(data.notes, payment_timing),
            "raw_payload": result,
        }
    ).execute()

    return {
        "message": "PayMongo QRPh Payment Intent created.",
        "data": {
            "payment_intent_id": intent_id,
            "client_key": client_key,
            "public_key": PAYMONGO_PUBLIC_KEY,
            "amount": float(amount_due),
            "currency": "PHP",
            "reference": reference,
            "expires_at": expires_at,
        },
    }


def finalize_qrph_intent(payment_intent_id: str) -> dict[str, Any]:
    client = service_client()
    intent_rows = rows(
        client.table("front_desk_payment_intents")
        .select("*")
        .eq("payment_intent_id", payment_intent_id)
        .limit(1)
        .execute()
    )
    if not intent_rows:
        raise HTTPException(status_code=404, detail="Front-desk QRPh intent was not found.")

    stored_intent = intent_rows[0]
    existing_payment = rows(
        client.table("front_desk_payments")
        .select(FRONT_DESK_PAYMENT_SELECT)
        .eq("payment_intent_id", payment_intent_id)
        .limit(1)
        .execute()
    )
    if existing_payment:
        booking = fetch_booking(str(stored_intent["booking_id"]))
        return {
            "booking": booking,
            "payment": front_desk_payment_api(existing_payment[0], booking=booking),
        }

    result = paymongo_request(
        "GET",
        f"{PAYMONGO_PAYMENT_INTENTS_URL}/{payment_intent_id}",
    )
    intent = result.get("data", {}) or {}
    state = payment_intent_state(intent)
    current_status = state["status"]

    client.table("front_desk_payment_intents").update(
        {
            "status": current_status,
            "raw_payload": result,
            "updated_at": now_iso(),
        }
    ).eq("payment_intent_id", payment_intent_id).execute()

    if not state["paid"]:
        return {
            "booking": fetch_booking(str(stored_intent["booking_id"])),
            "payment": {
                "paymentIntentId": payment_intent_id,
                "status": current_status,
                "expiresAt": stored_intent.get("expires_at"),
            },
        }

    payment = state.get("payment") or {}
    payment_attributes = payment.get("attributes", {}) or {}
    paid_amount = money(payment_attributes.get("amount", 0)) / Decimal("100")
    expected_amount = money(stored_intent.get("expected_amount"))
    if paid_amount and paid_amount != expected_amount:
        client.table("front_desk_payment_intents").update(
            {"status": "amount_mismatch", "updated_at": now_iso()}
        ).eq("payment_intent_id", payment_intent_id).execute()
        return {
            "booking": fetch_booking(str(stored_intent["booking_id"])),
            "payment": {
                "paymentIntentId": payment_intent_id,
                "status": "amount_mismatch",
            },
        }

    booking = fetch_booking(str(stored_intent["booking_id"]))
    cashier = fetch_staff(str(stored_intent["cashier_staff_id"]))
    stored_payment_timing, _ = decode_settlement_notes(stored_intent.get("notes"))
    paymongo_metadata = (attributes.get("metadata") or {}) if isinstance(attributes, dict) else {}
    payment_timing = normalize_payment_timing(
        stored_payment_timing or paymongo_metadata.get("payment_timing") or "check_in"
    )
    completed = complete_front_desk_settlement(
        booking=booking,
        cashier=cashier,
        method="QRPh",
        payer_name=stored_intent.get("payer_name") or booking.get("customer_name") or "Villa Guest",
        other_charges=stored_intent.get("other_charges") or [],
        reference=stored_intent.get("reference") or payment_intent_id,
        payment_intent_id=payment_intent_id,
        notes=stored_intent.get("notes"),
    )
    record_payment_timing_event(
        booking=completed.get("booking") or booking,
        cashier=cashier,
        payment=completed.get("payment"),
        payment_timing=payment_timing,
        method="QRPh",
    )
    client.table("front_desk_payment_intents").update(
        {
            "status": "paid",
            "paid_at": now_iso(),
            "updated_at": now_iso(),
        }
    ).eq("payment_intent_id", payment_intent_id).execute()
    return completed


@front_desk_router.get("/payments/{payment_intent_id}/status")
def qrph_status(
    payment_intent_id: str,
    context: dict[str, Any] = Depends(require_admin),
):
    result = finalize_qrph_intent(payment_intent_id)
    return {"data": result}


@front_desk_router.post("/paymongo/webhook")
async def front_desk_paymongo_webhook(request: Request):
    raw_body = await request.body()
    signature = (
        request.headers.get("Paymongo-Signature")
        or request.headers.get("paymongo-signature")
        or request.headers.get("X-Paymongo-Signature")
        or ""
    ).strip()
    verify_paymongo_signature(raw_body, signature)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON.") from error

    event = payload.get("data", {}) or {}
    attributes = event.get("attributes", {}) or {}
    event_type = str(attributes.get("type") or event.get("type") or "")
    resource = attributes.get("data", {}) or {}

    payment_intent_id = ""
    if event_type == "payment.paid":
        payment_attributes = resource.get("attributes", {}) or {}
        payment_intent_id = str(
            payment_attributes.get("payment_intent_id")
            or (payment_attributes.get("payment_intent") or {}).get("id")
            or ""
        )
    elif event_type in {"payment_intent.succeeded", "payment_intent.payment_failed"}:
        payment_intent_id = str(resource.get("id") or "")

    if not payment_intent_id:
        return {"received": True, "ignored": True, "event_type": event_type}

    stored = rows(
        service_client()
        .table("front_desk_payment_intents")
        .select("id")
        .eq("payment_intent_id", payment_intent_id)
        .limit(1)
        .execute()
    )
    if not stored:
        return {"received": True, "ignored": True, "event_type": event_type}

    result = finalize_qrph_intent(payment_intent_id)
    return {"received": True, "event_type": event_type, "data": result}

# ============================================================
# ADMIN MANUAL BOOKINGS — Messenger / assisted reservations
# ============================================================
@admin_router.get("/manual-bookings/availability")
def manual_booking_availability(
    check_in_date: date,
    context: dict[str, Any] = Depends(require_admin),
):
    # Same source of truth and same overlap rules as public BookForm.
    from booking import public_booking_availability
    return public_booking_availability(check_in_date=check_in_date, guest_count=1)


@admin_router.get("/manual-bookings/airbnb-availability")
def manual_booking_airbnb_availability(
    check_in_date: date,
    check_out_date: date,
    guest_count: int = Query(ge=1, le=32),
    context: dict[str, Any] = Depends(require_admin),
):
    if check_in_date < villa_business_today():
        raise HTTPException(status_code=422, detail="Choose today or a future check-in date.")
    if check_out_date <= check_in_date:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in.")
    if (check_out_date - check_in_date).days > 63:
        raise HTTPException(status_code=422, detail="Availability can be checked for up to 63 nights.")

    from booking import public_booking_calendar_availability

    calendar = public_booking_calendar_availability(
        start_date=check_in_date,
        end_date=check_out_date - timedelta(days=1),
        guest_count=guest_count,
    )
    catalog = get_villa_catalog_map(service_client())
    nights = calendar["days"]
    available_sets = [
        set(day["available_villa_ids"])
        for day in nights.values()
    ]
    available_ids = set.intersection(*available_sets) if available_sets else set()
    villas = []
    for villa_id, villa in catalog.items():
        is_available = villa_id in available_ids
        was_booked = any(villa_id in day.get("booked_villa_ids", []) for day in nights.values())
        airbnb_blocked = any(
            villa_id in day.get("airbnb_blocked_villa_ids", [])
            for day in nights.values()
        )
        unavailable = any(
            villa_id in day.get("unavailable_villa_ids", [])
            for day in nights.values()
        )
        reasons = []
        if airbnb_blocked:
            reasons.append("Airbnb hold or stay for part of the stay")
        if was_booked:
            reasons.append("Booked for part of the stay")
        if unavailable:
            reasons.append("Maintenance or unavailable")
        villas.append({
            "villa_id": villa_id,
            "villa_name": villa["name"],
            "capacity": villa["capacity"],
            "available": is_available,
            "reason": "Available for all nights" if is_available else ", ".join(reasons or ["Maintenance or unavailable"]),
        })

    total_capacity = sum(villa["capacity"] for villa in villas if villa["available"])
    return {
        "check_in_date": check_in_date.isoformat(),
        "check_out_date": check_out_date.isoformat(),
        "nights": (check_out_date - check_in_date).days,
        "guest_count": guest_count,
        "available": total_capacity >= guest_count,
        "total_available_capacity": total_capacity,
        "available_villa_ids": sorted(available_ids),
        "villas": villas,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@admin_router.get("/manual-bookings/airbnb-stays")
def list_manual_airbnb_stays(
    context: dict[str, Any] = Depends(require_admin),
):
    from booking import _active_airbnb_stays

    client = service_client()
    stays = _active_airbnb_stays(client)
    catalog = get_villa_catalog_map(client)
    today = villa_business_today()
    data = []
    for stay in stays:
        if date.fromisoformat(str(stay["check_out_date"])[:10]) < today:
            continue
        data.append({
            **stay,
            "villa_names": [
                catalog[villa_id]["name"]
                for villa_id in stay.get("villa_ids") or []
                if villa_id in catalog
            ],
        })
    data.sort(key=lambda stay: (stay["check_in_date"], stay["created_at"]))
    return {"data": data}


@admin_router.post("/manual-bookings/airbnb-stays", status_code=status.HTTP_201_CREATED)
def create_manual_airbnb_stay_hold(
    data: AirbnbStayHoldRequest,
    context: dict[str, Any] = Depends(require_admin),
):
    if data.check_in_date < villa_business_today():
        raise HTTPException(status_code=422, detail="Choose today or a future check-in date.")
    if data.check_out_date <= data.check_in_date:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in.")
    if (data.check_out_date - data.check_in_date).days > 63:
        raise HTTPException(status_code=422, detail="Availability can be checked for up to 63 nights.")

    client = service_client()
    check = manual_booking_airbnb_availability(
        check_in_date=data.check_in_date,
        check_out_date=data.check_out_date,
        guest_count=data.guest_count,
        context=context,
    )
    selected_ids = set(data.villa_ids)
    selected_villas = {
        villa["villa_id"]: villa
        for villa in check["villas"]
        if villa["villa_id"] in selected_ids
    }
    if len(selected_villas) != len(selected_ids):
        raise HTTPException(status_code=422, detail="One or more selected villas do not exist.")
    if any(not villa["available"] for villa in selected_villas.values()):
        raise HTTPException(status_code=409, detail="A selected villa is no longer available for every night.")
    if sum(villa["capacity"] for villa in selected_villas.values()) < data.guest_count:
        raise HTTPException(status_code=422, detail="The selected villas cannot accommodate all guests.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=10)
    stay_id = str(uuid4())
    actor_id = str(context["account"]["id"])
    try:
        client.rpc("create_airbnb_stay_hold", {
            "p_id": stay_id,
            "p_check_in_date": data.check_in_date.isoformat(),
            "p_check_out_date": data.check_out_date.isoformat(),
            "p_guest_count": data.guest_count,
            "p_villa_ids": data.villa_ids,
            "p_created_by_staff_id": actor_id,
            "p_expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as error:
        message = str(error).lower()
        if "conflict" in message or "no longer available" in message:
            raise HTTPException(status_code=409, detail="Those dates or villas were just reserved. Check availability again.") from error
        logger.exception("Could not create an Airbnb availability hold.")
        raise HTTPException(
            status_code=503,
            detail="The Airbnb hold could not be saved. Apply the Airbnb stay database migration and retry.",
        ) from error

    villa_names = [selected_villas[villa_id]["villa_name"] for villa_id in data.villa_ids]
    return {
        "message": "A 10-minute hold was created. Accept the request on Airbnb, then confirm this stay here.",
        "data": {
            "id": stay_id,
            "check_in_date": data.check_in_date.isoformat(),
            "check_out_date": data.check_out_date.isoformat(),
            "guest_count": data.guest_count,
            "villa_ids": data.villa_ids,
            "villa_names": villa_names,
            "status": "held",
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat(),
        },
    }


@admin_router.post("/manual-bookings/airbnb-stays/{stay_id}/confirm")
def confirm_manual_airbnb_stay(
    stay_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    saved = rows(
        service_client().table("airbnb_stays")
        .update({
            "status": "confirmed",
            "expires_at": None,
            "updated_by_staff_id": str(context["account"]["id"]),
            "updated_at": now,
        })
        .eq("id", str(stay_id))
        .eq("status", "held")
        .gt("expires_at", now)
        .select("*")
        .execute()
    )
    if not saved:
        raise HTTPException(status_code=409, detail="This hold expired or was already handled. Check availability again.")
    return {"message": "Airbnb stay confirmed and dates remain blocked.", "data": saved[0]}


@admin_router.post("/manual-bookings/airbnb-stays/{stay_id}/release")
def release_manual_airbnb_stay(
    stay_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    saved = rows(
        service_client().table("airbnb_stays")
        .update({
            "status": "released",
            "expires_at": None,
            "updated_by_staff_id": str(context["account"]["id"]),
            "updated_at": now,
        })
        .eq("id", str(stay_id))
        .in_("status", ["held", "confirmed"])
        .select("*")
        .execute()
    )
    if not saved:
        raise HTTPException(status_code=404, detail="The Airbnb hold or stay was not found or was already released.")
    return {"message": "Airbnb dates released from The Villa calendar.", "data": saved[0]}


@admin_router.post("/manual-bookings", status_code=status.HTTP_201_CREATED)
def create_manual_booking(
    data: ManualBookingRequest,
    request: Request,
    context: dict[str, Any] = Depends(require_admin),
):
    from booking import (
        PublicBookingCreateRequest,
        PublicCheckoutRequest,
        _prepare_public_booking,
        _create_public_booking_checkout,
    )

    # Never trust client-side prices, capacities, or availability.
    if len(data.villa_ids) != len(set(data.villa_ids)):
        raise HTTPException(status_code=422, detail="Choose each villa only once.")
    if data.check_in_date < villa_business_today():
        raise HTTPException(status_code=422, detail="Select today or a future check-in date.")

    creation = _prepare_public_booking(PublicBookingCreateRequest(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        villa_id=data.villa_ids[0],
        villa_ids=data.villa_ids,
        check_in_date=data.check_in_date,
        check_in_time="3:00 PM",
        guest_count=data.guest_count,
        notes=data.notes,
        payment_choice=data.payment_choice,
        payment_method=data.payment_method,
    ), draft_only=True)
    booking = creation["booking"]
    booking_id = str(booking["id"])

    # Pending checkouts are isolated from bookings, reports, and booking history.
    expiration = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    booking["hold_expires_at"] = expiration
    client = service_client()
    # Verify staging storage exists BEFORE creating a live payment link.
    client.table("manual_booking_checkouts").insert({
        "id": booking_id,
        "booking_payload": booking,
        "created_by_staff_id": str(context["account"]["id"]),
        "expires_at": expiration,
    }).execute()
    try:
        payment = _create_public_booking_checkout(
            booking_id,
            PublicCheckoutRequest(payment_method=data.payment_method, payment_scope="selected"),
            x_booking_token=creation["booking_access_token"],
            manual_return_base_url=str(request.base_url).rstrip("/"),
            draft_booking=booking,
        )
        client.table("manual_booking_checkouts").update({
            "booking_payload": booking,
        }).eq("id", booking_id).execute()
    except Exception as error:
        logger.exception("Manual checkout setup failed for draft %s", booking_id)
        # No booking, payment ledger, acknowledgement email, or admin event was saved.
        raise HTTPException(
            status_code=502,
            detail="Payment setup could not be completed. No booking was saved. Please retry.",
        ) from error

    return {
        "message": "Checkout ready. The booking will be saved only after payment is verified.",
        "booking_id": booking_id,
        "booking_code": booking.get("booking_code"),
        "booking_status": "Pending Payment",
        "payment_status": "Unpaid",
        "payment_due": payment["amount"],
        "total_amount": booking.get("total_amount"),
        "checkout_url": payment["checkout_url"],
        "expires_at": expiration,
        "payment_method": data.payment_method,
        "booking": {key: value for key, value in booking.items()
                    if key not in {"guest_access_token_hash", "feedback_token_hash"}},
    }


@admin_router.post("/manual-bookings/{booking_id}/sync-payment")
def sync_admin_manual_booking_payment(
    booking_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    # Secure PayMongo verification, never client-authorized payment marking.
    from booking import sync_manual_checkout_payment
    result = sync_manual_checkout_payment(str(booking_id))
    booking = result["booking"]
    return {"state": result["state"], "data": {
        "id": booking["id"],
        "booking_code": booking.get("booking_code"),
        "booking_status": booking.get("booking_status"),
        "payment_status": booking.get("payment_status"),
        "amount_paid": booking.get("amount_paid"),
        "total_amount": booking.get("total_amount"),
        "balance_amount": booking.get("balance_amount"),
        "checkout_url": booking.get("paymongo_checkout_url"),
        "hold_expires_at": booking.get("hold_expires_at"),
    }}


@admin_router.get("/manual-bookings/{booking_id}")
def get_manual_booking_status(
    booking_id: UUID,
    context: dict[str, Any] = Depends(require_admin),
):
    from booking import _manual_checkout_draft
    draft = _manual_checkout_draft(service_client(), str(booking_id))
    booking = draft["booking_payload"] if draft else fetch_booking(str(booking_id))
    return {"data": {
        "id": booking["id"],
        "booking_code": booking.get("booking_code"),
        "booking_status": booking.get("booking_status"),
        "payment_status": booking.get("payment_status"),
        "amount_paid": booking.get("amount_paid"),
        "balance_amount": booking.get("balance_amount"),
        "checkout_url": booking.get("paymongo_checkout_url"),
        "hold_expires_at": booking.get("hold_expires_at"),
    }}


@admin_router.get("/guest-feedback")
def list_guest_feedback(context: dict[str, Any] = Depends(require_admin)):
    from feedback_policy import admin_feedback_projection
    from ml.inference import model_status
    client = service_client()
    try:
        feedback_rows = rows(client.rpc("list_verified_guest_feedback", {}).execute())
        records = [admin_feedback_projection(item) for item in feedback_rows]
        outbox = rows(client.table("feedback_invitation_outbox").select("status").execute())
    except Exception:
        raise HTTPException(status_code=503, detail="Guest feedback is unavailable. Confirm that the post-stay feedback migration is installed.")
    return {"data":records, "invitation_status":{state:sum(row["status"]==state for row in outbox) for state in ("pending","retry","accepted","uncertain","suppressed")}, "analysis_available":model_status()["available"], "model":model_status()}


@admin_router.get("/guest-feedback/historical")
def list_historical_guest_feedback(context: dict[str, Any] = Depends(require_admin)):
    from feedback_policy import admin_feedback_projection
    try:
        records = rows(service_client().table("guest_feedback").select("*").eq("source", "historical_dataset").order("created_at", desc=True).execute())
        return {"data": [admin_feedback_projection(item) for item in records]}
    except Exception:
        raise HTTPException(status_code=503, detail="Historical reviews could not be loaded. Apply the historical feedback import migration.")


@admin_router.post("/guest-feedback/analyze")
def analyze_saved_guest_feedback(context: dict[str, Any] = Depends(require_admin)):
    from ml.inference import model_status, save_pilot_prediction
    if not model_status()["available"]:
        raise HTTPException(status_code=503,detail="The pilot sentiment model is unavailable. Train or restore the model first.")
    client = service_client()
    try:
        from feedback_analysis import records_for
        records = records_for(client, AnalysisFilters())
    except Exception:
        raise HTTPException(status_code=503,detail="Feedback could not be loaded.")
    successful = sum(save_pilot_prediction(client,item) for item in records)
    return {"analyzed":successful,"failed":len(records)-successful,"model":model_status()}


@admin_router.get("/guest-feedback/analysis")
def guest_feedback_analysis(
    source: Literal["all", "verified", "historical"] = "all",
    villa: str = Query(default="", max_length=160),
    rating: int | None = Query(default=None, ge=1, le=5),
    start: date | None = None, end: date | None = None,
    context: dict[str, Any] = Depends(require_admin),
):
    from feedback_analysis import build_report
    from ml.recommendations import configured
    client = service_client()
    filters = AnalysisFilters(source=source,villa=villa,rating=rating,start=start,end=end)
    try:
        result = build_report(client, filters)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="Feedback analysis could not be loaded. Check the feedback migrations.") from None
    result['gemini_configured'] = configured()
    try:
        result['recommendation_reports'] = rows(client.table('feedback_recommendation_reports').select('id,created_at,status,recommendation,approved_at,filters,evidence_fingerprint').eq('evidence_fingerprint',result['summary']['fingerprint']).order('created_at',desc=True).limit(5).execute())
        result['recommendation_storage_ready'] = True
    except Exception:
        result['recommendation_reports'] = []
        result['recommendation_storage_ready'] = False
    result['automation'] = {'status':'pending'}
    try:
        jobs = rows(client.table('feedback_analysis_jobs').select('status,last_error').eq('evidence_fingerprint',result['summary']['fingerprint']).limit(1).execute())
        if jobs: result['automation'] = jobs[0]
    except Exception:
        result['automation'] = {'status':'unavailable','last_error':'Automatic analysis needs the latest database migration.'}
    return result


@admin_router.post("/guest-feedback/recommendations")
def create_feedback_recommendations(
    filters: AnalysisFilters,
    context: dict[str, Any] = Depends(require_admin),
):
    from feedback_analysis import build_report
    from ml.recommendations import generate
    client = service_client()
    # Check storage before an external API request.
    try:
        client.table('feedback_recommendation_reports').select('id').limit(1).execute()
        analysis = build_report(client,filters)
    except Exception:
        raise HTTPException(status_code=503, detail="Recommendation storage or feedback is unavailable. Apply the analysis pipeline migration.") from None
    try:
        draft = generate(analysis['summary'])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    try:
        saved = rows(client.table('feedback_recommendation_reports').insert({
            'created_by_staff_id':str(context['account']['id']),
            'filters':filters.model_dump(mode='json'),
            'evidence_fingerprint':analysis['summary']['fingerprint'],
            'evidence_summary':analysis['summary'], 'model_version':analysis['model']['version'],
            'recommendation':draft, 'status':'draft',
        }).execute())
        if not saved: raise ValueError('No saved draft')
        return {'data':saved[0]}
    except Exception:
        raise HTTPException(status_code=503, detail="The recommendation was generated but could not be saved. No approval was recorded.") from None


@admin_router.post("/guest-feedback/recommendations/{report_id}/approve")
def approve_feedback_recommendations(report_id: UUID, context: dict[str, Any] = Depends(require_admin)):
    from feedback_analysis import build_report
    client = service_client()
    try:
        saved = rows(client.table('feedback_recommendation_reports').select('*').eq('id',str(report_id)).limit(1).execute())
    except Exception:
        raise HTTPException(status_code=503, detail="Recommendation storage could not be loaded.") from None
    if not saved: raise HTTPException(status_code=404, detail="Recommendation report was not found.")
    current = saved[0]
    try:
        analysis = build_report(client,AnalysisFilters(**current['filters']))
    except Exception:
        raise HTTPException(status_code=503, detail="The current evidence could not be verified.") from None
    if analysis['summary']['fingerprint'] != current['evidence_fingerprint']:
        raise HTTPException(status_code=409, detail="Feedback or model changed. Generate and review a fresh recommendation before approval.")
    if current['status'] == 'approved': return {'data':current}
    try:
        saved = rows(client.table('feedback_recommendation_reports').update({
            'status':'approved','approved_by_staff_id':str(context['account']['id']), 'approved_at':now_iso(),
        }).eq('id',str(report_id)).eq('status','draft').execute())
        if not saved: raise ValueError('Draft changed')
        return {'data':saved[0]}
    except Exception:
        raise HTTPException(status_code=409, detail="The draft changed or could not be approved. Refresh and retry.") from None


# Register routes only AFTER all @admin_router endpoints have been declared.
router.include_router(admin_router)
router.include_router(front_desk_router)
