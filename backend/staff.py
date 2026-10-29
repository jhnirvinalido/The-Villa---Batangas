from __future__ import annotations

from task_workflow import staff_checklist_update, task_start_is_available

import secrets
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
    TASK_SELECT,
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
    task_api,
)

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
    status: Literal["Pending", "In Progress", "Pending Review"] | None = None
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


def require_staff(
    request: Request,
) -> dict[str, Any]:
    token = bearer_token(
        request
    )

    account = (
        validate_portal_access_token(
            token,
            required_role="staff",
        )
    )

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
            filters=[("role", "staff"), ("is_active", True), ("account_status", "Active")], order_column="full_name", limit=5000),
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
    if current.get("status") == "Pending Review":
        raise HTTPException(
            status_code=409,
            detail="This task is waiting for administrator review.",
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
    allowed = {
        "Pending": {"Pending", "In Progress"},
        "In Progress": {"In Progress", "Pending Review"},
    }
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
        if current.get("source") == "manual-maintenance-request":
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
        title = (
            "Assignment Submitted for Review"
            if next_status == "Pending Review"
            else "Assignment Started"
        )
        notify_admins(
            title,
            f"{context['account']['full_name']} changed “{current['title']}” to {next_status}.",
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
