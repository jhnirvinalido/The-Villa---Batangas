"""Admin-managed corrective maintenance, persisted as typed operational tasks.

The existing task JSON audit history holds versioned maintenance snapshots. This
keeps assignment, evidence, review and realtime behavior on the existing durable
store without requiring a parallel task table or a schema migration.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from admin import (
    TASK_SELECT, THE_VILLA_TIMEZONE, fetch_staff, now_iso,
    require_admin, rows, service_client, task_api,
)
from live_updates import emit_table
from villa_catalog import get_villa_catalog_map

SOURCE = "manual-maintenance-request"
router = APIRouter(prefix="/admin/maintenance", tags=["Maintenance"])


class Photo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    phase: Literal["Before", "After"] = "Before"
    url: str = Field(max_length=480000)

    @field_validator("url")
    @classmethod
    def valid_picture(cls, value):
        try:
            header, payload = value.split(",", 1)
            if header not in ("data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"):
                raise ValueError()
            decoded = base64.b64decode(payload, validate=True)
            matches = ((header.startswith("data:image/jpeg") and decoded.startswith(b"\xff\xd8\xff"))
                       or (header.startswith("data:image/png") and decoded.startswith(b"\x89PNG\r\n\x1a\n"))
                       or (header.startswith("data:image/webp") and decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"))
            if not matches or len(decoded) > 350000:
                raise ValueError()
        except (ValueError, binascii.Error):
            raise ValueError("Use a JPEG, PNG or WebP photo smaller than 350 KB.") from None
        return value


class MaintenanceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5, max_length=5000)
    assigned_staff_id: UUID | None = Field(default=None, alias="assignedStaffId")
    response_window_minutes: int | None = Field(default=None, alias="responseWindowMinutes", ge=1, le=240)
    villa_id: str = Field(default="", alias="villaId", max_length=100)
    location: str = Field(default="", max_length=180)
    equipment: str = Field(default="", max_length=180)
    reported_by: str = Field(default="", alias="reportedBy", max_length=160)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    kind: Literal["Repair", "Inspection"] = "Repair"
    blocks_booking: bool = Field(default=False, alias="blocksBooking")
    due_date: date | None = Field(default=None, alias="dueDate")
    contact_method: Literal["Not contacted", "Email", "Phone call", "Messenger", "In person"] = Field(default="Not contacted", alias="contactMethod")
    contact_notes: str = Field(default="", alias="contactNotes", max_length=2000)
    messenger_url: str = Field(default="", alias="messengerUrl", max_length=500)
    repair_notes: str = Field(default="", alias="repairNotes", max_length=5000)
    verification_note: str = Field(default="", alias="verificationNote", max_length=2000)
    waiting_for_parts: bool = Field(default=False, alias="waitingForParts")
    parts_notes: str = Field(default="", alias="partsNotes", max_length=2000)
    repair_cost: Decimal = Field(default=Decimal("0"), alias="repairCost", ge=0, le=99999999, max_digits=10, decimal_places=2)
    photos: list[Photo] = Field(default_factory=list, max_length=4)

    @field_validator("messenger_url")
    @classmethod
    def safe_messenger_url(cls, value):
        if value:
            parsed = urlparse(value)
            if (parsed.scheme != "https" or parsed.hostname not in
                    {"m.me", "www.messenger.com", "messenger.com", "www.facebook.com", "facebook.com"}
                    or parsed.username or parsed.password or parsed.port not in (None, 443)):
                raise ValueError("Use an HTTPS Messenger or Facebook contact link.")
        return value

    @model_validator(mode="after")
    def location_and_parts(self):
        if not self.villa_id and not self.location:
            raise ValueError("Select a villa or enter the affected location.")
        if self.waiting_for_parts and not self.parts_notes:
            raise ValueError("Describe the parts or supplies being awaited.")
        return self


class MaintenanceUpdate(MaintenanceRequest):
    status: Literal["Pending", "In Progress", "Pending Review", "Completed", "Cancelled"]
    expected_updated_at: datetime | None = Field(alias="expectedUpdatedAt")
    response_action: Literal["", "Request availability", "Accepted", "Unavailable", "Proposed time", "No response"] = Field(default="", alias="responseAction")
    expected_arrival: datetime | None = Field(default=None, alias="expectedArrival")
    response_notes: str = Field(default="", alias="responseNotes", max_length=2000)


def details(row):
    for event in reversed(row.get("status_history") or []):
        if isinstance(event, dict) and isinstance(event.get("maintenance"), dict):
            return deepcopy(event["maintenance"])
    return {}


def serialize(row, staff=None):
    value = task_api(row, staff)
    value["maintenance"] = details(row)
    value["maintenance"]["repairNotes"] = row.get("notes") or ""
    value["technicianEmail"] = (staff or {}).get("personal_email") or ""
    return value


def technician(staff_id):
    staff = fetch_staff(str(staff_id))
    if (str(staff.get("role", "")).lower() != "staff"
            or str(staff.get("department", "")).lower() != "maintenance"
            or not staff.get("is_active") or staff.get("account_status") != "Active"):
        raise HTTPException(status_code=422, detail="Choose an active Maintenance staff member.")
    if not str(staff.get("personal_email") or "").strip():
        raise HTTPException(status_code=422, detail="The Maintenance staff member must enter a personal email first.")
    return staff


def request_snapshot(data, current=None):
    previous = details(current or {})
    value = {
        "villaId": data.villa_id, "location": data.location,
        "equipment": data.equipment, "reportedBy": data.reported_by,
        "kind": data.kind, "blocksBooking": data.blocks_booking,
        "contactMethod": data.contact_method, "contactNotes": data.contact_notes,
        "messengerUrl": data.messenger_url, "repairNotes": data.repair_notes,
        "verificationNote": data.verification_note,
        "waitingForParts": data.waiting_for_parts, "partsNotes": data.parts_notes,
        "repairCost": str(data.repair_cost.quantize(Decimal("0.01"))),
        "contactedAt": previous.get("contactedAt"),
        **({"onCall": previous["onCall"]} if previous.get("onCall") else {}),
        **({"suggestedArrival": previous["suggestedArrival"]} if previous.get("suggestedArrival") else {}),
        **({"targetBooking": previous["targetBooking"]} if previous.get("targetBooking") else {}),
        **({"broadcastToMaintenance": previous["broadcastToMaintenance"]} if "broadcastToMaintenance" in previous else {}),
    }
    if data.contact_method == "Not contacted":
        value["contactedAt"] = None
    elif (not previous.get("contactedAt") or data.contact_method != previous.get("contactMethod")
          or data.contact_notes != previous.get("contactNotes")):
        value["contactedAt"] = now_iso()
    return value


def task_fields(data, staff):
    villa_name = data.location
    if data.villa_id:
        catalog = get_villa_catalog_map()
        villa = catalog.get(data.villa_id)
        if not villa:
            raise HTTPException(status_code=422, detail="The selected villa was not found.")
        villa_name = villa.get("title") or villa.get("name") or data.villa_id
    if data.blocks_booking and not data.villa_id:
        raise HTTPException(status_code=422, detail="Select the villa whose bookings should be paused.")
    return {
        "title": data.title, "description": data.description,
        "assigned_staff_id": str(data.assigned_staff_id),
        "assigned_role": staff.get("position"), "department": "Maintenance",
        "villa_name": villa_name, "priority": data.priority,
        "due_date": (data.due_date or datetime.now(THE_VILLA_TIMEZONE).date()).isoformat(),
        "due_time": "23:59:00", "notes": data.repair_notes,
        "attachments": [photo.model_dump() for photo in data.photos],
    }


def audit(context, status, snapshot, note):
    return {"id": str(uuid4()), "status": status,
            "actor": context["account"]["full_name"],
            "actorStaffId": str(context["account"]["id"]),
            "timestamp": now_iso(), "note": note, "maintenance": snapshot}


@router.get("")
def list_maintenance(context=Depends(require_admin)):
    from maintenance_oncall import link_configuration_error
    client = service_client()
    records = rows(client.table("admin_tasks").select(TASK_SELECT).eq("source", SOURCE)
                   .order("created_at", desc=True).limit(2000).execute())
    ids = list({str(row["assigned_staff_id"]) for row in records if row.get("assigned_staff_id")})
    staff_map = {}
    if ids:
        staff_map = {str(item["id"]): item for item in rows(client.table("staff_accounts")
                         .select("id,full_name,personal_email,position,avatar_url,nickname").in_("id", ids).execute())}
    return {"data": [serialize(row, staff_map.get(str(row.get("assigned_staff_id")))) for row in records], "configurationNotice": link_configuration_error()}


@router.post("", status_code=201)
def create_maintenance(data: MaintenanceRequest, context=Depends(require_admin)):
    from maintenance_oncall import begin_dispatch, choose_technician, notify_maintenance_team, suggest_maintenance_schedule
    client = service_client()
    staff = technician(data.assigned_staff_id) if data.assigned_staff_id else choose_technician(client)
    if not staff:
        raise HTTPException(status_code=422, detail="Ask an active Maintenance technician to enter a personal email first.")
    data = data.model_copy(update={"assigned_staff_id": staff["id"], "blocks_booking": False})
    snapshot = request_snapshot(data)
    snapshot.update(suggest_maintenance_schedule(client, data.villa_id))
    broadcast = str(context.get("account", {}).get("role", "")).lower() == "admin"
    snapshot["broadcastToMaintenance"] = broadcast
    begin_dispatch({"assigned_staff_id": str(staff["id"]), "priority": data.priority}, snapshot, window=data.response_window_minutes)
    code = "MAINT-" + datetime.now(THE_VILLA_TIMEZONE).strftime("%Y%m%d") + "-" + uuid4().hex[:6].upper()
    record = {**task_fields(data, staff), "task_code": code,
              "source": SOURCE, "assignment_type": "maintenance-repair", "from_booking": False,
              "created_by_staff_id": str(context["account"]["id"]),
              "updated_by_staff_id": str(context["account"]["id"]),
              "status": "Pending", "progress": 0,
              "checklist": [{"id": str(uuid4()), "label": label, "done": False} for label in
                            ("Inspect and diagnose the issue", "Complete repair and record repair notes", "Confirm the area or equipment is ready for use")],
              "status_history": [audit(context, "Pending", snapshot, "Issue reported; technician availability request queued.")]}
    saved = rows(client.table("admin_tasks").insert(record).select(TASK_SELECT).execute())
    if not saved:
        raise HTTPException(status_code=500, detail="The maintenance request could not be saved.")
    emit_table("admin_tasks", saved[0])
    if broadcast:
        notify_maintenance_team(client, saved[0])
    return {"message": "Maintenance request created.", "data": serialize(saved[0], staff)}


@router.patch("/{request_id}")
def update_maintenance(request_id: UUID, data: MaintenanceUpdate, context=Depends(require_admin)):
    client = service_client()
    found = rows(client.table("admin_tasks").select(TASK_SELECT).eq("id", str(request_id)).eq("source", SOURCE).limit(1).execute())
    if not found:
        raise HTTPException(status_code=404, detail="Maintenance request was not found.")
    current = found[0]
    previous_meta = details(current)
    if previous_meta.get("villaId") and data.villa_id != previous_meta["villaId"]:
        raise HTTPException(status_code=409, detail="Keep this request linked to its original villa. Report a separate issue for another villa.")
    if current.get("status") in {"Completed", "Cancelled"}:
        raise HTTPException(status_code=409, detail="Closed requests are read-only. Create a new request if another repair is needed.")
    stored_version = current.get("updated_at")
    parsed_version = datetime.fromisoformat(str(stored_version).replace("Z", "+00:00")) if stored_version else None
    if parsed_version != data.expected_updated_at:
        raise HTTPException(status_code=409, detail="This request changed. Refresh it before saving again.")
    allowed = {"Pending": {"Pending", "In Progress", "Cancelled"},
               "In Progress": {"In Progress", "Pending Review", "Cancelled"},
               "Pending Review": {"Pending Review", "In Progress", "Completed", "Cancelled"}}
    if data.status not in allowed.get(current["status"], set()):
        raise HTTPException(status_code=409, detail=f"A request cannot move from {current['status']} to {data.status}.")
    if data.waiting_for_parts and data.status in {"Pending Review", "Completed"}:
        raise HTTPException(status_code=422, detail="Clear Waiting for parts before submitting or verifying this repair.")
    if data.status in {"Pending Review", "Completed"} and len(data.repair_notes) < 5:
        raise HTTPException(status_code=422, detail="Record the repair performed before requesting verification.")
    if data.status == "Completed" and len(data.verification_note) < 5:
        raise HTTPException(status_code=422, detail="An administrator verification note is required to close this repair.")
    if previous_meta.get("blocksBooking") and not data.blocks_booking and data.status not in {"Completed", "Cancelled"}:
        raise HTTPException(status_code=409, detail="Verify or cancel the blocking request before restoring booking availability.")
    if data.status == "Cancelled" and previous_meta.get("blocksBooking") and len(data.verification_note) < 5:
        raise HTTPException(status_code=422, detail="Explain why it is safe to cancel this booking-blocking request.")
    from maintenance_oncall import begin_dispatch, record_response
    assigned_id = str(data.assigned_staff_id or current["assigned_staff_id"])
    reassigned = assigned_id != str(current["assigned_staff_id"])
    if reassigned and (current["status"] != "Pending" or data.status != "Pending"):
        raise HTTPException(status_code=409, detail="Reassign a technician before repair work starts.")
    if data.response_action and current["status"] != "Pending":
        raise HTTPException(status_code=409, detail="Availability responses can only be recorded before repair work starts.")
    if reassigned and data.response_action not in {"", "Request availability"}:
        raise HTTPException(status_code=409, detail="Save the new technician first, then record their response.")
    data = data.model_copy(update={"assigned_staff_id": assigned_id})
    staff = fetch_staff(assigned_id) if data.status in {"Completed", "Cancelled"} and not reassigned else technician(assigned_id)
    snapshot = request_snapshot(data, current)
    if reassigned or data.response_action == "Request availability":
        begin_dispatch({**current, "assigned_staff_id": assigned_id, "priority": data.priority}, snapshot, window=data.response_window_minutes)
    elif data.response_action:
        if data.contact_method == "Not contacted":
            raise HTTPException(status_code=422, detail="Select how the technician provided this response.")
        if data.response_action != "Accepted" and len(data.response_notes) < 3:
            raise HTTPException(status_code=422, detail="Add a short note explaining the technician response.")
        if not snapshot.get("onCall"):
            begin_dispatch(current, snapshot, window=data.response_window_minutes)
        if data.expected_arrival and snapshot.get("villaId"):
            from maintenance_oncall import ensure_arrival_not_booked
            ensure_arrival_not_booked(client, snapshot["villaId"], data.expected_arrival)
        record_response(snapshot, data.response_action, data.expected_arrival, data.response_notes, "Administrator / " + data.contact_method)
    if data.status == "In Progress" and snapshot.get("villaId"):
        if (snapshot.get("onCall") or {}).get("state") != "Accepted":
            raise HTTPException(status_code=409, detail="Confirm the technician's availability before pausing bookings and starting maintenance.")
        data = data.model_copy(update={"blocks_booking": True})
    else:
        data = data.model_copy(update={"blocks_booking": bool(previous_meta.get("blocksBooking"))})
    snapshot["blocksBooking"] = data.blocks_booking
    if (data.status == "In Progress" and current["status"] == "Pending"
            and snapshot.get("onCall") and snapshot["onCall"]["state"] != "Accepted"):
        raise HTTPException(status_code=409, detail="Confirm the technician's availability and arrival time before starting the repair.")
    note = ("Repair verified and closed. " + data.verification_note if data.status == "Completed"
            else "Request updated by administrator.")
    now = now_iso()
    changes = {**task_fields(data, staff), "status": data.status,
               "updated_by_staff_id": str(context["account"]["id"]), "updated_at": now,
               "status_history": [*(current.get("status_history") or []), audit(context, data.status, snapshot, note)]}
    if data.status == "In Progress" and not current.get("started_at"):
        changes["started_at"] = now
    if data.status in {"Pending Review", "Completed"}:
        changes["checklist"] = [{**item, "done": True} for item in current.get("checklist") or []]
        changes["progress"] = 100
        if not current.get("submitted_at"):
            changes["submitted_at"] = now
    if data.status == "In Progress" and current["status"] == "Pending Review":
        changes["submitted_at"] = None
    if data.status == "Completed":
        changes.update(approved_at=now, approved_by_staff_id=str(context["account"]["id"]))
    query = client.table("admin_tasks").update(changes).eq("id", str(request_id)).eq("source", SOURCE)
    query = query.eq("updated_at", stored_version) if stored_version else query.is_("updated_at", "null")
    saved = rows(query.select(TASK_SELECT).execute())
    if not saved:
        raise HTTPException(status_code=409, detail="This request changed. Refresh it before saving again.")
    emit_table("admin_tasks", saved[0], current)
    if data.villa_id:
        emit_table("villa_catalog")
    return {"message": "Maintenance request saved.", "data": serialize(saved[0], staff)}
