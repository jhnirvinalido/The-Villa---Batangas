from __future__ import annotations

import getpass
import os
import secrets
import string
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
).strip()


def require_configuration() -> None:
    missing = []

    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")

    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append(
            "SUPABASE_SERVICE_ROLE_KEY"
        )

    if missing:
        raise RuntimeError(
            "Missing backend configuration: "
            + ", ".join(missing)
        )


def generate_strong_password(
    length: int = 24,
) -> str:
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()-_=+"

    characters = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]

    alphabet = (
        lowercase
        + uppercase
        + digits
        + symbols
    )

    characters.extend(
        secrets.choice(alphabet)
        for _ in range(length - 4)
    )

    secrets.SystemRandom().shuffle(
        characters
    )

    return "".join(characters)


def admin_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": (
            "Bearer "
            + SUPABASE_SERVICE_ROLE_KEY
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def read_json(
    response: requests.Response,
) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError as error:
        raise RuntimeError(
            "Supabase returned invalid JSON."
        ) from error

    if not isinstance(value, dict):
        raise RuntimeError(
            "Supabase returned an invalid response."
        )

    return value


def list_auth_users() -> list[dict[str, Any]]:
    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/auth/v1/admin/users"
            "?page=1&per_page=1000"
        ),
        headers=admin_headers(),
        timeout=(5, 30),
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to list Supabase Auth users: "
            + response.text
        )

    payload = read_json(response)

    users = payload.get("users", [])

    return (
        users
        if isinstance(users, list)
        else []
    )


def find_auth_user(
    email: str,
) -> dict[str, Any] | None:
    normalized_email = (
        email.strip().lower()
    )

    for user in list_auth_users():
        user_email = str(
            user.get("email") or ""
        ).strip().lower()

        if user_email == normalized_email:
            return user

    return None


def create_auth_user(
    *,
    email: str,
    password: str,
    full_name: str,
) -> dict[str, Any]:
    response = requests.post(
        (
            f"{SUPABASE_URL}"
            "/auth/v1/admin/users"
        ),
        headers=admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name,
                "role": "admin",
            },
            "app_metadata": {
                "role": "admin",
            },
        },
        timeout=(5, 30),
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to create the Auth user: "
            + response.text
        )

    return read_json(response)


def repair_auth_user(
    *,
    user_id: str,
    email: str,
    password: str,
    full_name: str,
) -> dict[str, Any]:
    response = requests.put(
        (
            f"{SUPABASE_URL}"
            f"/auth/v1/admin/users/{user_id}"
        ),
        headers=admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name,
                "role": "admin",
            },
            "app_metadata": {
                "role": "admin",
            },
        },
        timeout=(5, 30),
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to repair the Auth user: "
            + response.text
        )

    return read_json(response)


def sync_staff_account(
    *,
    auth_user_id: str,
    email: str,
    full_name: str,
) -> dict[str, Any]:
    client = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )

    email_response = (
        client.table("staff_accounts")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
    )

    email_rows = (
        getattr(
            email_response,
            "data",
            [],
        )
        or []
    )

    auth_response = (
        client.table("staff_accounts")
        .select("*")
        .eq(
            "auth_user_id",
            auth_user_id,
        )
        .limit(1)
        .execute()
    )

    auth_rows = (
        getattr(
            auth_response,
            "data",
            [],
        )
        or []
    )

    values = {
        "auth_user_id": auth_user_id,
        "employee_code": "ADMIN-001",
        "full_name": full_name,
        "email": email,
        "username": (
            email.split("@", 1)[0]
            .replace(" ", "")
            .lower()
        ),
        "role": "admin",
        "department": "Administration",
        "position": "System Administrator",
        "shift": "8:00 AM – 5:00 PM",
        "is_active": True,
        "account_status": "Active",
        "must_change_password": False,
    }

    existing = (
        email_rows[0]
        if email_rows
        else (
            auth_rows[0]
            if auth_rows
            else None
        )
    )

    if existing:
        result = (
            client.table("staff_accounts")
            .update(values)
            .eq("id", existing["id"])
            .execute()
        )
    else:
        result = (
            client.table("staff_accounts")
            .insert(values)
            .execute()
        )

    rows = (
        getattr(
            result,
            "data",
            [],
        )
        or []
    )

    if not rows:
        raise RuntimeError(
            "The staff_accounts record "
            "was not saved."
        )

    return rows[0]


def main() -> None:
    require_configuration()

    print()
    print(
        "THE VILLA ADMIN ACCOUNT REPAIR"
    )
    print(
        "=" * 44
    )

    email = input(
        "Admin email: "
    ).strip().lower()

    if (
        not email
        or "@" not in email
    ):
        raise RuntimeError(
            "Enter a valid email address."
        )

    full_name = input(
        "Admin full name [Admin 1]: "
    ).strip() or "Admin 1"

    generated_password = (
        generate_strong_password()
    )

    print()
    print(
        "A strong temporary password "
        "will be generated."
    )

    existing_user = find_auth_user(
        email
    )

    if existing_user:
        auth_user = repair_auth_user(
            user_id=str(
                existing_user["id"]
            ),
            email=email,
            password=generated_password,
            full_name=full_name,
        )

        action = "repaired"
    else:
        auth_user = create_auth_user(
            email=email,
            password=generated_password,
            full_name=full_name,
        )

        action = "created"

    auth_user_id = str(
        auth_user.get("id") or ""
    ).strip()

    if not auth_user_id:
        raise RuntimeError(
            "Supabase did not return "
            "the Auth user ID."
        )

    account = sync_staff_account(
        auth_user_id=auth_user_id,
        email=email,
        full_name=full_name,
    )

    print()
    print(
        "=" * 44
    )
    print(
        f"ADMIN ACCOUNT {action.upper()}"
    )
    print(
        "=" * 44
    )
    print(
        f"Email: {email}"
    )
    print(
        f"Name: {full_name}"
    )
    print(
        "Role: admin"
    )
    print(
        "Status: Active"
    )
    print(
        f"Staff account ID: "
        f"{account.get('id', '')}"
    )
    print()
    print(
        "TEMPORARY STRONG PASSWORD:"
    )
    print(
        generated_password
    )
    print()
    print(
        "Copy the password now, then sign "
        "in at /admin-login."
    )
    print(
        "=" * 44
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print()
        print(
            f"ERROR: {error}"
        )
        raise SystemExit(1)
