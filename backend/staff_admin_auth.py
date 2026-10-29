from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

if TYPE_CHECKING:
    from supabase import Client

load_dotenv()

SUPABASE_URL = (
    os.getenv("SUPABASE_URL", "")
    .strip()
    .rstrip("/")
)

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "",
).strip()

SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
).strip()

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")

logger = logging.getLogger(
    "thevilla.staff_admin_auth"
)

router = APIRouter(
    prefix="/staff-auth",
    tags=[
        "Staff and Admin Authentication"
    ],
)


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=128,
    )


class PasswordResetRequest(BaseModel):
    email: EmailStr


class StaffSessionRefreshRequest(BaseModel):
    refresh_token: Any = None


class StaffAccountResponse(BaseModel):
    id: str
    auth_user_id: str
    employee_code: str | None = None
    full_name: str
    email: str
    role: Literal["admin", "staff"]
    department: str | None = None
    position: str | None = None
    is_active: bool


def _attr(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    if value is None:
        return default

    if isinstance(value, dict):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def _require_configuration() -> None:
    missing = [
        name
        for name, value in (
            (
                "SUPABASE_URL",
                SUPABASE_URL,
            ),
            (
                "SUPABASE_ANON_KEY",
                SUPABASE_ANON_KEY,
            ),
            (
                "SUPABASE_SERVICE_ROLE_KEY",
                SUPABASE_SERVICE_ROLE_KEY,
            ),
        )
        if not value
    ]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing backend configuration: "
                + ", ".join(missing)
            ),
        )


def _service_client() -> Client:
    """
    Create the Supabase service client using the installed SDK defaults.

    This avoids the incompatible custom client-options object that caused the
    login endpoint to crash before staff_accounts could be queried.
    """

    _require_configuration()

    from db_pool import service_client_for
    return service_client_for(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _auth_headers(
    access_token: str | None = None,
) -> dict[str, str]:
    _require_configuration()

    headers = {
        "apikey":
            SUPABASE_ANON_KEY,

        "Accept":
            "application/json",

        "Content-Type":
            "application/json",
    }

    if access_token:
        headers["Authorization"] = (
            f"Bearer {access_token}"
        )

    return headers


def _response_json(
    response: requests.Response,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    return (
        payload
        if isinstance(
            payload,
            dict,
        )
        else {}
    )


def _read_staff_account(
    auth_user_id: str,
) -> dict[str, Any] | None:
    response = (
        _service_client()
        .table("staff_accounts")
        .select(
            "id,auth_user_id,employee_code,"
            "full_name,email,username,phone,"
            "role,department,position,shift,"
            "is_active,account_status,"
            "must_change_password,last_login_at,"
            "password_reset_at,created_at,"
            "updated_at"
        )
        .eq(
            "auth_user_id",
            auth_user_id,
        )
        .limit(1)
        .execute()
    )

    rows = (
        _attr(
            response,
            "data",
            [],
        )
        or []
    )

    if (
        isinstance(rows, list)
        and rows
    ):
        return rows[0]

    return None


def _safe_account(
    account: dict[str, Any],
) -> dict[str, Any]:
    full_name = str(
        account.get("full_name")
        or "Villa User"
    )

    role = str(
        account.get("role")
        or ""
    ).strip().lower()

    position = account.get(
        "position"
    )

    active = bool(
        account.get("is_active")
    )

    return {
        "id":
            str(
                account.get("id")
                or ""
            ),

        "staffId":
            str(
                account.get("id")
                or ""
            ),

        "staff_account_id":
            str(
                account.get("id")
                or ""
            ),

        "auth_user_id":
            str(
                account.get(
                    "auth_user_id"
                )
                or ""
            ),

        "authUserId":
            str(
                account.get(
                    "auth_user_id"
                )
                or ""
            ),

        "employee_code":
            account.get(
                "employee_code"
            ),

        "employeeCode":
            account.get(
                "employee_code"
            ),

        "full_name":
            full_name,

        "fullName":
            full_name,

        "name":
            full_name,

        "displayName":
            full_name,

        "email":
            str(
                account.get("email")
                or ""
            ),

        "username":
            account.get("username"),

        "phone":
            account.get("phone"),

        "role":
            role,

        "portalRole":
            role,

        "department":
            account.get(
                "department"
            ),

        "position":
            position,

        "displayRole":
            position
            or role.title(),

        "shift":
            account.get("shift"),

        "is_active":
            active,

        "isActive":
            active,

        "accountStatus":
            account.get(
                "account_status"
            )
            or (
                "Active"
                if active
                else "Disabled"
            ),

        "mustChangePassword":
            bool(
                account.get(
                    "must_change_password"
                )
            ),

        "lastLogin":
            account.get(
                "last_login_at"
            ),

        "passwordResetAt":
            account.get(
                "password_reset_at"
            ),

        "createdAt":
            account.get(
                "created_at"
            ),

        "updatedAt":
            account.get(
                "updated_at"
            ),
    }


def _bearer_token(
    request: Request,
) -> str:
    authorization = (
        request.headers.get(
            "Authorization",
            "",
        )
        .strip()
    )

    if not authorization.startswith(
        "Bearer "
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Login session is missing."
            ),
        )

    token = (
        authorization
        .removeprefix("Bearer ")
        .strip()
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Login session is missing."
            ),
        )

    return token


def get_supabase_user(
    access_token: str,
) -> dict[str, Any]:
    token = str(
        access_token or ""
    ).strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Login session is missing."
            ),
        )

    try:
        response = requests.get(
            (
                f"{SUPABASE_URL}"
                "/auth/v1/user"
            ),
            headers=_auth_headers(
                token
            ),
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "The authentication service "
                "could not be reached."
            ),
        ) from error

    payload = _response_json(
        response
    )

    if not response.ok:
        raise HTTPException(
            status_code=401,
            detail=(
                "The login session is "
                "invalid or expired."
            ),
        )

    user_id = str(
        payload.get("id")
        or ""
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Supabase returned an "
                "invalid user session."
            ),
        )

    return payload


def validate_portal_access_token(
    access_token: str,
    required_role: Literal[
        "admin",
        "staff",
    ]
    | None = None,
) -> dict[str, Any]:
    auth_user = get_supabase_user(
        access_token
    )

    auth_user_id = str(
        auth_user.get("id")
        or ""
    ).strip()

    account = _read_staff_account(
        auth_user_id
    )

    if not account:
        raise HTTPException(
            status_code=403,
            detail=(
                "This account is not "
                "registered in the staff "
                "directory."
            ),
        )

    role = str(
        account.get("role")
        or ""
    ).strip().lower()

    if role not in {
        "admin",
        "staff",
    }:
        raise HTTPException(
            status_code=403,
            detail=(
                "This account has an "
                "invalid portal role."
            ),
        )

    if (
        required_role
        and role != required_role
    ):
        label = (
            "Administrator"
            if required_role
            == "admin"
            else "Staff"
        )

        raise HTTPException(
            status_code=403,
            detail=(
                f"{label} access "
                "is required."
            ),
        )

    disabled = (
        not bool(
            account.get("is_active")
        )
        or str(
            account.get(
                "account_status"
            )
            or ""
        ).strip().lower()
        == "disabled"
    )

    if disabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "This portal account "
                "is disabled."
            ),
        )

    auth_email = str(
        auth_user.get("email")
        or ""
    ).strip().lower()

    account_email = str(
        account.get("email")
        or ""
    ).strip().lower()

    if (
        auth_email
        and account_email
        and auth_email
        != account_email
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "The staff directory "
                "email does not match "
                "the authenticated account."
            ),
        )

    return account


def _password_login(
    email: str,
    password: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            (
                f"{SUPABASE_URL}"
                "/auth/v1/token"
                "?grant_type=password"
            ),
            headers=_auth_headers(),
            json={
                "email": email,
                "password": password,
            },
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "The authentication service "
                "could not be reached."
            ),
        ) from error

    payload = _response_json(
        response
    )

    if not response.ok:
        detail = str(
            payload.get("msg")
            or payload.get("message")
            or payload.get(
                "error_description"
            )
            or payload.get("error")
            or (
                "Incorrect email address "
                "or password."
            )
        )

        lowered = detail.lower()

        if (
            "invalid login"
            in lowered
            or "invalid credentials"
            in lowered
        ):
            detail = (
                "Incorrect email address "
                "or password."
            )

        raise HTTPException(
            status_code=401,
            detail=detail,
        )

    return payload


def _refresh_login(
    refresh_token: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            (
                f"{SUPABASE_URL}"
                "/auth/v1/token"
                "?grant_type=refresh_token"
            ),
            headers=_auth_headers(),
            json={
                "refresh_token":
                    refresh_token,
            },
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "The authentication service "
                "could not be reached."
            ),
        ) from error

    payload = _response_json(
        response
    )

    if not response.ok:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session has "
                "expired. Please sign in "
                "again."
            ),
        )

    return payload


def _session_response(
    auth_payload: dict[str, Any],
    account: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    access_token = str(
        auth_payload.get(
            "access_token"
        )
        or ""
    ).strip()

    refresh_token = str(
        auth_payload.get(
            "refresh_token"
        )
        or ""
    ).strip()

    if (
        not access_token
        or not refresh_token
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Supabase returned an "
                "incomplete login session."
            ),
        )

    return {
        "message":
            message,

        "authenticated":
            True,

        "token":
            access_token,

        "access_token":
            access_token,

        "refresh_token":
            refresh_token,

        "expires_in":
            auth_payload.get(
                "expires_in"
            ),

        "expires_at":
            auth_payload.get(
                "expires_at"
            ),

        "token_type":
            auth_payload.get(
                "token_type"
            )
            or "bearer",

        "user":
            _safe_account(
                account
            ),
    }


@router.post("/login")
def staff_admin_login(
    data: StaffLoginRequest,
):
    email = str(
        data.email
    ).strip().lower()

    auth_payload = _password_login(
        email,
        data.password,
    )

    access_token = str(
        auth_payload.get(
            "access_token"
        )
        or ""
    ).strip()

    account = (
        validate_portal_access_token(
            access_token
        )
    )

    now = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    (
        _service_client()
        .table("staff_accounts")
        .update({
            "last_login_at": now,
            "updated_at": now,
        })
        .eq(
            "id",
            account["id"],
        )
        .execute()
    )

    fresh_account = (
        _read_staff_account(
            str(
                account[
                    "auth_user_id"
                ]
            )
        )
        or account
    )

    return _session_response(
        auth_payload,
        fresh_account,
        "Login successful.",
    )


@router.post("/refresh")
def refresh_staff_admin_session(
    data:
        StaffSessionRefreshRequest,
):
    raw = data.refresh_token

    refresh_token = (
        raw.strip()
        if isinstance(raw, str)
        else ""
    )

    invalid = (
        not refresh_token
        or refresh_token.lower()
        in {
            "undefined",
            "null",
            "none",
        }
        or len(refresh_token) < 20
        or len(refresh_token) > 10000
    )

    if invalid:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your saved portal session "
                "is invalid. Please sign "
                "in again."
            ),
        )

    auth_payload = _refresh_login(
        refresh_token
    )

    access_token = str(
        auth_payload.get(
            "access_token"
        )
        or ""
    ).strip()

    account = (
        validate_portal_access_token(
            access_token
        )
    )

    return _session_response(
        auth_payload,
        account,
        "Login session refreshed.",
    )


@router.get("/me")
def current_staff_admin(
    request: Request,
):
    token = _bearer_token(
        request
    )

    account = (
        validate_portal_access_token(
            token
        )
    )

    return {
        "authenticated": True,

        "user":
            _safe_account(
                account
            ),
    }


@router.post("/forgot-password")
def forgot_staff_password(
    data: PasswordResetRequest,
):
    email = str(
        data.email
    ).strip().lower()

    redirect_url = (
        f"{FRONTEND_URL}"
        "/reset-password"
    )

    try:
        requests.post(
            (
                f"{SUPABASE_URL}"
                "/auth/v1/recover"
                f"?redirect_to="
                f"{quote(redirect_url)}"
            ),
            headers=_auth_headers(),
            json={
                "email": email,
            },
            timeout=(5, 30),
        )
    except requests.RequestException:
        logger.info(
            (
                "Password recovery "
                "request could not be "
                "completed for %s"
            ),
            email,
        )

    return {
        "message": (
            "If this email belongs to "
            "an authorized portal account, "
            "a password reset link has "
            "been sent."
        )
    }