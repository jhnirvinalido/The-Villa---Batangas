from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
)
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)
from standardwebhooks.webhooks import Webhook
from booking import (
    router as booking_router,
    public_router as public_booking_router,
)
from staff_admin_auth import router as staff_admin_auth_router
from admin import router as admin_router
from maintenance import router as maintenance_router
from maintenance_oncall import public_router as maintenance_response_router
from staff import router as staff_router
from staff_villa_operations import router as staff_villa_operations_router
from villa_catalog import router as villa_catalog_router

if TYPE_CHECKING:
    from supabase import Client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
).strip()
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")

HTTPSMS_API_KEY = os.getenv("HTTPSMS_API_KEY")
HTTPSMS_FROM = os.getenv("HTTPSMS_FROM")
SUPABASE_SMS_HOOK_SECRET = os.getenv(
    "SUPABASE_SMS_HOOK_SECRET"
)

HTTPSMS_SEND_URL = (
    "https://api.httpsms.com/v1/messages/send"
)

CURRENT_TERMS_VERSION = "2026-07-13"
CURRENT_PRIVACY_VERSION = "2026-07-13"

PROFILE_PHOTO_BUCKET = "profile-photos"
PROFILE_PHOTO_MAX_BYTES = 2 * 1024 * 1024

ACCOUNT_DELETION_GRACE_DAYS = 30
ACCOUNT_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_PENDING_DELETION = "pending_deletion"

ACCOUNT_METHODS = {
    "email",
    "google",
    "phone",
}

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | %(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "thevilla.phone_auth"
)


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is missing in backend/.env"
    )

if not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_ANON_KEY is missing in backend/.env"
    )


def create_supabase_client() -> Client:
    from supabase import create_client

    return create_client(
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
    )


def create_service_supabase_client() -> Client:
    from supabase import create_client

    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "SUPABASE_SERVICE_ROLE_KEY is required "
                "for account deletion and cleanup."
            ),
        )

    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )


app = FastAPI(
    title="The Villa Authentication API",
    version="1.6.0",
)


LOCAL_FRONTEND_ORIGINS = {
    FRONTEND_URL,
    os.getenv("MAINTENANCE_FRONTEND_URL", "").strip().rstrip("/"),
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


def normalize_origin(
    value: str,
) -> str:
    return str(
        value or ""
    ).strip().rstrip("/")


def origin_is_allowed(
    origin: str,
) -> bool:
    normalized = normalize_origin(
        origin
    )

    if not normalized:
        return False

    if normalized in {
        normalize_origin(item)
        for item in LOCAL_FRONTEND_ORIGINS
        if item
    }:
        return True

    return bool(
        re.fullmatch(
            (
                r"https?://"
                r"(localhost|127\.0\.0\.1)"
                r"(?::\d+)?"
            ),
            normalized,
        )
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        normalize_origin(item)
        for item in LOCAL_FRONTEND_ORIGINS
        if item
    ],
    allow_origin_regex=(
        r"^https?://"
        r"(localhost|127\.0\.0\.1)"
        r"(?::\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-Refresh-Token",
        "X-Booking-Token",
        "X-Manual-Booking-Token",
        "X-Feedback-Token",
        "X-Maintenance-Token",
    ],
    expose_headers=[
        "X-Villa-Access-Token",
        "X-Villa-Refresh-Token",
    ],
    max_age=86400,
)


@app.middleware("http")
async def guarantee_local_cors_headers(
    request: Request,
    call_next,
):
    """
    Guarantee CORS headers for the local React application.

    This also covers authentication error responses such as 401 and 403,
    allowing the browser to display the actual backend error instead of
    replacing it with the generic "Failed to fetch" message.
    """

    origin = normalize_origin(
        request.headers.get(
            "Origin",
            "",
        )
    )

    allowed = origin_is_allowed(
        origin
    )

    if (
        request.method.upper()
        == "OPTIONS"
        and allowed
    ):
        response = Response(
            status_code=204,
        )
    else:
        try:
            response = await call_next(
                request
            )
        except Exception as error:
            logger.exception(
                (
                    "Unhandled API error "
                    "for %s %s"
                ),
                request.method,
                request.url.path,
            )

            response = JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        "The server could not "
                        "complete the request. "
                        "Check the backend "
                        "terminal for the "
                        "recorded error."
                    )
                },
            )

    if allowed:
        requested_headers = (
            request.headers.get(
                "Access-Control-Request-Headers",
                "",
            )
            .strip()
        )

        response.headers[
            "Access-Control-Allow-Origin"
        ] = origin

        response.headers[
            "Access-Control-Allow-Credentials"
        ] = "true"

        response.headers[
            "Access-Control-Allow-Methods"
        ] = (
            "GET, POST, PUT, PATCH, "
            "DELETE, OPTIONS"
        )

        response.headers[
            "Access-Control-Allow-Headers"
        ] = (
            requested_headers
            or (
                "Accept, Authorization, "
                "Content-Type, Origin, "
                "X-Requested-With, "
                "X-Refresh-Token, "
                "X-Booking-Token, "
                "X-Manual-Booking-Token"
            )
        )

        response.headers[
            "Access-Control-Expose-Headers"
        ] = (
            "X-Villa-Access-Token, "
            "X-Villa-Refresh-Token"
        )

        response.headers[
            "Access-Control-Max-Age"
        ] = "86400"

        existing_vary = (
            response.headers.get(
                "Vary",
                "",
            )
            .strip()
        )

        vary_values = {
            value.strip()
            for value in existing_vary.split(",")
            if value.strip()
        }

        vary_values.add(
            "Origin"
        )

        response.headers[
            "Vary"
        ] = ", ".join(
            sorted(vary_values)
        )

    return response


@app.middleware("http")
async def expose_refreshed_auth_tokens(
    request: Request,
    call_next,
):
    """
    Return rotated Supabase tokens to the browser after
    a protected booking request refreshes its session.
    """

    response = await call_next(request)

    refreshed_access = getattr(
        request.state,
        "villa_access_token",
        "",
    )

    refreshed_refresh = getattr(
        request.state,
        "villa_refresh_token",
        "",
    )

    if refreshed_access:
        response.headers[
            "X-Villa-Access-Token"
        ] = refreshed_access

    if refreshed_refresh:
        response.headers[
            "X-Villa-Refresh-Token"
        ] = refreshed_refresh

    return response


app.include_router(booking_router)
app.include_router(public_booking_router)
from companion_feedback import router as companion_feedback_router
app.include_router(companion_feedback_router)
app.include_router(staff_admin_auth_router)
app.include_router(admin_router)
app.include_router(maintenance_router)
app.include_router(maintenance_response_router)
app.include_router(staff_router)
app.include_router(staff_villa_operations_router)
app.include_router(villa_catalog_router)


class RegisterRequest(BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
    )
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=128,
    )
    terms_accepted: bool = False
    privacy_accepted: bool = False
    terms_version: str | None = None
    privacy_version: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=128,
    )


class SessionRefreshRequest(BaseModel):
    # Validate explicitly inside the endpoint so legacy
    # browser data returns a readable 401 instead of a
    # framework-generated 422 response.
    refresh_token: Any = None


class GoogleLoginRequest(BaseModel):
    credential: str = Field(
        min_length=20,
        max_length=20_000,
        description=(
            "Google Identity Services ID token."
        ),
    )
    nonce: str = Field(
        min_length=16,
        max_length=512,
        description=(
            "Raw nonce whose SHA-256 hexadecimal digest "
            "was supplied to Google Identity Services."
        ),
    )
    create_account: bool = False
    terms_accepted: bool = False
    privacy_accepted: bool = False
    terms_version: str | None = None
    privacy_version: str | None = None


class PhoneOtpRequest(BaseModel):
    phone_number: str = Field(
        min_length=10,
        max_length=20,
    )
    create_account: bool = False
    first_name: str | None = Field(
        default=None,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        max_length=100,
    )
    terms_accepted: bool = False
    privacy_accepted: bool = False
    terms_version: str | None = None
    privacy_version: str | None = None


class PhoneOtpVerifyRequest(BaseModel):
    phone_number: str = Field(
        min_length=10,
        max_length=20,
    )
    otp: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )


class ProfileUpdateRequest(BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
    )
    email: EmailStr | None = None
    phone_number: str | None = Field(
        default=None,
        max_length=20,
    )


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(
        min_length=6,
        max_length=128,
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class ProfileAvatarRequest(BaseModel):
    image_data: str = Field(
        min_length=100,
        max_length=4_000_000,
    )


class AccountDeleteRequest(BaseModel):
    confirmation: str = Field(
        min_length=6,
        max_length=20,
    )


def require_legal_acceptance(
    terms_accepted: bool,
    privacy_accepted: bool,
    terms_version: str | None,
    privacy_version: str | None,
) -> None:
    if not terms_accepted or not privacy_accepted:
        raise HTTPException(
            status_code=422,
            detail=(
                "You must accept the Terms and Conditions "
                "and Privacy Policy before creating an account."
            ),
        )

    if terms_version != CURRENT_TERMS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=(
                "The Terms and Conditions version is out of date. "
                "Refresh the page and review the current terms."
            ),
        )

    if privacy_version != CURRENT_PRIVACY_VERSION:
        raise HTTPException(
            status_code=422,
            detail=(
                "The Privacy Policy version is out of date. "
                "Refresh the page and review the current policy."
            ),
        )


def legal_acceptance_metadata() -> dict[str, Any]:
    accepted_at = datetime.now(
        timezone.utc
    ).isoformat()

    return {
        "terms_accepted": True,
        "privacy_accepted": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "privacy_version": CURRENT_PRIVACY_VERSION,
        "terms_accepted_at": accepted_at,
        "privacy_accepted_at": accepted_at,
    }


def get_attribute(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    if value is None:
        return default

    if isinstance(value, dict):
        return value.get(name, default)

    return getattr(value, name, default)



def account_method_label(
    method: str,
) -> str:
    labels = {
        "email": "Email and password",
        "google": "Google",
        "phone": "Phone verification",
    }

    return labels.get(
        method,
        "the original sign-in method",
    )


def get_account_origin(
    user: Any,
) -> str:
    """
    Return the single sign-in method permanently assigned
    to this Villa account.

    New accounts store account_origin explicitly.
    Existing accounts fall back to the original provider
    stored in user metadata, then to Supabase app metadata.
    """

    if not user:
        return "email"

    user_metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    app_metadata = (
        get_attribute(
            user,
            "app_metadata",
            {},
        )
        or {}
    )

    for candidate in (
        user_metadata.get(
            "account_origin"
        ),
        user_metadata.get("provider"),
        app_metadata.get("provider"),
    ):
        if candidate in ACCOUNT_METHODS:
            return candidate

    providers = app_metadata.get(
        "providers",
        [],
    )

    if isinstance(providers, list):
        for candidate in (
            "phone",
            "google",
            "email",
        ):
            if candidate in providers:
                return candidate

    return "email"


def get_linked_account_methods(
    user: Any,
) -> list[str]:
    """
    Return every Supabase identity currently linked to the
    user. Supabase can automatically link verified OAuth
    identities that use the same email address.

    The original account_origin remains available for
    profile compatibility, but it no longer prevents a
    safely linked Google identity from signing in.
    """

    methods: set[str] = set()

    if not user:
        return ["email"]

    user_metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    app_metadata = (
        get_attribute(
            user,
            "app_metadata",
            {},
        )
        or {}
    )

    for candidate in (
        user_metadata.get(
            "account_origin"
        ),
        user_metadata.get(
            "provider"
        ),
        user_metadata.get(
            "last_login_method"
        ),
        app_metadata.get(
            "provider"
        ),
    ):
        if candidate in ACCOUNT_METHODS:
            methods.add(candidate)

    providers = app_metadata.get(
        "providers",
        [],
    )

    if isinstance(
        providers,
        list,
    ):
        for provider in providers:
            if provider in ACCOUNT_METHODS:
                methods.add(provider)

    identities = get_attribute(
        user,
        "identities",
        [],
    )

    if isinstance(
        identities,
        list,
    ):
        for identity in identities:
            provider = get_attribute(
                identity,
                "provider",
            )

            if provider in ACCOUNT_METHODS:
                methods.add(provider)

    if not methods:
        methods.add(
            get_account_origin(
                user
            )
        )

    preferred_order = [
        "email",
        "google",
        "phone",
    ]

    return [
        method
        for method in preferred_order
        if method in methods
    ]


def require_account_method(
    user: Any,
    attempted_method: str,
) -> str:
    """
    Allow any authentication identity that Supabase has
    safely linked to this user.

    A 409 is returned only when the attempted method is
    not one of the user's linked identities.
    """

    account_origin = get_account_origin(
        user
    )

    linked_methods = (
        get_linked_account_methods(
            user
        )
    )

    if attempted_method not in linked_methods:
        allowed_labels = ", ".join(
            account_method_label(
                method
            )
            for method in linked_methods
        )

        attempted_label = (
            account_method_label(
                attempted_method
            )
        )

        raise HTTPException(
            status_code=409,
            detail=(
                f"{attempted_label} is not linked to "
                "this Villa account. Sign in using "
                f"{allowed_labels}, or link the Google "
                "identity to the same verified email "
                "address first."
            ),
        )

    return account_origin



def normalize_ph_phone(
    value: str,
) -> str:
    """
    Convert common Philippine mobile formats to E.164.

    Accepted examples:
      9123456789
      09123456789
      639123456789
      +639123456789
    """

    raw = value.strip()
    digits = re.sub(r"\D", "", raw)

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

    raise HTTPException(
        status_code=422,
        detail=(
            "Enter a valid Philippine mobile number, "
            "for example 9123456789."
        ),
    )


def clean_person_name(
    value: Any,
) -> str | None:
    cleaned = re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()

    return cleaned or None


def split_full_name(
    full_name: str | None,
    family_name: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Split a display name without forcing the second word
    into the surname.

    Examples:
      Jhon Irvin Alido -> Jhon Irvin / Alido
      Maria Dela Cruz with family_name Dela Cruz
        -> Maria / Dela Cruz

    Google given_name and family_name are still preferred
    whenever they are available.
    """

    cleaned = clean_person_name(
        full_name
    )

    if not cleaned:
        return None, None

    cleaned_family_name = (
        clean_person_name(
            family_name
        )
    )

    if cleaned_family_name:
        full_folded = cleaned.casefold()
        family_folded = (
            cleaned_family_name.casefold()
        )

        if full_folded.endswith(
            family_folded
        ):
            first_part = cleaned[
                : len(cleaned)
                - len(cleaned_family_name)
            ].strip()

            if first_part:
                return (
                    first_part,
                    cleaned_family_name,
                )

    parts = cleaned.rsplit(
        maxsplit=1
    )

    return (
        parts[0],
        parts[1]
        if len(parts) > 1
        else None,
    )


def decode_google_identity_claims(
    credential: str,
) -> dict[str, Any]:
    """
    Read the already-verified Google ID-token claims
    only for profile-name initialization.

    Authentication remains handled by Supabase before
    these values are used.
    """

    try:
        token_parts = credential.split(".")

        if len(token_parts) < 2:
            return {}

        encoded_payload = (
            token_parts[1]
        )

        padding = "=" * (
            -len(encoded_payload) % 4
        )

        decoded_payload = (
            base64.urlsafe_b64decode(
                encoded_payload + padding
            )
        )

        claims = json.loads(
            decoded_payload.decode(
                "utf-8"
            )
        )

        return (
            claims
            if isinstance(claims, dict)
            else {}
        )

    except Exception:
        return {}


def build_google_name_metadata(
    user: Any,
    credential: str,
) -> dict[str, Any]:
    """
    Keep Google's name as the initial account name, but
    never overwrite a name that the customer saved inside
    The Villa profile.
    """

    existing_metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    claims = (
        decode_google_identity_claims(
            credential
        )
    )

    google_full_name = (
        clean_person_name(
            claims.get("name")
        )
        or clean_person_name(
            existing_metadata.get(
                "google_full_name"
            )
        )
        or clean_person_name(
            existing_metadata.get(
                "name"
            )
        )
        or clean_person_name(
            existing_metadata.get(
                "full_name"
            )
        )
    )

    google_first_name = (
        clean_person_name(
            claims.get("given_name")
        )
        or clean_person_name(
            existing_metadata.get(
                "google_given_name"
            )
        )
        or clean_person_name(
            existing_metadata.get(
                "given_name"
            )
        )
    )

    google_last_name = (
        clean_person_name(
            claims.get("family_name")
        )
        or clean_person_name(
            existing_metadata.get(
                "google_family_name"
            )
        )
        or clean_person_name(
            existing_metadata.get(
                "family_name"
            )
        )
    )

    derived_first_name, derived_last_name = (
        split_full_name(
            google_full_name,
            google_last_name,
        )
    )

    google_first_name = (
        google_first_name
        or derived_first_name
    )

    google_last_name = (
        google_last_name
        or derived_last_name
    )

    if not google_full_name:
        google_full_name = clean_person_name(
            " ".join(
                part
                for part in [
                    google_first_name,
                    google_last_name,
                ]
                if part
            )
        )

    profile_name_customized = bool(
        existing_metadata.get(
            "profile_name_customized"
        )
    )

    profile_first_name = (
        clean_person_name(
            existing_metadata.get(
                "profile_first_name"
            )
        )
    )

    profile_last_name = (
        clean_person_name(
            existing_metadata.get(
                "profile_last_name"
            )
        )
    )

    profile_full_name = (
        clean_person_name(
            existing_metadata.get(
                "profile_full_name"
            )
        )
    )

    if (
        not profile_name_customized
        or not profile_first_name
        or not profile_last_name
    ):
        profile_first_name = (
            google_first_name
            or profile_first_name
        )

        profile_last_name = (
            google_last_name
            or profile_last_name
        )

        profile_full_name = (
            clean_person_name(
                " ".join(
                    part
                    for part in [
                        profile_first_name,
                        profile_last_name,
                    ]
                    if part
                )
            )
            or google_full_name
        )

        profile_name_customized = False

    else:
        profile_full_name = (
            clean_person_name(
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
        )

    return {
        "google_given_name": (
            google_first_name
        ),
        "google_family_name": (
            google_last_name
        ),
        "google_full_name": (
            google_full_name
        ),
        "profile_first_name": (
            profile_first_name
        ),
        "profile_last_name": (
            profile_last_name
        ),
        "profile_full_name": (
            profile_full_name
        ),
        "profile_name_customized": (
            profile_name_customized
        ),
        # Compatibility fields used by the existing UI.
        "first_name": (
            profile_first_name
        ),
        "last_name": (
            profile_last_name
        ),
        "full_name": (
            profile_full_name
        ),
    }


def user_to_dict(
    user: Any,
) -> dict[str, Any] | None:
    if not user:
        return None

    user_metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    app_metadata = (
        get_attribute(
            user,
            "app_metadata",
            {},
        )
        or {}
    )

    linked_methods = (
        get_linked_account_methods(
            user
        )
    )

    providers = list(
        linked_methods
    )

    account_origin = get_account_origin(
        user
    )

    login_method = (
        user_metadata.get(
            "last_login_method"
        )
        or account_origin
    )

    if login_method not in linked_methods:
        login_method = account_origin

    password_enabled = bool(
        user_metadata.get(
            "password_enabled"
        )
        or "email" in linked_methods
    )

    google_full_name = (
        clean_person_name(
            user_metadata.get(
                "google_full_name"
            )
        )
        or clean_person_name(
            user_metadata.get("name")
        )
        or clean_person_name(
            user_metadata.get(
                "full_name"
            )
        )
    )

    google_first_name = (
        clean_person_name(
            user_metadata.get(
                "google_given_name"
            )
        )
        or clean_person_name(
            user_metadata.get(
                "given_name"
            )
        )
    )

    google_last_name = (
        clean_person_name(
            user_metadata.get(
                "google_family_name"
            )
        )
        or clean_person_name(
            user_metadata.get(
                "family_name"
            )
        )
    )

    (
        derived_google_first_name,
        derived_google_last_name,
    ) = split_full_name(
        google_full_name,
        google_last_name,
    )

    profile_first_name = (
        clean_person_name(
            user_metadata.get(
                "profile_first_name"
            )
        )
    )

    profile_last_name = (
        clean_person_name(
            user_metadata.get(
                "profile_last_name"
            )
        )
    )

    profile_full_name = (
        clean_person_name(
            user_metadata.get(
                "profile_full_name"
            )
        )
    )

    first_name = (
        profile_first_name
        or clean_person_name(
            user_metadata.get(
                "first_name"
            )
        )
        or google_first_name
        or derived_google_first_name
    )

    last_name = (
        profile_last_name
        or clean_person_name(
            user_metadata.get(
                "last_name"
            )
        )
        or google_last_name
        or derived_google_last_name
    )

    full_name = (
        profile_full_name
        or clean_person_name(
            " ".join(
                part
                for part in [
                    first_name,
                    last_name,
                ]
                if part
            )
        )
        or google_full_name
    )

    auth_email = get_attribute(
        user,
        "email",
    )

    auth_phone = get_attribute(
        user,
        "phone",
    )

    contact_email = (
        user_metadata.get(
            "contact_email"
        )
    )

    contact_phone = (
        user_metadata.get(
            "contact_phone"
        )
    )

    if account_origin == "phone":
        email = (
            contact_email
            if contact_email
            else None
        )
        phone = auth_phone
    else:
        email = auth_email
        phone = (
            contact_phone
            if contact_phone
            else None
        )

    google_user_id = None

    if "google" in linked_methods:
        google_user_id = (
            user_metadata.get("sub")
            or user_metadata.get(
                "provider_id"
            )
        )

    auth_email_verified = bool(
        user_metadata.get("email_verified")
        or get_attribute(
            user,
            "email_confirmed_at",
        )
    )

    auth_phone_verified = bool(
        user_metadata.get("phone_verified")
        or get_attribute(
            user,
            "phone_confirmed_at",
        )
    )

    email_verified = bool(
        (
            "email" in linked_methods
            or "google" in linked_methods
        )
        and auth_email
        and auth_email_verified
    )

    phone_verified = bool(
        "phone" in linked_methods
        and auth_phone
        and auth_phone_verified
    )

    resolved_full_name = (
        clean_person_name(
            " ".join(
                part
                for part in [
                    first_name,
                    last_name,
                ]
                if part
            )
        )
        or full_name
        or email
        or phone
    )

    return {
        "id": str(
            get_attribute(
                user,
                "id",
                "",
            )
        ),
        "email": email,
        "phone": phone,
        "auth_email": auth_email,
        "auth_phone": auth_phone,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": resolved_full_name,
        "avatar_url": (
            None
            if user_metadata.get(
                "avatar_removed"
            )
            else (
                user_metadata.get(
                    "custom_avatar_url"
                )
                or user_metadata.get(
                    "avatar_url"
                )
                or user_metadata.get(
                    "picture"
                )
            )
        ),
        "provider": account_origin,
        "account_origin": account_origin,
        "login_method": login_method,
        "password_enabled": password_enabled,
        "providers": providers,
        "allowed_login_methods": (
            linked_methods
        ),
        "google_user_id": google_user_id,
        "email_verified": email_verified,
        "phone_verified": phone_verified,
        "last_sign_in_at": get_attribute(
            user,
            "last_sign_in_at",
        ),
        "account_role": user_metadata.get(
            "account_role",
            "client",
        ),
        "terms_accepted": bool(
            user_metadata.get(
                "terms_accepted"
            )
        ),
        "privacy_accepted": bool(
            user_metadata.get(
                "privacy_accepted"
            )
        ),
        "terms_version": user_metadata.get(
            "terms_version"
        ),
        "privacy_version": user_metadata.get(
            "privacy_version"
        ),
        "terms_accepted_at": user_metadata.get(
            "terms_accepted_at"
        ),
        "privacy_accepted_at": user_metadata.get(
            "privacy_accepted_at"
        ),
        "account_status": user_metadata.get(
            "account_status",
            ACCOUNT_STATUS_ACTIVE,
        ),
        "deletion_requested_at": user_metadata.get(
            "deletion_requested_at"
        ),
        "deletion_due_at": user_metadata.get(
            "deletion_due_at"
        ),
    }

def get_user_identities(
    user: Any,
) -> list[Any]:
    identities = get_attribute(
        user,
        "identities",
        [],
    )

    if isinstance(identities, list):
        return identities

    return []


def is_obfuscated_existing_user(
    response: Any,
) -> bool:
    """
    Supabase returns an obfuscated user with no identities
    when sign-up is attempted for an existing confirmed
    account. This prevents account-enumeration attacks.
    """

    user = get_attribute(
        response,
        "user",
    )

    session = get_attribute(
        response,
        "session",
    )

    return bool(
        user
        and not session
        and len(get_user_identities(user)) == 0
    )


def auth_response_to_dict(
    response: Any,
) -> dict[str, Any]:
    user = get_attribute(
        response,
        "user",
    )
    session = get_attribute(
        response,
        "session",
    )

    return {
        "user": user_to_dict(user),
        "access_token": (
            get_attribute(
                session,
                "access_token",
            )
            if session
            else None
        ),
        "refresh_token": (
            get_attribute(
                session,
                "refresh_token",
            )
            if session
            else None
        ),
        "expires_in": (
            get_attribute(
                session,
                "expires_in",
            )
            if session
            else None
        ),
        "token_type": (
            get_attribute(
                session,
                "token_type",
                "bearer",
            )
            if session
            else None
        ),
    }


def update_login_context(
    supabase: Client,
    user: Any,
    login_method: str,
    password_enabled: bool | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Any:
    """
    Save the method used for this login while preserving
    the account's original creation method.

    Email and Google may both be valid when Supabase has
    automatically linked them to the same verified user.
    """

    account_origin = require_account_method(
        user,
        login_method,
    )

    linked_methods = (
        get_linked_account_methods(
            user
        )
    )

    existing_metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    resolved_password_enabled = (
        bool(password_enabled)
        if password_enabled is not None
        else "email" in linked_methods
    )

    metadata_updates: dict[str, Any] = {
        "account_origin":
            account_origin,

        "provider":
            account_origin,

        "last_login_method":
            login_method,

        "password_enabled":
            resolved_password_enabled,

        "linked_login_methods":
            linked_methods,
    }

    if extra_metadata:
        metadata_updates.update(
            extra_metadata
        )

    response = supabase.auth.update_user(
        {
            "data": {
                **existing_metadata,
                **metadata_updates,
            }
        }
    )

    return (
        get_attribute(
            response,
            "user",
        )
        or user
    )



TRANSIENT_CONNECTION_MARKERS = (
    "connectionterminated",
    "connection terminated",
    "last_stream_id",
    "server disconnected",
    "connection reset",
    "connection aborted",
    "remoteprotocolerror",
    "readerror",
    "writeerror",
    "temporarily unavailable",
    "service unavailable",
    "timed out",
    "timeout",
)


def is_transient_connection_error(
    error: Exception,
) -> bool:
    message = str(error).strip().lower()

    return any(
        marker in message
        for marker in TRANSIENT_CONNECTION_MARKERS
    )


def sign_in_with_google_id_token(
    credential: str,
    raw_nonce: str,
) -> dict[str, Any]:
    """
    Exchange a Google Identity Services ID token for a
    Supabase session while validating the matching nonce.
    """

    endpoint = (
        f"{SUPABASE_URL}/auth/v1/token"
        "?grant_type=id_token"
    )

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json={
                "provider": "google",
                "id_token": credential,
                "nonce": raw_nonce,
            },
            timeout=(5, 25),
        )

    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google authentication is temporarily "
                "unavailable. Please try again."
            ),
        ) from error

    try:
        result = response.json()
    except ValueError:
        result = {}

    if response.status_code != 200:
        provider_message = str(
            result.get(
                "msg",
                result.get(
                    "message",
                    result.get(
                        "error_description",
                        "",
                    ),
                ),
            )
        ).strip()

        if "nonce" in provider_message.lower():
            detail = (
                "Google sign-in security validation "
                "failed. Refresh the page and select "
                "your Google account again."
            )

        elif response.status_code in {
            400,
            401,
            403,
        }:
            detail = (
                provider_message
                or (
                    "Supabase rejected the Google "
                    "identity token. Confirm that the "
                    "Google provider uses the same OAuth "
                    "Web client ID and secret."
                )
            )

        else:
            detail = (
                "The Google authentication service "
                "returned an unexpected response."
            )

        raise HTTPException(
            status_code=401,
            detail=detail,
        )

    for field in (
        "access_token",
        "refresh_token",
        "user",
    ):
        if not result.get(field):
            raise HTTPException(
                status_code=502,
                detail=(
                    "Supabase returned an incomplete "
                    "Google login session."
                ),
            )

    return result


def refresh_session_via_supabase_rest(
    refresh_token: str,
) -> dict[str, Any]:
    """
    Refresh a Supabase session through the Auth REST
    endpoint using requests/HTTP 1.1.

    This avoids turning a temporary HTTP/2 disconnect
    into a false "Please log in again" response.
    """

    endpoint = (
        f"{SUPABASE_URL}/auth/v1/token"
        "?grant_type=refresh_token"
    )

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json={
                    "refresh_token": (
                        refresh_token
                    )
                },
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
                    "The Villa authentication service "
                    "is temporarily unavailable. "
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

            if (
                not result.get("access_token")
                or not result.get(
                    "refresh_token"
                )
                or not result.get("user")
            ):
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "The refreshed session was "
                        "incomplete."
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
            raise HTTPException(
                status_code=401,
                detail=(
                    "Your login session has expired. "
                    "Please log in again."
                ),
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "The authentication service rejected "
                "the session refresh."
            ),
        )

    raise HTTPException(
        status_code=503,
        detail=(
            "The Villa authentication service is "
            "temporarily unavailable. Please try again."
        ),
    ) from last_error


def update_authenticated_user_with_retry(
    supabase: Client,
    update_payload: dict[str, Any],
    access_token: str,
    refresh_token: str,
) -> tuple[Client, Any]:
    """
    Retry only short-lived connection failures.

    Updating user metadata is idempotent for the profile
    payload, so a second attempt is safe when the first
    response is interrupted after Supabase commits it.
    """

    last_error: Exception | None = None

    for attempt in range(2):
        active_client = (
            supabase
            if attempt == 0
            else create_supabase_client()
        )

        try:
            active_client.auth.set_session(
                access_token,
                refresh_token,
            )

            response = (
                active_client.auth.update_user(
                    update_payload
                )
            )

            return active_client, response

        except Exception as error:
            last_error = error

            if (
                not is_transient_connection_error(
                    error
                )
                or attempt >= 1
            ):
                raise

            logger.warning(
                (
                    "Transient Supabase connection "
                    "failure while updating a user. "
                    "Retrying once."
                )
            )

            time.sleep(0.35)

    raise last_error or RuntimeError(
        "Unable to update the authenticated user."
    )


def get_authenticated_supabase(
    request: Request,
) -> tuple[
    Client,
    Any,
    str,
    str,
]:
    """
    Restore the authenticated Supabase session.

    Temporary HTTP/2 disconnects are retried and return
    503 instead of being incorrectly reported as a 401.
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

    last_error: Exception | None = None

    for attempt in range(3):
        supabase = create_supabase_client()

        try:
            session_response = (
                supabase.auth.set_session(
                    access_token,
                    refresh_token,
                )
            )

            restored_session = get_attribute(
                session_response,
                "session",
            )

            current_access_token = (
                get_attribute(
                    restored_session,
                    "access_token",
                )
                or access_token
            )

            current_refresh_token = (
                get_attribute(
                    restored_session,
                    "refresh_token",
                )
                or refresh_token
            )

            current_user = (
                get_attribute(
                    session_response,
                    "user",
                )
                or get_attribute(
                    restored_session,
                    "user",
                )
            )

            if not current_user:
                user_response = (
                    supabase.auth.get_user(
                        current_access_token
                    )
                )

                current_user = get_attribute(
                    user_response,
                    "user",
                )

            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "Your login session is no longer "
                        "valid. Please log in again."
                    ),
                )

            current_metadata = (
                get_attribute(
                    current_user,
                    "user_metadata",
                    {},
                )
                or {}
            )

            if (
                current_metadata.get(
                    "account_status"
                )
                == ACCOUNT_STATUS_PENDING_DELETION
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
                current_access_token
            )

            request.state.villa_refresh_token = (
                current_refresh_token
            )

            return (
                supabase,
                current_user,
                current_access_token,
                current_refresh_token,
            )

        except HTTPException:
            raise

        except Exception as error:
            last_error = error

            if (
                is_transient_connection_error(
                    error
                )
                and attempt < 2
            ):
                logger.warning(
                    (
                        "Temporary Supabase auth "
                        "connection interruption. "
                        "Retry %s of 2."
                    ),
                    attempt + 1,
                )

                time.sleep(
                    0.3 * (attempt + 1)
                )
                continue

            if is_transient_connection_error(
                error
            ):
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "The Villa authentication "
                        "connection was interrupted. "
                        "Please try again."
                    ),
                ) from error

            raise HTTPException(
                status_code=401,
                detail=readable_auth_error(
                    error
                ),
            ) from error

    raise HTTPException(
        status_code=503,
        detail=(
            "The Villa authentication connection "
            "was interrupted. Please try again."
        ),
    ) from last_error



def sync_profile(
    supabase: Client,
    user_data: dict[str, Any] | None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    tolerate_transient_failure: bool = False,
) -> bool:
    """
    Store only safe profile information.

    The public profile is a searchable mirror of the
    authenticated user's metadata. Short-lived Supabase
    connection interruptions are retried with a fresh
    client so raw ConnectionTerminated details are never
    exposed to the customer.
    """

    if not user_data or not user_data.get("id"):
        return False

    profile_data = jsonable_encoder(
        {
            "id": user_data["id"],
            "first_name": user_data.get(
                "first_name"
            ),
            "last_name": user_data.get(
                "last_name"
            ),
            "full_name": user_data.get(
                "full_name"
            ),
            "email": user_data.get("email"),
            "phone": user_data.get("phone"),
            "avatar_url": user_data.get(
                "avatar_url"
            ),
            "provider": user_data.get(
                "provider",
                "email",
            ),
            "google_user_id": user_data.get(
                "google_user_id"
            ),
            "email_verified": bool(
                user_data.get("email_verified")
            ),
            "phone_verified": bool(
                user_data.get("phone_verified")
            ),
            "last_sign_in_at": user_data.get(
                "last_sign_in_at"
            ),
            "terms_accepted_at": user_data.get(
                "terms_accepted_at"
            ),
            "privacy_accepted_at": user_data.get(
                "privacy_accepted_at"
            ),
            "terms_version": user_data.get(
                "terms_version"
            ),
            "privacy_version": user_data.get(
                "privacy_version"
            ),
            "account_status": user_data.get(
                "account_status",
                ACCOUNT_STATUS_ACTIVE,
            ),
            "deletion_requested_at": user_data.get(
                "deletion_requested_at"
            ),
            "deletion_due_at": user_data.get(
                "deletion_due_at"
            ),
        },
        exclude_none=False,
    )

    last_error: Exception | None = None

    for attempt in range(3):
        active_client = (
            supabase
            if attempt == 0
            else create_supabase_client()
        )

        try:
            if access_token and refresh_token:
                active_client.auth.set_session(
                    access_token,
                    refresh_token,
                )

            (
                active_client.table("profiles")
                .upsert(
                    profile_data,
                    on_conflict="id",
                )
                .execute()
            )

            return True

        except Exception as error:
            last_error = error
            error_message = str(error).lower()

            if (
                "profiles_phone_unique"
                in error_message
                and user_data.get(
                    "provider"
                ) != "phone"
            ):
                logger.warning(
                    (
                        "Retrying profile sync without "
                        "a conflicting stale phone. "
                        "User=%s"
                    ),
                    user_data["id"],
                )

                profile_data["phone"] = None
                profile_data[
                    "phone_verified"
                ] = False

                try:
                    (
                        active_client
                        .table("profiles")
                        .upsert(
                            profile_data,
                            on_conflict="id",
                        )
                        .execute()
                    )

                    return True

                except Exception as retry_error:
                    last_error = retry_error
                    error = retry_error
                    error_message = str(
                        retry_error
                    ).lower()

            if (
                "profiles_phone_unique"
                in error_message
                and user_data.get(
                    "provider"
                ) == "phone"
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This phone number is already "
                        "connected to another account. "
                        "Use a different number."
                    ),
                ) from error

            if (
                is_transient_connection_error(
                    error
                )
                and attempt < 2
            ):
                logger.warning(
                    (
                        "Transient profile database "
                        "connection failure for user %s. "
                        "Retry %s of 2."
                    ),
                    user_data["id"],
                    attempt + 1,
                )

                time.sleep(
                    0.25 * (attempt + 1)
                )
                continue

            if (
                is_transient_connection_error(
                    error
                )
                and tolerate_transient_failure
            ):
                logger.exception(
                    (
                        "Profile metadata was saved, "
                        "but the public profile mirror "
                        "could not be synchronized."
                    )
                )

                return False

            raise

    if (
        last_error
        and tolerate_transient_failure
        and is_transient_connection_error(
            last_error
        )
    ):
        return False

    if last_error:
        raise last_error

    return False


def normalize_webhook_secret(
    secret: str,
) -> str:
    """
    Convert the Supabase dashboard secret into the
    base64 value expected by standardwebhooks.

    Supabase displays:
        v1,whsec_<base64_secret>

    standardwebhooks.Webhook expects:
        <base64_secret>
    """

    cleaned = (
        secret.strip()
        .strip('"')
        .strip("'")
    )

    full_prefix = "v1,whsec_"
    short_prefix = "whsec_"

    if cleaned.startswith(full_prefix):
        return cleaned[len(full_prefix):]

    if cleaned.startswith(short_prefix):
        return cleaned[len(short_prefix):]

    return cleaned


def require_httpsms_configuration() -> None:
    missing = []

    if not HTTPSMS_API_KEY:
        missing.append("HTTPSMS_API_KEY")

    if not HTTPSMS_FROM:
        missing.append("HTTPSMS_FROM")

    if not SUPABASE_SMS_HOOK_SECRET:
        missing.append(
            "SUPABASE_SMS_HOOK_SECRET"
        )

    if missing:
        logger.error(
            "Phone OTP configuration is missing: %s",
            ", ".join(missing),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Phone OTP is not configured. Missing: "
                + ", ".join(missing)
            ),
        )


async def send_httpsms_message(
    destination: str,
    otp: str,
) -> None:
    require_httpsms_configuration()

    normalized_from = normalize_ph_phone(
        HTTPSMS_FROM
    )
    normalized_to = normalize_ph_phone(
        destination
    )

    payload = {
        "from": normalized_from,
        "to": normalized_to,
        "content": (
            f"The Villa verification code is {otp}. "
            "Do not share this code with anyone."
        ),
        "request_id": str(uuid.uuid4()),
    }

    # Use the exact request format documented by httpSMS:
    # explicit JSON serialization and explicit Content-Type.
    serialized_payload = json.dumps(
        payload,
        separators=(",", ":"),
    )

    headers = {
        "x-api-key": str(
            HTTPSMS_API_KEY
        ).strip(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    logger.info(
        (
            "Sending httpSMS request. "
            "From=%s To=%s Content-Type=%s"
        ),
        normalized_from,
        normalized_to,
        headers["Content-Type"],
    )

    def perform_request():
        return requests.post(
            HTTPSMS_SEND_URL,
            headers=headers,
            data=serialized_payload,
            timeout=6,
            allow_redirects=True,
        )

    try:
        response = await asyncio.to_thread(
            perform_request
        )

    except requests.RequestException as error:
        logger.exception(
            "Could not connect to httpSMS for destination %s",
            normalized_to,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not connect to httpSMS. "
                "Make sure the Android gateway phone "
                "is online and try again."
            ),
        ) from error

    response_content_type = (
        response.headers.get(
            "Content-Type",
            "",
        )
    )

    logger.info(
        (
            "httpSMS response received. "
            "Status=%s Content-Type=%s"
        ),
        response.status_code,
        response_content_type or "missing",
    )

    if (
        response.status_code < 200
        or response.status_code >= 300
    ):
        try:
            provider_error = response.json()
        except ValueError:
            provider_error = response.text

        logger.error(
            (
                "httpSMS rejected the SMS. "
                "Status=%s Response=%s"
            ),
            response.status_code,
            provider_error,
        )

        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "httpSMS rejected the OTP message."
                ),
                "provider_status": (
                    response.status_code
                ),
                "provider_response": provider_error,
                "from": normalized_from,
                "to": normalized_to,
            },
        )

    logger.info(
        "httpSMS accepted OTP delivery for %s",
        normalized_to,
    )


def decode_profile_photo(
    image_data: str,
) -> bytes:
    prefix = "data:image/jpeg;base64,"

    if not image_data.startswith(prefix):
        raise HTTPException(
            status_code=422,
            detail=(
                "The profile photo must be a prepared "
                "JPEG image."
            ),
        )

    encoded_image = image_data[len(prefix):]

    try:
        image_bytes = base64.b64decode(
            encoded_image,
            validate=True,
        )
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "The selected profile photo is invalid."
            ),
        ) from error

    if not image_bytes.startswith(
        b"\xff\xd8\xff"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "The selected profile photo is not "
                "a valid JPEG image."
            ),
        )

    if len(image_bytes) > PROFILE_PHOTO_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "The prepared profile photo must be "
                "2 MB or smaller."
            ),
        )

    return image_bytes


def readable_auth_error(
    error: Exception,
) -> str:
    message = str(error).strip()

    if is_transient_connection_error(
        error
    ):
        return (
            "The Villa database connection was "
            "interrupted. Please try again."
        )

    replacements = {
        "Invalid login credentials": (
            "Invalid email or password."
        ),
        "Email not confirmed": (
            "Your email is not confirmed. "
            "Confirm your email first."
        ),
        "User already registered": (
            "An account with this email already exists."
        ),
        "Unsupported provider": (
            "The selected authentication provider "
            "is not enabled in Supabase."
        ),
        "Invalid token": (
            "The verification code is invalid. "
            "Check the code and try again."
        ),
        "Token has expired": (
            "The verification code has expired. "
            "Request a new code."
        ),
        "Otp expired": (
            "The verification code has expired. "
            "Request a new code."
        ),
        "Token has been expired or is invalid": (
            "The verification code is invalid or "
            "expired. Request a new code."
        ),
        "Signups not allowed for otp": (
            "No account exists for this phone number. "
            "Choose Create Account first."
        ),
        "Object of type datetime is not JSON serializable": (
            "A profile timestamp could not be saved. "
            "Restart the backend with the updated code."
        ),
        "profiles_phone_unique": (
            "This phone number is already connected "
            "to another account. Log in with that "
            "phone number or use a different number."
        ),
        "duplicate key value violates unique constraint": (
            "This account information is already "
            "connected to another user."
        ),
        "email address is already registered": (
            "That email address is already connected "
            "to another account."
        ),
        "phone number already registered": (
            "That phone number is already connected "
            "to another account."
        ),
        "user already registered": (
            "That email address or phone number is "
            "already connected to another account."
        ),
        "same password": (
            "Choose a password that is different "
            "from your current password."
        ),
        "new password should be different": (
            "Choose a password that is different "
            "from your current password."
        ),
    }

    for original, replacement in replacements.items():
        if original.lower() in message.lower():
            return replacement

    return (
        message
        or "Authentication request failed."
    )


@app.get("/")
def root():
    frontend_dist = os.getenv("FRONTEND_DIST", "").strip()
    if frontend_dist:
        return FileResponse(Path(frontend_dist) / "index.html")
    return {
        "name": "The Villa Authentication API",
        "status": "running",
        "database": "Supabase",
        "email_login": "enabled",
        "google_login": "enabled",
        "phone_otp": "enabled",
        "sms_gateway": "httpSMS",
        "profile_table": "public.profiles",
        "account_method_policy": (
            "one permanent sign-in method "
            "per account"
        ),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }



def parse_account_timestamp(
    value: Any,
) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def delete_supabase_auth_user(
    user_id: str,
) -> None:
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "SUPABASE_SERVICE_ROLE_KEY is required "
                "for permanent account deletion."
            ),
        )

    response = requests.delete(
        (
            f"{SUPABASE_URL}/auth/v1/admin/users/"
            f"{user_id}"
        ),
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": (
                f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
            ),
            "Accept": "application/json",
        },
        timeout=(5, 25),
    )

    if response.status_code not in {
        200,
        204,
        404,
    }:
        logger.error(
            "Supabase auth user deletion failed for %s: %s",
            user_id,
            response.text[:1000],
        )

        raise RuntimeError(
            "Supabase rejected permanent user deletion."
        )


def permanently_delete_customer_account(
    user_id: str,
) -> None:
    service = (
        create_service_supabase_client()
    )

    # Booking rows contain the customer's booking history,
    # payment references, and generated receipt details.
    try:
        (
            service.table("bookings")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "Could not delete bookings for expired account %s.",
            user_id,
        )
        raise

    try:
        (
            service.storage
            .from_(PROFILE_PHOTO_BUCKET)
            .remove([
                f"{user_id}/avatar.jpg"
            ])
        )
    except Exception as storage_error:
        lowered = str(
            storage_error
        ).lower()

        if (
            "not found" not in lowered
            and "does not exist" not in lowered
        ):
            logger.warning(
                "Could not remove profile photo for expired account %s.",
                user_id,
            )

    delete_supabase_auth_user(
        user_id
    )

    try:
        (
            service.table("profiles")
            .delete()
            .eq("id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "Could not delete profile row for expired account %s.",
            user_id,
        )
        raise


def purge_expired_customer_accounts() -> int:
    if not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "Account cleanup skipped because SUPABASE_SERVICE_ROLE_KEY is missing."
        )
        return 0

    service = (
        create_service_supabase_client()
    )

    now_iso = datetime.now(
        timezone.utc
    ).isoformat()

    response = (
        service.table("profiles")
        .select(
            "id,deletion_due_at"
        )
        .eq(
            "account_status",
            ACCOUNT_STATUS_PENDING_DELETION,
        )
        .lte(
            "deletion_due_at",
            now_iso,
        )
        .execute()
    )

    rows = get_attribute(
        response,
        "data",
        [],
    ) or []

    deleted_count = 0

    for row in rows:
        user_id = str(
            row.get("id")
            if isinstance(row, dict)
            else ""
        ).strip()

        if not user_id:
            continue

        try:
            permanently_delete_customer_account(
                user_id
            )
            deleted_count += 1
        except Exception:
            logger.exception(
                "Permanent cleanup failed for account %s.",
                user_id,
            )

    if deleted_count:
        logger.info(
            "Permanently deleted %s expired customer account(s).",
            deleted_count,
        )

    return deleted_count


def restore_pending_account_after_login(
    supabase: Client,
    user: Any,
    access_token: str,
    refresh_token: str,
) -> tuple[Any, bool, str | None]:
    metadata = (
        get_attribute(
            user,
            "user_metadata",
            {},
        )
        or {}
    )

    account_status = metadata.get(
        "account_status",
        ACCOUNT_STATUS_ACTIVE,
    )

    if (
        account_status
        != ACCOUNT_STATUS_PENDING_DELETION
    ):
        return user, False, None

    deletion_due_at = (
        parse_account_timestamp(
            metadata.get(
                "deletion_due_at"
            )
        )
    )

    now = datetime.now(
        timezone.utc
    )

    user_id = str(
        get_attribute(
            user,
            "id",
            "",
        )
    ).strip()

    if (
        deletion_due_at
        and now >= deletion_due_at
    ):
        if user_id:
            permanently_delete_customer_account(
                user_id
            )

        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        raise HTTPException(
            status_code=410,
            detail=(
                "The 30-day account recovery period has expired. "
                "This account and its stored data were permanently deleted."
            ),
        )

    updated_response = (
        supabase.auth.update_user(
            {
                "data": {
                    **metadata,
                    "account_status": (
                        ACCOUNT_STATUS_ACTIVE
                    ),
                    "deletion_requested_at": None,
                    "deletion_due_at": None,
                    "account_restored_at": (
                        now.isoformat()
                    ),
                }
            }
        )
    )

    restored_user = (
        get_attribute(
            updated_response,
            "user",
        )
        or user
    )

    if user_id:
        service = (
            create_service_supabase_client()
        )

        (
            service.table("profiles")
            .upsert(
                {
                    "id": user_id,
                    "account_status": (
                        ACCOUNT_STATUS_ACTIVE
                    ),
                    "deletion_requested_at": None,
                    "deletion_due_at": None,
                },
                on_conflict="id",
            )
            .execute()
        )

    return (
        restored_user,
        True,
        (
            "Welcome back. Your Villa account, booking history, "
            "payment receipts, and customer records have been "
            "restored successfully."
        ),
    )


@app.post("/auth/session/refresh")
def refresh_auth_session(
    data: SessionRefreshRequest,
):
    raw_refresh_token = (
        data.refresh_token
    )

    refresh_token = (
        raw_refresh_token.strip()
        if isinstance(
            raw_refresh_token,
            str,
        )
        else ""
    )

    if (
        not refresh_token
        or refresh_token.lower()
        in {
            "undefined",
            "null",
            "none",
        }
        or len(refresh_token) < 20
        or len(refresh_token) > 4096
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Your saved login session is invalid. "
                "Please log in again."
            ),
        )

    refreshed = (
        refresh_session_via_supabase_rest(
            refresh_token
        )
    )

    user_data = user_to_dict(
        refreshed.get("user")
    )

    if not user_data:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session is no longer "
                "valid. Please log in again."
            ),
        )

    return {
        "message": (
            "Login session refreshed."
        ),
        "authenticated": True,
        "user": user_data,
        "access_token": refreshed.get(
            "access_token"
        ),
        "refresh_token": refreshed.get(
            "refresh_token"
        ),
        "expires_in": refreshed.get(
            "expires_in"
        ),
        "token_type": refreshed.get(
            "token_type",
            "bearer",
        ),
    }


@app.post("/auth/register")
def register_user(
    data: RegisterRequest,
):
    first_name = data.first_name.strip()
    last_name = data.last_name.strip()

    email = str(
        data.email
    ).strip().lower()

    full_name = (
        f"{first_name} {last_name}".strip()
    )

    require_legal_acceptance(
        data.terms_accepted,
        data.privacy_accepted,
        data.terms_version,
        data.privacy_version,
    )

    legal_metadata = legal_acceptance_metadata()

    try:
        supabase = create_supabase_client()

        response = supabase.auth.sign_up(
            {
                "email": email,
                "password": data.password,
                "options": {
                    "data": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "full_name": full_name,
                        "profile_first_name": first_name,
                        "profile_last_name": last_name,
                        "profile_full_name": full_name,
                        "profile_name_customized": True,
                        "provider": "email",
                        "account_origin": "email",
                        "account_role": "client",
                        "last_login_method": "email",
                        "password_enabled": True,
                        **legal_metadata,
                    }
                },
            }
        )

        auth_data = auth_response_to_dict(
            response
        )

        if (
            auth_data["access_token"]
            and auth_data["user"]
        ):
            sync_profile(
                supabase,
                auth_data["user"],
                auth_data["access_token"],
                auth_data["refresh_token"],
            )

            return {
                "message": (
                    "Account created and logged "
                    "in successfully."
                ),
                "authenticated": True,
                "email_confirmation_required": False,
                **auth_data,
            }

        if is_obfuscated_existing_user(
            response
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This email already has a Villa "
                    "account. Use the sign-in method "
                    "chosen when the account was first "
                    "created. The same email cannot be "
                    "registered under another method."
                ),
            )

        if auth_data["user"]:
            return {
                "message": (
                    "Account created successfully. "
                    "Please check your email and "
                    "confirm your account before "
                    "logging in."
                ),
                "authenticated": False,
                "email_confirmation_required": True,
                **auth_data,
            }

        raise HTTPException(
            status_code=400,
            detail=(
                "Supabase did not return a "
                "created user."
            ),
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=readable_auth_error(error),
        ) from error


@app.post("/auth/login")
def login_user(
    data: LoginRequest,
):
    try:
        supabase = create_supabase_client()

        response = (
            supabase.auth.sign_in_with_password(
                {
                    "email": str(
                        data.email
                    ).strip().lower(),
                    "password": data.password,
                }
            )
        )

        auth_data = auth_response_to_dict(
            response
        )

        if (
            not auth_data["access_token"]
            or not auth_data["user"]
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Supabase did not return a "
                    "valid login session."
                ),
            )

        raw_user = get_attribute(
            response,
            "user",
        )

        try:
            require_account_method(
                raw_user,
                "email",
            )
        except HTTPException:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            raise

        supabase.auth.set_session(
            auth_data["access_token"],
            auth_data["refresh_token"],
        )

        restored_user, account_restored, restoration_message = (
            restore_pending_account_after_login(
                supabase,
                get_attribute(
                    response,
                    "user",
                ),
                auth_data["access_token"],
                auth_data["refresh_token"],
            )
        )

        logged_in_user = update_login_context(
            supabase,
            restored_user,
            "email",
            password_enabled=True,
        )

        auth_data["user"] = user_to_dict(
            logged_in_user
        )

        sync_profile(
            supabase,
            auth_data["user"],
            auth_data["access_token"],
            auth_data["refresh_token"],
        )

        return {
            "message": "Login successful.",
            "authenticated": True,
            "account_restored": account_restored,
            "restoration_message": restoration_message,
            **auth_data,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=401,
            detail=readable_auth_error(error),
        ) from error


@app.post("/auth/google")
def login_with_google(
    data: GoogleLoginRequest,
):
    if data.create_account:
        require_legal_acceptance(
            data.terms_accepted,
            data.privacy_accepted,
            data.terms_version,
            data.privacy_version,
        )

    try:
        auth_data = (
            sign_in_with_google_id_token(
                data.credential,
                data.nonce,
            )
        )

        raw_user = auth_data.get(
            "user"
        )

        if not isinstance(
            raw_user,
            dict,
        ):
            raise HTTPException(
                status_code=502,
                detail=(
                    "Supabase did not return a "
                    "valid Google user."
                ),
            )

        require_account_method(
            raw_user,
            "google",
        )

        supabase = (
            create_supabase_client()
        )

        supabase.auth.set_session(
            str(
                auth_data[
                    "access_token"
                ]
            ),
            str(
                auth_data[
                    "refresh_token"
                ]
            ),
        )

        raw_user, account_restored, restoration_message = (
            restore_pending_account_after_login(
                supabase,
                raw_user,
                str(
                    auth_data[
                        "access_token"
                    ]
                ),
                str(
                    auth_data[
                        "refresh_token"
                    ]
                ),
            )
        )

        google_metadata = (
            build_google_name_metadata(
                raw_user,
                data.credential,
            )
        )

        if data.create_account:
            google_metadata.update(
                legal_acceptance_metadata()
            )

        logged_in_user = (
            update_login_context(
                supabase,
                raw_user,
                "google",
                extra_metadata=(
                    google_metadata
                ),
            )
        )

        auth_data["user"] = (
            user_to_dict(
                logged_in_user
            )
        )

        sync_profile(
            supabase,
            auth_data["user"],
            str(
                auth_data[
                    "access_token"
                ]
            ),
            str(
                auth_data[
                    "refresh_token"
                ]
            ),
        )

        return {
            "message":
                "Google login successful.",
            "authenticated": True,
            "account_restored": account_restored,
            "restoration_message": restoration_message,
            **auth_data,
        }

    except HTTPException:
        raise

    except Exception as error:
        logger.exception(
            "Google authentication failed."
        )

        raise HTTPException(
            status_code=401,
            detail=readable_auth_error(
                error
            ),
        ) from error


@app.post("/auth/phone/send")
def send_phone_otp(
    data: PhoneOtpRequest,
):
    phone = normalize_ph_phone(
        data.phone_number
    )

    first_name = (
        data.first_name or ""
    ).strip()

    last_name = (
        data.last_name or ""
    ).strip()

    if data.create_account:
        require_legal_acceptance(
            data.terms_accepted,
            data.privacy_accepted,
            data.terms_version,
            data.privacy_version,
        )

        if not first_name:
            raise HTTPException(
                status_code=422,
                detail=(
                    "First name is required when "
                    "creating a phone account."
                ),
            )

        if not last_name:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Last name is required when "
                    "creating a phone account."
                ),
            )

    full_name = (
        f"{first_name} {last_name}".strip()
    )

    options: dict[str, Any] = {
        "should_create_user": (
            data.create_account
        ),
        "channel": "sms",
    }

    if data.create_account:
        options["data"] = {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "profile_first_name": first_name,
            "profile_last_name": last_name,
            "profile_full_name": full_name,
            "profile_name_customized": True,
            "provider": "phone",
            "account_origin": "phone",
            "account_role": "client",
            "last_login_method": "phone",
            "password_enabled": False,
            **legal_acceptance_metadata(),
        }

    try:
        supabase = create_supabase_client()

        supabase.auth.sign_in_with_otp(
            {
                "phone": phone,
                "options": options,
            }
        )

        return {
            "message": (
                "A 6-digit verification code was "
                f"sent to {phone}."
            ),
            "phone": phone,
            "otp_sent": True,
        }

    except HTTPException:
        raise

    except Exception as error:
        message = readable_auth_error(error)
        lowered = message.lower()

        status_code = (
            502
            if (
                "hook" in lowered
                or "httpsms" in lowered
                or "unexpected status code" in lowered
                or "bad gateway" in lowered
            )
            else 400
        )

        logger.error(
            "Phone OTP send failed. Status=%s Error=%s",
            status_code,
            message,
        )

        raise HTTPException(
            status_code=status_code,
            detail=message,
        ) from error


@app.post("/auth/phone/verify")
def verify_phone_otp(
    data: PhoneOtpVerifyRequest,
):
    phone = normalize_ph_phone(
        data.phone_number
    )

    try:
        supabase = create_supabase_client()

        response = supabase.auth.verify_otp(
            {
                "phone": phone,
                "token": data.otp,
                "type": "sms",
            }
        )

        auth_data = auth_response_to_dict(
            response
        )

        if (
            not auth_data["access_token"]
            or not auth_data["user"]
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Supabase did not return a "
                    "valid phone login session."
                ),
            )

        raw_user = get_attribute(
            response,
            "user",
        )

        try:
            require_account_method(
                raw_user,
                "phone",
            )
        except HTTPException:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            raise

        supabase.auth.set_session(
            auth_data["access_token"],
            auth_data["refresh_token"],
        )

        restored_user, account_restored, restoration_message = (
            restore_pending_account_after_login(
                supabase,
                get_attribute(
                    response,
                    "user",
                ),
                auth_data["access_token"],
                auth_data["refresh_token"],
            )
        )

        logged_in_user = update_login_context(
            supabase,
            restored_user,
            "phone",
        )

        auth_data["user"] = user_to_dict(
            logged_in_user
        )

        sync_profile(
            supabase,
            auth_data["user"],
            auth_data["access_token"],
            auth_data["refresh_token"],
        )

        return {
            "message": (
                "Phone number verified successfully."
            ),
            "authenticated": True,
            "account_restored": account_restored,
            "restoration_message": restoration_message,
            **auth_data,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=401,
            detail=readable_auth_error(error),
        ) from error



@app.post("/auth/account/delete")
def request_account_deletion(
    data: AccountDeleteRequest,
    request: Request,
):
    if (
        data.confirmation.strip().upper()
        != "DELETE"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Type DELETE exactly to confirm account deletion."
            ),
        )

    (
        supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    user_id = str(
        get_attribute(
            current_user,
            "id",
            "",
        )
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your login session is no longer valid. "
                "Please log in again."
            ),
        )

    now = datetime.now(
        timezone.utc
    )

    deletion_due_at = (
        now
        + timedelta(
            days=ACCOUNT_DELETION_GRACE_DAYS
        )
    )

    existing_metadata = (
        get_attribute(
            current_user,
            "user_metadata",
            {},
        )
        or {}
    )

    try:
        updated_response = (
            supabase.auth.update_user(
                {
                    "data": {
                        **existing_metadata,
                        "account_status": (
                            ACCOUNT_STATUS_PENDING_DELETION
                        ),
                        "deletion_requested_at": (
                            now.isoformat()
                        ),
                        "deletion_due_at": (
                            deletion_due_at.isoformat()
                        ),
                    }
                }
            )
        )

        updated_user = (
            get_attribute(
                updated_response,
                "user",
            )
            or current_user
        )

        service = (
            create_service_supabase_client()
        )

        (
            service.table("profiles")
            .upsert(
                {
                    "id": user_id,
                    "account_status": (
                        ACCOUNT_STATUS_PENDING_DELETION
                    ),
                    "deletion_requested_at": (
                        now.isoformat()
                    ),
                    "deletion_due_at": (
                        deletion_due_at.isoformat()
                    ),
                },
                on_conflict="id",
            )
            .execute()
        )

        return {
            "message": (
                "Your account is now deactivated and scheduled for "
                "permanent deletion in 30 days. Sign in again using "
                "the same email or linked sign-in method before "
                f"{deletion_due_at.strftime('%B %d, %Y')} to restore "
                "your account, booking history, receipts, and customer data."
            ),
            "account_status": (
                ACCOUNT_STATUS_PENDING_DELETION
            ),
            "deletion_requested_at": (
                now.isoformat()
            ),
            "deletion_due_at": (
                deletion_due_at.isoformat()
            ),
            "grace_period_days": (
                ACCOUNT_DELETION_GRACE_DAYS
            ),
            "user": user_to_dict(
                updated_user
            ),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    except HTTPException:
        raise

    except Exception as error:
        logger.exception(
            "Account deletion request failed for user %s.",
            user_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to schedule account deletion. "
                "Please try again."
            ),
        ) from error


@app.get("/auth/profile")
def get_profile(
    request: Request,
):
    (
        _supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    user_data = user_to_dict(
        current_user
    )

    return {
        "message": (
            "Profile loaded successfully."
        ),
        "authenticated": True,
        "user": user_data,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@app.put("/auth/profile")
def update_profile(
    data: ProfileUpdateRequest,
    request: Request,
):
    (
        supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    first_name = data.first_name.strip()
    last_name = data.last_name.strip()

    if not first_name:
        raise HTTPException(
            status_code=422,
            detail="First name is required.",
        )

    if not last_name:
        raise HTTPException(
            status_code=422,
            detail="Last name is required.",
        )

    full_name = (
        f"{first_name} {last_name}".strip()
    )

    requested_email = (
        str(data.email).strip().lower()
        if data.email
        else ""
    )

    if (
        not data.phone_number
        or not data.phone_number.strip()
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Phone number is required before "
                "booking a villa."
            ),
        )

    requested_phone = (
        normalize_ph_phone(
            data.phone_number
        )
    )

    current_user_data = (
        user_to_dict(current_user)
        or {}
    )

    account_origin = (
        current_user_data.get(
            "account_origin"
        )
        or current_user_data.get(
            "provider",
            "email",
        )
    )

    auth_email = str(
        current_user_data.get(
            "auth_email"
        )
        or ""
    ).strip().lower()

    auth_phone = (
        current_user_data.get(
            "auth_phone"
        )
    )

    existing_metadata = (
        get_attribute(
            current_user,
            "user_metadata",
            {},
        )
        or {}
    )

    updated_metadata = {
        **existing_metadata,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "profile_first_name": first_name,
        "profile_last_name": last_name,
        "profile_full_name": full_name,
        "profile_name_customized": True,
        "profile_name_updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "provider": account_origin,
        "account_origin": account_origin,
        "last_login_method": account_origin,
        "password_enabled": (
            account_origin == "email"
        ),
    }

    update_payload: dict[str, Any] = {
        "data": updated_metadata,
    }

    email_change_requested = False
    phone_change_requested = False

    if account_origin == "email":
        if not requested_email:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Email address is required for an "
                    "email and password account."
                ),
            )

        if requested_email != auth_email:
            update_payload["email"] = (
                requested_email
            )
            email_change_requested = True

        updated_metadata[
            "contact_email"
        ] = None
        updated_metadata[
            "contact_phone"
        ] = requested_phone

    elif account_origin == "google":
        if (
            requested_email
            and auth_email
            and requested_email != auth_email
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This account uses Google sign-in. "
                    "The Google email cannot be changed "
                    "inside The Villa."
                ),
            )

        updated_metadata[
            "contact_email"
        ] = None
        updated_metadata[
            "contact_phone"
        ] = requested_phone

    elif account_origin == "phone":
        if not requested_phone:
            requested_phone = auth_phone

        if not requested_phone:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Phone number is required for a "
                    "phone verification account."
                ),
            )

        if requested_phone != auth_phone:
            update_payload["phone"] = (
                requested_phone
            )
            phone_change_requested = True

        updated_metadata[
            "contact_email"
        ] = (
            requested_email
            if requested_email
            else None
        )
        updated_metadata[
            "contact_phone"
        ] = None

    update_payload["data"] = (
        updated_metadata
    )

    try:
        (
            profile_supabase,
            response,
        ) = update_authenticated_user_with_retry(
            supabase,
            update_payload,
            access_token,
            refresh_token,
        )

        updated_user = (
            get_attribute(
                response,
                "user",
            )
            or current_user
        )

        updated_user_data = user_to_dict(
            updated_user
        )

        profile_mirror_synced = sync_profile(
            profile_supabase,
            updated_user_data,
            access_token,
            refresh_token,
            tolerate_transient_failure=True,
        )

        confirmation_messages = []

        if email_change_requested:
            confirmation_messages.append(
                "Check your new email address for "
                "the confirmation message."
            )

        if phone_change_requested:
            confirmation_messages.append(
                "Complete the verification sent to "
                "your new phone number."
            )

        message = (
            "Profile updated successfully."
        )

        if confirmation_messages:
            message += " " + " ".join(
                confirmation_messages
            )

        if not profile_mirror_synced:
            message += (
                " Your account details were saved. "
                "The database copy will synchronize "
                "automatically on your next sign-in."
            )

        return {
            "message": message,
            "authenticated": True,
            "user": updated_user_data,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email_confirmation_required": (
                email_change_requested
            ),
            "phone_confirmation_required": (
                phone_change_requested
            ),
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=readable_auth_error(
                error
            ),
        ) from error


@app.post("/auth/change-password")
def change_password(
    data: PasswordChangeRequest,
    request: Request,
):
    (
        supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    current_user_data = (
        user_to_dict(current_user)
        or {}
    )

    account_origin = (
        current_user_data.get(
            "account_origin"
        )
        or current_user_data.get(
            "provider",
            "email",
        )
    )

    password_enabled = bool(
        current_user_data.get(
            "password_enabled"
        )
    )

    if account_origin == "google":
        raise HTTPException(
            status_code=409,
            detail=(
                "This session uses Google sign-in. "
                "Change your password through your "
                "Google Account security settings."
            ),
        )

    if account_origin == "phone":
        raise HTTPException(
            status_code=409,
            detail=(
                "This session uses phone verification. "
                "There is no permanent Villa password "
                "to change."
            ),
        )

    if not password_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Password changes are available only "
                "after signing in with email and password."
            ),
        )

    current_email = str(
        get_attribute(
            current_user,
            "email",
            "",
        )
        or ""
    ).strip().lower()

    if not current_email:
        raise HTTPException(
            status_code=400,
            detail=(
                "A verified email account is required "
                "to confirm the current password."
            ),
        )

    if data.old_password == data.new_password:
        raise HTTPException(
            status_code=422,
            detail=(
                "Your new password must be different "
                "from your current password."
            ),
        )

    # Verify the old password using a separate client.
    # The old password is never saved or logged.
    try:
        verification_client = (
            create_supabase_client()
        )

        verification_client.auth.sign_in_with_password(
            {
                "email": current_email,
                "password": data.old_password,
            }
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "The current password is incorrect."
            ),
        ) from error

    try:
        response = (
            supabase.auth.update_user(
                {
                    "password": (
                        data.new_password
                    )
                }
            )
        )

        updated_user = (
            get_attribute(
                response,
                "user",
            )
            or current_user
        )

        updated_user = update_login_context(
            supabase,
            updated_user,
            "email",
            password_enabled=True,
        )

        return {
            "message": (
                "Your password was changed "
                "successfully."
            ),
            "authenticated": True,
            "user": user_to_dict(
                updated_user
            ),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=readable_auth_error(
                error
            ),
        ) from error


@app.post("/auth/profile/avatar")
def upload_profile_avatar(
    data: ProfileAvatarRequest,
    request: Request,
):
    (
        supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    user_id = str(
        get_attribute(
            current_user,
            "id",
            "",
        )
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your account could not be identified. "
                "Please log in again."
            ),
        )

    image_bytes = decode_profile_photo(
        data.image_data
    )

    object_path = (
        f"{user_id}/avatar.jpg"
    )

    try:
        (
            supabase.storage
            .from_(PROFILE_PHOTO_BUCKET)
            .upload(
                path=object_path,
                file=image_bytes,
                file_options={
                    "cache-control": "3600",
                    "content-type": "image/jpeg",
                    "upsert": "true",
                },
            )
        )

        cache_version = int(
            datetime.now(
                timezone.utc
            ).timestamp()
        )

        avatar_url = (
            f"{SUPABASE_URL}/storage/v1/object/"
            f"public/{PROFILE_PHOTO_BUCKET}/"
            f"{object_path}?v={cache_version}"
        )

        existing_metadata = (
            get_attribute(
                current_user,
                "user_metadata",
                {},
            )
            or {}
        )

        updated_response = (
            supabase.auth.update_user(
                {
                    "data": {
                        **existing_metadata,
                        "custom_avatar_url": (
                            avatar_url
                        ),
                        "avatar_removed": False,
                    }
                }
            )
        )

        updated_user = (
            get_attribute(
                updated_response,
                "user",
            )
            or current_user
        )

        updated_user_data = user_to_dict(
            updated_user
        )

        sync_profile(
            supabase,
            updated_user_data,
            access_token,
            refresh_token,
        )

        return {
            "message": (
                "Profile photo updated successfully."
            ),
            "authenticated": True,
            "user": updated_user_data,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    except HTTPException:
        raise

    except Exception as error:
        lowered = str(error).lower()

        if (
            "bucket not found" in lowered
            or "row-level security" in lowered
            or "violates row-level" in lowered
            or "not authorized" in lowered
        ):
            detail = (
                "Profile photo storage is not ready. "
                "Run the included Supabase Storage SQL "
                "once, then try again."
            )
        else:
            detail = (
                "Unable to update the profile photo."
            )

        logger.exception(
            "Profile photo upload failed for user %s",
            user_id,
        )

        raise HTTPException(
            status_code=400,
            detail=detail,
        ) from error


@app.delete("/auth/profile/avatar")
def remove_profile_avatar(
    request: Request,
):
    (
        supabase,
        current_user,
        access_token,
        refresh_token,
    ) = get_authenticated_supabase(
        request
    )

    user_id = str(
        get_attribute(
            current_user,
            "id",
            "",
        )
    ).strip()

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your account could not be identified. "
                "Please log in again."
            ),
        )

    object_path = (
        f"{user_id}/avatar.jpg"
    )

    try:
        try:
            (
                supabase.storage
                .from_(PROFILE_PHOTO_BUCKET)
                .remove([object_path])
            )
        except Exception as storage_error:
            lowered = str(
                storage_error
            ).lower()

            if (
                "not found" not in lowered
                and "does not exist" not in lowered
            ):
                raise

        existing_metadata = (
            get_attribute(
                current_user,
                "user_metadata",
                {},
            )
            or {}
        )

        updated_response = (
            supabase.auth.update_user(
                {
                    "data": {
                        **existing_metadata,
                        "custom_avatar_url": None,
                        "avatar_removed": True,
                    }
                }
            )
        )

        updated_user = (
            get_attribute(
                updated_response,
                "user",
            )
            or current_user
        )

        updated_user_data = user_to_dict(
            updated_user
        )

        sync_profile(
            supabase,
            updated_user_data,
            access_token,
            refresh_token,
        )

        return {
            "message": (
                "Profile photo removed successfully."
            ),
            "authenticated": True,
            "user": updated_user_data,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    except HTTPException:
        raise

    except Exception as error:
        logger.exception(
            "Profile photo removal failed for user %s",
            user_id,
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to remove the profile photo."
            ),
        ) from error



_account_cleanup_task: asyncio.Task | None = None


async def account_cleanup_worker() -> None:
    while True:
        try:
            await asyncio.to_thread(
                purge_expired_customer_accounts
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Scheduled account cleanup failed."
            )

        await asyncio.sleep(
            ACCOUNT_CLEANUP_INTERVAL_SECONDS
        )


@app.on_event("startup")
async def start_account_cleanup_worker() -> None:
    global _account_cleanup_task

    if (
        _account_cleanup_task is None
        or _account_cleanup_task.done()
    ):
        _account_cleanup_task = (
            asyncio.create_task(
                account_cleanup_worker()
            )
        )


@app.on_event("shutdown")
async def stop_account_cleanup_worker() -> None:
    global _account_cleanup_task

    if _account_cleanup_task is None:
        return

    _account_cleanup_task.cancel()

    try:
        await _account_cleanup_task
    except asyncio.CancelledError:
        pass

    _account_cleanup_task = None


@app.get("/debug/httpsms/config")
def httpsms_config_status():
    """
    Safe configuration check. This does not reveal
    secrets and does not send an SMS.
    """

    sender = None
    sender_valid = False

    if HTTPSMS_FROM:
        try:
            sender = normalize_ph_phone(
                HTTPSMS_FROM
            )
            sender_valid = True
        except HTTPException:
            sender = HTTPSMS_FROM

    return {
        "httpsms_api_key_configured": bool(
            HTTPSMS_API_KEY
        ),
        "httpsms_from_configured": bool(
            HTTPSMS_FROM
        ),
        "httpsms_from_normalized": sender,
        "httpsms_from_valid": sender_valid,
        "sms_hook_secret_configured": bool(
            SUPABASE_SMS_HOOK_SECRET
        ),
        "send_endpoint": HTTPSMS_SEND_URL,
    }


@app.post("/hooks/supabase/send-sms")
async def supabase_send_sms_hook(
    request: Request,
):
    """
    Supabase Send SMS Hook.

    Supabase creates and validates the OTP.
    This endpoint only delivers that OTP through
    the httpSMS Android gateway.
    """

    require_httpsms_configuration()

    raw_body = await request.body()

    try:
        verifier = Webhook(
            normalize_webhook_secret(
                SUPABASE_SMS_HOOK_SECRET
            )
        )

        verifier.verify(
            raw_body.decode("utf-8"),
            dict(request.headers),
        )

    except Exception as error:
        logger.exception(
            "Supabase SMS hook signature verification failed."
        )

        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid Supabase SMS hook signature. "
                "Confirm that backend/.env contains the exact "
                "v1,whsec_ secret generated by Supabase."
            ),
        ) from error

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid SMS hook JSON payload.",
        ) from error

    phone = (
        event.get("user", {}).get("phone")
    )

    otp = (
        event.get("sms", {}).get("otp")
    )


    logger.info(
        "Received Supabase Send SMS hook for %s",
        phone or "unknown phone",
    )

    if not phone or not otp:
        raise HTTPException(
            status_code=400,
            detail=(
                "The SMS hook payload is missing "
                "the phone number or OTP."
            ),
        )

    await send_httpsms_message(
        destination=phone,
        otp=otp,
    )

    return Response(
        content='{"status":"ok"}',
        status_code=200,
        media_type="application/json",
    )




from live_updates import router as live_router, hub as live_hub, database_listener, emit_table, mutation_tables
app.include_router(live_router)
_database_live_task = None

@app.middleware("http")
async def publish_successful_mutations(request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        path_parts = request.url.path.strip("/").split("/")
        booking_id = ""
        if len(path_parts) > 1 and path_parts[0] in {"public-bookings", "bookings"}:
            candidate = path_parts[1]
            if candidate not in {"calendar-availability", "availability", "feedback"}:
                booking_id = candidate
        elif (
            len(path_parts) > 2
            and path_parts[:2] in (
                ["admin", "bookings"],
                ["front-desk", "bookings"],
                ["admin", "manual-bookings"],
            )
        ):
            booking_id = path_parts[2]
        for table in mutation_tables(request.url.path):
            record = (
                {"id": booking_id}
                if table == "bookings" and booking_id
                else {"booking_id": booking_id}
                if booking_id
                else None
            )
            emit_table(table, record)
    return response

@app.on_event("startup")
async def start_database_live_updates():
    global _database_live_task
    live_hub.attach()
    if os.getenv("DATABASE_REALTIME_ENABLED", "true").lower() in {"true", "1", "yes"}:
        _database_live_task = asyncio.create_task(database_listener())

@app.on_event("shutdown")
async def stop_database_live_updates():
    global _database_live_task
    if _database_live_task:
        _database_live_task.cancel()
        try:
            await _database_live_task
        except asyncio.CancelledError:
            pass
        _database_live_task = None


# Assignment emails have an independent persistent outbox and database leases.
_staff_assignment_email_task = None

async def staff_assignment_email_worker():
    from staff_assignment_email import process_assignment_emails
    while True:
        try:
            await asyncio.to_thread(process_assignment_emails)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("thevilla.staff_assignment_email").warning(
                "Staff assignment email processing unavailable; check the 20261025_staff_assignment_emails migration and SMTP configuration."
            )
        await live_hub.wait("emails", 30)

@app.on_event("startup")
async def start_staff_assignment_email_worker():
    global _staff_assignment_email_task
    if os.getenv("STAFF_ASSIGNMENT_EMAIL_ENABLED", "true").lower() in {"true", "1", "yes"}:
        _staff_assignment_email_task = asyncio.create_task(staff_assignment_email_worker())

@app.on_event("shutdown")
async def stop_staff_assignment_email_worker():
    global _staff_assignment_email_task
    if _staff_assignment_email_task:
        _staff_assignment_email_task.cancel()
        try:
            await _staff_assignment_email_task
        except asyncio.CancelledError:
            pass
        _staff_assignment_email_task = None


# Booking records provide durable recovery for missed pre-arrival allocations.
_maintenance_oncall_task = None


async def maintenance_oncall_worker():
    from maintenance_oncall import process_maintenance_oncall
    while True:
        try:
            await asyncio.to_thread(process_maintenance_oncall)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("thevilla.maintenance.oncall").warning("Maintenance automation needs follow-up processing.")
        await live_hub.wait("maintenance", 30)


@app.on_event("startup")
async def start_maintenance_oncall_worker():
    global _maintenance_oncall_task
    if os.getenv("MAINTENANCE_AUTOMATION_ENABLED", "true").lower() in {"true", "1", "yes"}:
        _maintenance_oncall_task = asyncio.create_task(maintenance_oncall_worker())


@app.on_event("shutdown")
async def stop_maintenance_oncall_worker():
    global _maintenance_oncall_task
    if _maintenance_oncall_task:
        _maintenance_oncall_task.cancel()
        try:
            await _maintenance_oncall_task
        except asyncio.CancelledError:
            pass
        _maintenance_oncall_task = None


_booking_assignment_worker_task = None

async def booking_assignment_worker():
    from booking_assignments import process_confirmed_bookings
    while True:
        try:
            await asyncio.to_thread(process_confirmed_bookings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("thevilla.booking_assignments").exception(
                "Automatic booking preparation could not run; retrying in 60 seconds."
            )
        await live_hub.wait("assignments", 60)

@app.on_event("startup")
async def start_booking_assignment_worker():
    global _booking_assignment_worker_task
    if os.getenv("BOOKING_ASSIGNMENT_WORKER_ENABLED", "true").lower() in {"true", "1", "yes"}:
        _booking_assignment_worker_task = asyncio.create_task(booking_assignment_worker())

@app.on_event("shutdown")
async def stop_booking_assignment_worker():
    global _booking_assignment_worker_task
    if _booking_assignment_worker_task:
        _booking_assignment_worker_task.cancel()
        try:
            await _booking_assignment_worker_task
        except asyncio.CancelledError:
            pass
        _booking_assignment_worker_task = None


# Persistent outbox state lives in Supabase; each API process may safely run a
# worker because claims use FOR UPDATE SKIP LOCKED and a database lease.
_feedback_analysis_task = None

async def feedback_analysis_worker():
    from feedback_automation import process_feedback_analysis
    while True:
        try:
            await asyncio.to_thread(process_feedback_analysis)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("thevilla.feedback.automation").warning("Automatic feedback analysis could not run. Check the automation migration and configuration.")
        await live_hub.wait("analysis", 60)

@app.on_event("startup")
async def start_feedback_analysis_worker():
    global _feedback_analysis_task
    if os.getenv("FEEDBACK_ANALYSIS_WORKER_ENABLED", "true").lower() in {"true", "1", "yes"}:
        _feedback_analysis_task = asyncio.create_task(feedback_analysis_worker())

@app.on_event("shutdown")
async def stop_feedback_analysis_worker():
    global _feedback_analysis_task
    if _feedback_analysis_task:
        _feedback_analysis_task.cancel()
        try:
            await _feedback_analysis_task
        except asyncio.CancelledError:
            pass
        _feedback_analysis_task = None


_feedback_worker_task = None

async def feedback_invitation_worker():
    from feedback_service import process_feedback_outbox
    while True:
        try:
            await asyncio.to_thread(process_feedback_outbox)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Feedback outbox processing unavailable; check migration and SMTP configuration.")
        await live_hub.wait("feedback", 60)

@app.on_event("startup")
async def start_feedback_worker():
    global _feedback_worker_task
    if os.getenv("FEEDBACK_WORKER_ENABLED", "true").lower() == "true":
        _feedback_worker_task = asyncio.create_task(feedback_invitation_worker())

@app.on_event("shutdown")
async def stop_feedback_worker():
    global _feedback_worker_task
    if _feedback_worker_task:
        _feedback_worker_task.cancel()
        try:
            await _feedback_worker_task
        except asyncio.CancelledError:
            pass
        _feedback_worker_task = None

from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

@app.exception_handler(RequestValidationError)
async def safe_feedback_validation_error(request, error):
    if (request.url.path.startswith("/public-bookings/") and "/feedback" in request.url.path) or request.url.path.startswith("/maintenance-response/"):
        return JSONResponse(status_code=422, content={"detail":[{"loc":item["loc"],"msg":item["msg"],"type":item["type"]} for item in error.errors()]},headers={"Cache-Control":"no-store"})
    return await request_validation_exception_handler(request,error)

@app.middleware("http")
async def protect_feedback_responses(request, call_next):
    if request.url.path.startswith("/public-bookings/") and "/feedback" in request.url.path and request.method in {"GET","POST"}:
        from booking import _limit_feedback_request
        from fastapi import HTTPException
        try:
            await asyncio.to_thread(_limit_feedback_request,request,"")
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code,content={"detail":error.detail},headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})
    response = await call_next(request)
    if (request.url.path.startswith("/public-bookings/") and "/feedback" in request.url.path) or request.url.path.startswith("/admin/guest-feedback") or request.url.path.startswith("/maintenance-response/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


from frontend_hosting import mount_frontend

mount_frontend(app, os.getenv("FRONTEND_DIST", "").strip())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )   
