from __future__ import annotations

from task_workflow import staff_checklist_update, task_start_is_available

import secrets
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import EmailStr, Field

from staff_admin_auth import validate_portal_access_token

from admin import (
    ApiModel,
    MESSAGE_SELECT,
    NOTIFICATION_SELECT,
    STAFF_SELECT,
    STAFF_TIME_RECORD_SELECT,
    TASK_SELECT,
    BookingLifecycleRequest,
    ManualBookingRequest,
    check_in_booking as admin_check_in_booking,
    checkout_booking as admin_checkout_booking,
    bearer_token,
    fetch_staff_by_auth,
    fetch_task,
    message_api,
    model_values,
    notification_api,
    notify_admins,
    now_iso,
    public_client,
    record_booking_event,
    rows,
    service_client,
    staff_api,
    staff_time_record_api,
    task_api,
)

logger = logging.getLogger("thevilla.staff")

router = APIRouter(
    prefix="/staff",
    tags=["Staff Database"],
)

STAFF_SETTINGS_SELECT = (
    "id,staff_account_id,push_notifications,dark_mode,sound_on_message,"
    "show_completed_on_dashboard,created_at,updated_at"
)


class StaffTaskUpdateRequest(ApiModel):
    expected_updated_at: str | None = Field(default=None, alias="expectedUpdatedAt")
    status: Literal["Pending", "In Progress", "Pending Review", "Completed"] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    checklist: list[dict[str, Any]] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    waiting_for_parts: bool | None = Field(default=None, alias="waitingForParts")
    parts_notes: str | None = Field(default=None, alias="partsNotes", max_length=2000)


class StaffMessageRequest(ApiModel):
    concern: str = Field(default="General update", min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=5000)
    task_id: UUID | None = Field(default=None, alias="assignmentId")
    booking_code: str | None = Field(default=None, max_length=120, alias="bookingCode")


class StaffSettingsRequest(ApiModel):
    push_notifications: bool | None = Field(default=None, alias="pushNotifications")
    dark_mode: bool | None = Field(default=None, alias="darkMode")
    sound_on_message: bool | None = Field(default=None, alias="soundOnMessage")
    show_completed_on_dashboard: bool | None = Field(
        default=None,
        alias="showCompletedOnDashboard",
    )


class GuestServicesWalkInRequest(ManualBookingRequest):
    payment_choice: Literal["full"] = "full"
    payment_method: Literal["cash", "qrph"] = "cash"
    cash_tendered: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )


class StaffAccessRequest(ApiModel):
    area: Literal["walk_in", "payments"]


class StaffPaymentApprovalRequest(ApiModel):
    payment_method: Literal["cash", "qrph"]
    payment_timing: Literal["check_in", "check_out"]


def require_staff(
    request: Request,
) -> dict[str, Any]:
    token = bearer_token(
        request
    )

    account = (
        validate_portal_access_token(
            token,
        )
    )
    if str(account.get("role") or "").lower() not in {"staff", "maintenance"}:
        raise HTTPException(status_code=403, detail="Staff or Maintenance access is required.")

    return {
        "token": token,
        "account": account,
        "session": {
            "staff_account_id":
                account.get("id"),

            "last_seen_at":
                now_iso(),
        },
    }


def require_walk_in_access(
    context: dict[str, Any] = Depends(require_staff),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=403,
        detail="Walk-in booking is only available to the Front Desk / Operations role.",
    )


def require_front_desk_payment_access(
    context: dict[str, Any] = Depends(require_staff),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=403,
        detail="Payment settlement is only available to the Front Desk / Operations role.",
    )


@router.post("/access-requests")
def request_staff_access(
    data: StaffAccessRequest,
    context: dict[str, Any] = Depends(require_staff),
):
    raise HTTPException(
        status_code=403,
        detail="Ask an administrator to assign the Front Desk / Operations role in Staff Directory.",
    )


def guest_services_availability(
    check_in_date: date,
    guest_count: int = 1,
    context: dict[str, Any] = Depends(require_walk_in_access),
):
    from booking import public_booking_availability

    return public_booking_availability(
        check_in_date=check_in_date,
        guest_count=guest_count,
    )


def create_guest_services_walk_in(
    data: GuestServicesWalkInRequest,
    request: Request,
    context: dict[str, Any] = Depends(require_walk_in_access),
):
    walk_in_marker = f"[Walk-in booking staff:{context['account']['id']}]"
    if data.payment_method == "qrph":
        from admin import create_manual_booking

        data.notes = (
            f"{walk_in_marker}{' ' + data.notes.strip() if data.notes else ''}"
        )
        return create_manual_booking(data, request, context)

    if data.cash_tendered is None:
        raise HTTPException(
            status_code=422,
            detail="Enter the cash received from the guest.",
        )

    from admin import complete_front_desk_settlement, fetch_booking, money, rows, service_client
    from booking import (
        PublicBookingCreateRequest,
        _prepare_public_booking,
        _send_booking_confirmation_email,
    )

    creation = _prepare_public_booking(
        PublicBookingCreateRequest(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            villa_id=data.villa_ids[0],
            villa_ids=data.villa_ids,
            check_in_date=data.check_in_date,
            check_in_time="3:00 PM",
            guest_count=data.guest_count,
            notes=f"{walk_in_marker}{' ' + data.notes.strip() if data.notes else ''}",
            payment_choice="full",
            payment_method="qrph",
        ),
        draft_only=True,
    )
    booking = creation["booking"]
    total_amount = money(booking.get("total_amount"))
    cash_tendered = money(data.cash_tendered)
    if cash_tendered < total_amount:
        raise HTTPException(
            status_code=409,
            detail=f"Cash is insufficient by PHP {float(total_amount - cash_tendered):,.2f}.",
        )

    booking["payment_method"] = "Cash"
    booking["payment_method_code"] = "cash"
    try:
        inserted = rows(
            service_client()
            .table("bookings")
            .insert(booking)
            .select("*")
            .execute()
        )
    except Exception as error:
        message = str(error).lower()
        if any(marker in message for marker in ("duplicate key", "already booked", "bookings_active_villa_date_unique")):
            raise HTTPException(
                status_code=409,
                detail="The villa availability changed. Refresh availability and try again.",
            ) from error
        logger.exception("Could not save walk-in booking.")
        raise HTTPException(
            status_code=400,
            detail="The walk-in booking could not be stored. Check the booking database configuration.",
        ) from error
    if not inserted:
        raise HTTPException(status_code=500, detail="The walk-in booking could not be returned.")

    booking = inserted[0]
    settled = False
    try:
        settlement = complete_front_desk_settlement(
            booking=booking,
            cashier=context["account"],
            method="Cash",
            payer_name=booking["customer_name"],
            other_charges=[],
            reference=f"WALKIN-{booking['booking_code']}",
            cash_tendered=cash_tendered,
            change_given=cash_tendered - total_amount,
            notes="Full walk-in payment",
        )
        settled = True
        confirmed_rows = rows(
            service_client()
            .table("bookings")
            .update({
                "booking_status": "Confirmed",
                "stay_status": "Not Checked In",
                "hold_expires_at": None,
                "updated_at": now_iso(),
            })
            .eq("id", str(booking["id"]))
            .select("*")
            .execute()
        )
        if not confirmed_rows:
            raise HTTPException(
                status_code=500,
                detail="Payment was recorded, but the booking confirmation needs administrator review.",
            )
        booking = confirmed_rows[0]
    except Exception:
        if not settled:
            try:
                latest = fetch_booking(str(booking["id"]))
                settled = (
                    str(latest.get("payment_status") or "").lower() == "paid"
                    and Decimal(str(latest.get("amount_paid") or 0)) >= total_amount
                )
                if not settled:
                    (
                        service_client()
                        .table("bookings")
                        .update({
                            "booking_status": "Cancelled",
                            "hold_expires_at": None,
                            "updated_at": now_iso(),
                        })
                        .eq("id", str(booking["id"]))
                        .execute()
                    )
            except Exception:
                logger.exception("Could not release the failed walk-in booking hold %s.", booking["id"])
        raise

    try:
        from booking_assignments import schedule_prearrival_assignment

        schedule_prearrival_assignment(booking, service_client())
    except Exception:
        logger.exception(
            "Walk-in booking %s was paid and confirmed, but its housekeeping assignment needs retry.",
            booking.get("booking_code"),
        )

    email_sent = _send_booking_confirmation_email(booking)
    payment = settlement.get("payment") or {}
    return {
        "message": "Walk-in booking confirmed and cash payment recorded.",
        "data": {
            "booking": booking,
            "payment": payment,
            "change_given": float(cash_tendered - total_amount),
            "email_sent": email_sent,
        },
    }


def sync_guest_services_walk_in_payment(
    booking_id: UUID,
    context: dict[str, Any] = Depends(require_walk_in_access),
):
    from admin import fetch_booking, rows, service_client
    from booking import sync_manual_checkout_payment

    staff_id = str(context["account"]["id"])
    staged = rows(
        service_client()
        .table("manual_booking_checkouts")
        .select("id,created_by_staff_id")
        .eq("id", str(booking_id))
        .limit(1)
        .execute()
    )
    if staged:
        if str(staged[0].get("created_by_staff_id") or "") != staff_id:
            raise HTTPException(status_code=404, detail="Walk-in checkout was not found.")
    else:
        booking = fetch_booking(str(booking_id))
        marker = f"[Walk-in booking staff:{staff_id}]"
        if not str(booking.get("notes") or "").startswith(marker):
            raise HTTPException(status_code=404, detail="Walk-in checkout was not found.")

    result = sync_manual_checkout_payment(str(booking_id))
    booking = result["booking"]
    return {
        "state": result["state"],
        "data": {
            "id": booking["id"],
            "booking_code": booking.get("booking_code"),
            "booking_status": booking.get("booking_status"),
            "payment_status": booking.get("payment_status"),
            "amount_paid": booking.get("amount_paid"),
            "balance_amount": booking.get("balance_amount"),
            "hold_expires_at": booking.get("hold_expires_at"),
        },
    }


def guest_services_bookings(
    context: dict[str, Any] = Depends(require_front_desk_payment_access),
):
    from admin import apply_payment_timing_preferences, load_bookings_with_payments, load_payment_timing_events

    client = service_client()
    bookings = apply_payment_timing_preferences(
        load_bookings_with_payments(client),
        load_payment_timing_events(client),
    )
    active = [
        booking
        for booking in bookings
        if str(booking.get("booking_status") or "").strip().lower()
        in {"confirmed", "checked in"}
    ]
    return {"data": active}


def request_guest_services_payment_approval(
    booking_id: UUID,
    data: StaffPaymentApprovalRequest,
    context: dict[str, Any] = Depends(require_front_desk_payment_access),
):
    from admin import (
        PAYMENT_TIMING_LABELS,
        booking_initial_payment_verified,
        fetch_booking,
        money,
        notify_admins,
        validate_payment_timing_for_booking,
    )

    booking = fetch_booking(str(booking_id))
    if str(booking.get("booking_status") or "").strip().lower() not in {
        "confirmed",
        "checked in",
    }:
        raise HTTPException(status_code=409, detail="Only confirmed active stays can request payment approval.")
    if str(booking.get("payment_choice") or "").strip().lower() != "half":
        raise HTTPException(status_code=409, detail="This booking has no scheduled front-desk balance.")
    if not booking_initial_payment_verified(booking):
        raise HTTPException(status_code=409, detail="The original customer downpayment has not been verified.")

    timing = validate_payment_timing_for_booking(booking, data.payment_timing)
    amount = money(booking.get("balance_amount"))
    if amount <= 0:
        raise HTTPException(status_code=409, detail="This booking has no remaining balance.")

    client = service_client()
    pending = rows(
        client.table("front_desk_payment_approval_requests")
        .select("*")
        .eq("booking_id", str(booking_id))
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if pending:
        request_row = pending[0]
        if (
            str(request_row.get("requested_by_staff_id")) == str(context["account"]["id"])
            and request_row.get("payment_method") == data.payment_method
            and request_row.get("payment_timing") == timing
            and money(request_row.get("amount")) == amount
        ):
            return {"data": request_row}
        raise HTTPException(
            status_code=409,
            detail="An administrator already has a pending payment request for this booking.",
        )

    request_rows = rows(
        client.table("front_desk_payment_approval_requests")
        .insert({
            "booking_id": str(booking_id),
            "requested_by_staff_id": str(context["account"]["id"]),
            "payment_method": data.payment_method,
            "payment_timing": timing,
            "amount": float(amount),
            "status": "pending",
        })
        .select("*")
        .execute()
    )
    if not request_rows:
        raise HTTPException(status_code=500, detail="The payment approval request could not be saved.")

    request_row = request_rows[0]
    booking_code = str(booking.get("booking_code") or booking_id)
    timing_label = PAYMENT_TIMING_LABELS[timing]
    try:
        notify_admins(
            "Payment approval needed",
            f"{context['account'].get('full_name') or 'On-site staff'} requested "
            f"{data.payment_method.upper()} payment of PHP {amount:,.2f} for "
            f"{booking_code} ({timing_label}).",
            notification_type="front_desk_payment_approval",
            icon="shield",
        )
    except Exception:
        logger.exception("Could not notify administrators about payment approval request %s.", request_row["id"])
    return {"message": "Payment approval request sent to the administrator.", "data": request_row}


def get_guest_services_payment_approval(
    request_id: UUID,
    context: dict[str, Any] = Depends(require_front_desk_payment_access),
):
    request_rows = rows(
        service_client()
        .table("front_desk_payment_approval_requests")
        .select("id,booking_id,requested_by_staff_id,payment_method,payment_timing,amount,status,created_at,updated_at")
        .eq("id", str(request_id))
        .eq("requested_by_staff_id", str(context["account"]["id"]))
        .limit(1)
        .execute()
    )
    if not request_rows:
        raise HTTPException(status_code=404, detail="Your payment approval request was not found.")
    return {"data": request_rows[0]}


def guest_services_check_in_booking(
    booking_id: UUID,
    data: BookingLifecycleRequest,
    context: dict[str, Any] = Depends(require_front_desk_payment_access),
):
    return admin_check_in_booking(booking_id, data, context)


def guest_services_checkout_booking(
    booking_id: UUID,
    data: BookingLifecycleRequest,
    context: dict[str, Any] = Depends(require_front_desk_payment_access),
):
    return admin_checkout_booking(booking_id, data, context)


def staff_settings_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pushNotifications": bool(row.get("push_notifications", True)),
        "darkMode": bool(row.get("dark_mode", False)),
        "soundOnMessage": bool(row.get("sound_on_message", False)),
        "showCompletedOnDashboard": bool(row.get("show_completed_on_dashboard", False)),
    }


def load_staff_settings(staff_id: str) -> dict[str, Any]:
    client = service_client()
    result = rows(
        client.table("staff_settings")
        .select(STAFF_SETTINGS_SELECT)
        .eq("staff_account_id", staff_id)
        .limit(1)
        .execute()
    )
    if result:
        return result[0]

    created = rows(
        client.table("staff_settings")
        .insert({"staff_account_id": staff_id})
        .select(STAFF_SETTINGS_SELECT)
        .execute()
    )
    return created[0] if created else {}


def load_current_staff_account(
    account: dict[str, Any],
) -> dict[str, Any]:
    """
    Reload the exact staff_accounts row on every bootstrap request.

    This guarantees that the Staff Dashboard shows the name and profile
    maintained in the Admin Dashboard instead of stale Auth metadata or
    browser storage.
    """

    account_id = str(
        account.get("id")
        or ""
    ).strip()

    auth_user_id = str(
        account.get("auth_user_id")
        or ""
    ).strip()

    query = (
        service_client()
        .table("staff_accounts")
        .select(STAFF_SELECT)
    )

    if account_id:
        response = (
            query
            .eq("id", account_id)
            .limit(1)
            .execute()
        )
    elif auth_user_id:
        response = (
            query
            .eq(
                "auth_user_id",
                auth_user_id,
            )
            .limit(1)
            .execute()
        )
    else:
        raise HTTPException(
            status_code=401,
            detail=(
                "The staff login session "
                "has no linked profile."
            ),
        )

    result = rows(response)

    if not result:
        raise HTTPException(
            status_code=403,
            detail=(
                "The logged-in account "
                "is not in the staff "
                "directory."
            ),
        )

    current = result[0]

    if (
        str(
            current.get("role")
            or ""
        ).strip().lower()
        != "staff"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Staff access is required."
            ),
        )

    if (
        not bool(
            current.get("is_active")
        )
        or str(
            current.get(
                "account_status"
            )
            or ""
        ).strip().lower()
        == "disabled"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "This staff account "
                "is disabled."
            ),
        )

    return current


def load_all_staff_tasks(
    staff_id: str,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    """
    Load every admin_tasks row assigned to one staff account.

    Pagination prevents Supabase/PostgREST row limits from hiding older tasks.
    """

    all_tasks: list[
        dict[str, Any]
    ] = []

    offset = 0

    while True:
        page = rows(
            service_client()
            .table("admin_tasks")
            .select(TASK_SELECT)
            .eq(
                "assigned_staff_id",
                staff_id,
            )
            .order(
                "created_at",
                desc=True,
            )
            .range(
                offset,
                offset + page_size - 1,
            )
            .execute()
        )

        all_tasks.extend(page)

        if len(page) < page_size:
            break

        offset += page_size

    return all_tasks


def load_optional_rows(
    table_name: str,
    select_columns: str,
    *,
    filters: list[
        tuple[str, Any]
    ] | None = None,
    order_column: str | None = None,
    descending: bool = False,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    Optional communication/settings tables must not prevent the profile and
    assigned tasks from loading.
    """

    try:
        query = (
            service_client()
            .table(table_name)
            .select(select_columns)
        )

        for column, value in (
            filters or []
        ):
            query = query.eq(
                column,
                value,
            )

        if order_column:
            query = query.order(
                order_column,
                desc=descending,
            )

        return rows(
            query
            .limit(limit)
            .execute()
        )

    except Exception:
        return []


@router.get("/session")
@router.post("/session")
def staff_session(
    context: dict[str, Any] = Depends(
        require_staff
    ),
):
    current_account = (
        load_current_staff_account(
            context["account"]
        )
    )

    return {
        "authenticated":
            True,

        "user":
            staff_api(
                current_account
            ),

        "session": {
            **context["session"],

            "staff_account_id":
                current_account[
                    "id"
                ],
        },
    }


@router.delete("/session")
def staff_logout(context: dict[str, Any] = Depends(require_staff)):
    return {"message": "Staff session signed out successfully."}


@router.get("/bootstrap")
def staff_bootstrap(
    context: dict[str, Any] = Depends(
        require_staff
    ),
):
    current_account = (
        load_current_staff_account(
            context["account"]
        )
    )

    staff_id = str(
        current_account["id"]
    )

    from read_batches import parallel_reads
    loaded = parallel_reads({
        "directory": lambda: load_optional_rows("staff_accounts", STAFF_SELECT,
            filters=[("role", current_account.get("role", "staff")), ("is_active", True), ("account_status", "Active")], order_column="full_name", limit=5000),
        "admins": lambda: load_optional_rows("staff_accounts", STAFF_SELECT,
            filters=[("role", "admin"), ("is_active", True), ("account_status", "Active")], order_column="full_name", limit=1),
        "tasks": lambda: load_all_staff_tasks(staff_id),
        "messages": lambda: load_optional_rows("staff_messages", MESSAGE_SELECT,
            filters=[("staff_account_id", staff_id)], order_column="created_at", limit=5000),
        "notifications": lambda: load_optional_rows("admin_notifications", NOTIFICATION_SELECT,
            filters=[("recipient_staff_account_id", staff_id)], order_column="created_at", descending=True, limit=5000),
    })
    directory_rows, admin_rows = loaded["directory"], loaded["admins"]
    task_rows, message_rows, notification_rows = loaded["tasks"], loaded["messages"], loaded["notifications"]

    task_map = {
        str(item["id"]):
            item
        for item in task_rows
        if item.get("id")
    }

    related_account_ids = {
        str(value)
        for item in message_rows
        for value in (
            item.get(
                "sender_account_id"
            ),
        )
        if value
    }

    related_account_ids.update(
        str(
            item.get(
                "created_by_staff_id"
            )
        )
        for item in task_rows
        if item.get(
            "created_by_staff_id"
        )
    )

    sender_map = {
        staff_id:
            current_account
    }

    if related_account_ids:
        sender_rows = (
            load_optional_rows(
                "staff_accounts",
                STAFF_SELECT,
                limit=5000,
            )
        )

        sender_map.update({
            str(item["id"]):
                item
            for item in sender_rows
            if (
                item.get("id")
                and str(
                    item["id"]
                )
                in related_account_ids
            )
        })

    administrator = (
        admin_rows[0]
        if admin_rows
        else None
    )

    try:
        settings = (
            staff_settings_api(
                load_staff_settings(
                    staff_id
                )
            )
        )
    except Exception:
        settings = (
            staff_settings_api({})
        )

    profile = staff_api(
        current_account
    )

    tasks = [
        {
            **task_api(
                item,
                current_account,
                sender_map.get(str(item.get("created_by_staff_id"))),
            ),

            "assignedStaffId":
                staff_id,

            "assigned_staff_id":
                staff_id,

            "assignedTo":
                current_account.get(
                    "full_name"
                ),

            "assignedBy": "System" if item.get("source") == "automatic-booking-preparation" else
                sender_map.get(
                    str(
                        item.get(
                            "created_by_staff_id"
                        )
                    ),
                    {},
                ).get(
                    "full_name",
                    "Villa Administrator",
                ),
        }
        for item in task_rows
    ]

    return {
        "data": {
            "profile":
                profile,

            "session": {
                **context[
                    "session"
                ],

                "staff_account_id":
                    staff_id,

                "profile_name":
                    current_account.get(
                        "full_name"
                    ),
            },

            "staff": [
                staff_api(item)
                for item
                in directory_rows
            ],

            "administrator":
                (
                    staff_api(
                        administrator
                    )
                    if administrator
                    else None
                ),

            "tasks":
                tasks,

            "taskCount":
                len(tasks),

            "messages": [
                message_api(
                    item,
                    current_account,
                    sender_map.get(
                        str(
                            item.get(
                                "sender_account_id"
                            )
                        )
                    ),
                    task_map.get(
                        str(
                            item.get(
                                "task_id"
                            )
                        )
                    ),
                )
                for item
                in message_rows
            ],

            "notifications": [
                notification_api(item)
                for item
                in notification_rows
            ],

            "settings":
                settings,
        }
    }


@router.get("/tasks")
def staff_list_tasks(
    context: dict[str, Any] = Depends(
        require_staff
    ),
):
    current_account = (
        load_current_staff_account(
            context["account"]
        )
    )

    staff_id = str(
        current_account["id"]
    )

    task_rows = (
        load_all_staff_tasks(
            staff_id
        )
    )

    sender_map = {str(row["id"]): row for row in load_optional_rows("staff_accounts", STAFF_SELECT, limit=5000)}

    return {
        "data": [
            {
                **task_api(
                    item,
                    current_account,
                    sender_map.get(str(item.get("created_by_staff_id"))),
                ),

                "assignedStaffId":
                    staff_id,

                "assigned_staff_id":
                    staff_id,

                "assignedTo":
                    current_account.get(
                        "full_name"
                    ),
            }
            for item
            in task_rows
        ],

        "count":
            len(task_rows),
    }


@router.patch("/tasks/{task_id}")
def staff_update_task(
    task_id: UUID,
    data: StaffTaskUpdateRequest,
    context: dict[str, Any] = Depends(require_staff),
):
    current = fetch_task(str(task_id))
    staff_id = str(context["account"]["id"])

    if str(current.get("assigned_staff_id")) != staff_id:
        raise HTTPException(
            status_code=403,
            detail="This task is assigned to another staff account.",
        )
    if current.get("status") in {"Completed", "Cancelled"}:
        raise HTTPException(
            status_code=409,
            detail="A completed or cancelled task can no longer be changed.",
        )
    if current.get("status") == "Pending Review" and current.get("source") == "manual-maintenance-request":
        raise HTTPException(
            status_code=409,
            detail="This repair is waiting for administrator verification.",
        )

    if data.expected_updated_at and data.expected_updated_at != str(current.get("updated_at") or ""):
        raise HTTPException(status_code=409, detail="This assignment was updated elsewhere. Refresh your tasks before saving again.")

    updates: dict[str, Any] = {}
    if data.checklist is not None:
        try:
            checklist, progress = staff_checklist_update(current.get("checklist"), data.checklist, str(task_id))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        updates["checklist"] = checklist
        updates["progress"] = progress
    elif data.progress is not None and data.progress != current.get("progress", 0):
        raise HTTPException(status_code=422, detail="Progress is calculated from completed checklist steps.")
    if data.notes is not None:
        updates["notes"] = data.notes

    maintenance_snapshot = None
    if getattr(data, "waiting_for_parts", None) is not None or getattr(data, "parts_notes", None) is not None:
        if current.get("source") != "manual-maintenance-request" or current.get("status") != "In Progress":
            raise HTTPException(status_code=409, detail="Parts updates are available while maintenance is in progress.")
        from maintenance import details
        maintenance_snapshot = details(current)
        if data.waiting_for_parts is not None:
            maintenance_snapshot["waitingForParts"] = data.waiting_for_parts
        if data.parts_notes is not None:
            maintenance_snapshot["partsNotes"] = data.parts_notes.strip()
        if maintenance_snapshot.get("waitingForParts") and not maintenance_snapshot.get("partsNotes"):
            raise HTTPException(status_code=422, detail="Describe the parts or supplies being awaited.")

    next_status = data.status or current.get("status")
    is_maintenance_task = current.get("source") == "manual-maintenance-request"
    allowed = (
        {
            "Pending": {"Pending", "In Progress"},
            "In Progress": {"In Progress", "Pending Review"},
        }
        if is_maintenance_task
        else {
            "Pending": {"Pending", "In Progress"},
            "In Progress": {"In Progress", "Completed"},
            "Pending Review": {"Pending Review", "Completed"},
        }
    )
    if next_status not in allowed.get(
        str(current.get("status")),
        {str(current.get("status"))},
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Task cannot move from {current.get('status')} to {next_status}.",
        )

    if next_status == "In Progress" and current.get("status") == "Pending":
        from admin import maintenance_on_call
        on_call = maintenance_on_call(current)
        if current.get("source") == "manual-maintenance-request":
            from maintenance import details
            if details(current).get("villaId") and not details(current).get("blocksBooking"):
                raise HTTPException(status_code=409, detail="Wait for the administrator to confirm the technician schedule before starting maintenance.")
        if on_call and on_call["state"] != "Accepted":
            raise HTTPException(status_code=409, detail="Confirm your availability using the response link, or contact the administrator, before starting this repair.")
        if not on_call and not task_start_is_available(current.get("due_date"), current.get("due_time")):
            if not current.get("due_date") or not current.get("due_time"):
                detail = "A scheduled date and time are required before this task can be started."
            else:
                detail = "Tasks can only be started on the assigned date, before the deadline."
            raise HTTPException(status_code=409, detail=detail)
        updates["started_at"] = now_iso()

    if next_status == "Pending Review":
        if is_maintenance_task:
            from maintenance import details
            if (maintenance_snapshot or details(current)).get("waitingForParts") or len(str(updates.get("notes", current.get("notes")) or "").strip()) < 5:
                raise HTTPException(status_code=409, detail="Clear waiting for parts and record the repair performed before requesting verification.")
        checklist = updates.get("checklist", current.get("checklist") or [])
        if not checklist or not all(bool(item.get("done")) for item in checklist):
            raise HTTPException(
                status_code=409,
                detail="Complete every checklist item before requesting review.",
            )
        updates["progress"] = 100
        updates["submitted_at"] = now_iso()

    if next_status == "Completed" and current.get("status") != "Completed":
        if is_maintenance_task:
            raise HTTPException(status_code=409, detail="Maintenance work must be submitted for administrator verification.")
        checklist = updates.get("checklist", current.get("checklist") or [])
        if not checklist or not all(bool(item.get("done")) for item in checklist):
            raise HTTPException(
                status_code=409,
                detail="Complete every checklist item before marking this assignment complete.",
            )
        updates["progress"] = 100
        updates["submitted_at"] = None

    status_changed = next_status != current.get("status")
    updates["status"] = next_status
    if status_changed or maintenance_snapshot is not None:
        history = current.get("status_history") or []
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "id": f"AUDIT-{secrets.token_hex(6)}",
                "status": next_status,
                "actor": context["account"]["full_name"],
                "actorStaffId": staff_id,
                "note": f"Staff changed the assignment to {next_status}.",
                "timestamp": now_iso(),
                **({"maintenance": maintenance_snapshot} if maintenance_snapshot is not None else {}),
            }
        )
        updates["status_history"] = history

    updates["updated_by_staff_id"] = staff_id
    updates["updated_at"] = now_iso()

    query = (service_client().table("admin_tasks").update(updates)
             .eq("id", str(task_id)).eq("assigned_staff_id", staff_id)
             .eq("status", current.get("status")))
    if current.get("updated_at"):
        query = query.eq("updated_at", current["updated_at"])
    result = rows(query.select(TASK_SELECT).execute())
    if not result:
        raise HTTPException(status_code=409, detail="This assignment changed while saving. Refresh your tasks and try again.")

    if status_changed and current.get("booking_id"):
        record_booking_event(
            str(current["booking_id"]),
            "staff_assignment_status_changed",
            (
                f"{context['account']['full_name']} changed assignment "
                f"{current.get('task_code') or task_id} from "
                f"{current.get('status')} to {next_status}."
            ),
            from_status=str(current.get("booking_status") or ""),
            to_status=str(current.get("booking_status") or ""),
            actor_type="staff",
            actor_staff_id=staff_id,
            metadata={
                "task_id": str(task_id),
                "task_code": current.get("task_code"),
                "assignment_from_status": current.get("status"),
                "assignment_to_status": next_status,
            },
        )

    if status_changed:
        title = {
            "Pending Review": "Repair Submitted for Verification",
            "Completed": "Assignment Completed",
            "In Progress": "Assignment Started",
        }.get(next_status, "Assignment Updated")
        notify_admins(
            title,
            (
                f"{context['account']['full_name']} completed “{current['title']}”."
                if next_status == "Completed"
                else f"{context['account']['full_name']} changed “{current['title']}” to {next_status}."
            ),
            notification_type="staff-task-update",
            icon="task",
            task_id=str(task_id),
        )

    return {
        "message": "Task updated successfully.",
        "data": task_api(result[0], context["account"]),
    }


@router.post("/messages", status_code=201)
def staff_send_message(
    data: StaffMessageRequest,
    context: dict[str, Any] = Depends(require_staff),
):
    staff_id = str(context["account"]["id"])
    task = None
    if data.task_id:
        task = fetch_task(str(data.task_id))
        if str(task.get("assigned_staff_id")) != staff_id:
            raise HTTPException(
                status_code=403,
                detail="The selected task belongs to another staff account.",
            )

    result = rows(
        service_client()
        .table("staff_messages")
        .insert(
            {
                "staff_account_id": staff_id,
                "sender_account_id": staff_id,
                "sender_type": "staff",
                "concern": data.concern.strip(),
                "body": data.body.strip(),
                "task_id": str(data.task_id) if data.task_id else None,
                "booking_code": data.booking_code
                or (task.get("booking_code") if task else None),
                "read_by_admin": False,
                "read_by_staff": True,
            }
        )
        .select(MESSAGE_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=500, detail="The message was not saved.")

    message = result[0]
    notify_admins(
        data.concern.strip(),
        f"{context['account']['full_name']}: {data.body.strip()}",
        notification_type="staff-message",
        icon="message",
        task_id=str(data.task_id) if data.task_id else None,
        message_id=str(message["id"]),
    )

    return {
        "message": "Message sent to the administrator.",
        "data": message_api(
            message,
            context["account"],
            context["account"],
            task,
        ),
    }


@router.patch("/messages/read-all")
def staff_read_all_messages(context: dict[str, Any] = Depends(require_staff)):
    (
        service_client()
        .table("staff_messages")
        .update({"read_by_staff": True, "updated_at": now_iso()})
        .eq("staff_account_id", context["account"]["id"])
        .eq("sender_type", "admin")
        .eq("read_by_staff", False)
        .execute()
    )
    return {"message": "Administrator messages marked as read."}


@router.get("/notifications")
def staff_list_notifications(context: dict[str, Any] = Depends(require_staff)):
    records = rows(
        service_client().table("admin_notifications").select(NOTIFICATION_SELECT)
        .eq("recipient_staff_account_id", context["account"]["id"])
        .order("created_at", desc=True).limit(5000).execute()
    )
    return {"data": [notification_api(item) for item in records]}


@router.get("/time-records")
def staff_list_time_records(context: dict[str, Any] = Depends(require_staff)):
    records = rows(
        service_client()
        .table("staff_time_records")
        .select(STAFF_TIME_RECORD_SELECT)
        .eq("staff_account_id", context["account"]["id"])
        .order("clock_in_at", desc=True)
        .limit(250)
        .execute()
    )
    return {"data": [staff_time_record_api(record) for record in records]}


@router.post("/time-records/clock-in", status_code=201)
def staff_clock_in(context: dict[str, Any] = Depends(require_staff)):
    client = service_client()
    account_id = str(context["account"]["id"])
    open_record = rows(
        client.table("staff_time_records")
        .select("id")
        .eq("staff_account_id", account_id)
        .is_("clock_out_at", "null")
        .limit(1)
        .execute()
    )
    if open_record:
        raise HTTPException(status_code=409, detail="You are already clocked in.")

    record = rows(
        client.table("staff_time_records")
        .insert({
            "staff_account_id": account_id,
            "clock_in_at": now_iso(),
            "review_status": "open",
        })
        .select(STAFF_TIME_RECORD_SELECT)
        .execute()
    )
    if not record:
        raise HTTPException(status_code=500, detail="Your clock-in could not be saved.")
    return {"data": staff_time_record_api(record[0])}


@router.post("/time-records/clock-out")
def staff_clock_out(context: dict[str, Any] = Depends(require_staff)):
    client = service_client()
    account_id = str(context["account"]["id"])
    open_record = rows(
        client.table("staff_time_records")
        .select(STAFF_TIME_RECORD_SELECT)
        .eq("staff_account_id", account_id)
        .is_("clock_out_at", "null")
        .limit(1)
        .execute()
    )
    if not open_record:
        raise HTTPException(status_code=409, detail="You are not currently clocked in.")

    updated = rows(
        client.table("staff_time_records")
        .update({
            "clock_out_at": now_iso(),
            "review_status": "pending_review",
            "updated_at": now_iso(),
        })
        .eq("id", str(open_record[0]["id"]))
        .eq("staff_account_id", account_id)
        .eq("review_status", "open")
        .is_("clock_out_at", "null")
        .select(STAFF_TIME_RECORD_SELECT)
        .execute()
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Your work-hours record changed. Refresh and try again.")
    return {"data": staff_time_record_api(updated[0])}


@router.patch("/notifications/{notification_id}/read")
def staff_read_notification(
    notification_id: UUID,
    context: dict[str, Any] = Depends(require_staff),
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
    return {"data": notification_api(result[0])}


@router.patch("/notifications/read-all")
def staff_read_all_notifications(context: dict[str, Any] = Depends(require_staff)):
    (
        service_client()
        .table("admin_notifications")
        .update({"is_read": True, "read_at": now_iso()})
        .eq("recipient_staff_account_id", context["account"]["id"])
        .eq("is_read", False)
        .execute()
    )
    return {"message": "All notifications were marked as read."}


@router.put("/settings")
def update_staff_settings(
    data: StaffSettingsRequest,
    context: dict[str, Any] = Depends(require_staff),
):
    values = model_values(data)
    if not values:
        return {
            "data": staff_settings_api(
                load_staff_settings(context["account"]["id"])
            )
        }

    values.update(
        {
            "staff_account_id": context["account"]["id"],
            "updated_at": now_iso(),
        }
    )
    result = rows(
        service_client()
        .table("staff_settings")
        .upsert(values, on_conflict="staff_account_id")
        .select(STAFF_SETTINGS_SELECT)
        .execute()
    )
    if not result:
        raise HTTPException(status_code=500, detail="Staff settings were not saved.")

    return {
        "message": "Staff settings saved.",
        "data": staff_settings_api(result[0]),
    }

class StaffProfileUpdateRequest(ApiModel):
    personal_email: EmailStr = Field(alias="personalEmail")
    full_name: str = Field(min_length=3, max_length=120, alias="fullName")
    nickname: str = Field(default="", max_length=80)
    avatar_url: str = Field(default="", max_length=180000, alias="avatarUrl")


@router.patch("/profile")
def update_my_staff_profile(data: StaffProfileUpdateRequest, context: dict[str, Any] = Depends(require_staff)):
    # Only this authenticated account is editable; role and login fields are excluded.
    account_id = str(context["account"]["id"])
    name = data.full_name.strip()
    if len(name) < 3:
        raise HTTPException(status_code=422, detail="Enter your full name.")
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
            raise HTTPException(status_code=422, detail="Choose a valid profile picture.") from None
    updates = {
        "full_name": name, "nickname": data.nickname.strip() or None,
        "avatar_url": avatar or None,
        "updated_at": now_iso(), "updated_by_staff_id": account_id,
    }
    updates["personal_email"] = str(data.personal_email).strip()
    saved = rows(service_client().table("staff_accounts").update(updates).eq("id", account_id).select(STAFF_SELECT).execute())
    if not saved:
        raise HTTPException(status_code=404, detail="Your profile could not be found.")
    return {"data": staff_api(saved[0])}
