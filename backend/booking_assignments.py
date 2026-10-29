"""Pre-arrival housekeeping allocation after verified booking confirmation.

Uses existing task/notification primary keys for idempotency, including races
between payment webhooks, status polling and the recovery worker. No guest
request can specify the assignee. The existing booking is the durable retry job.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import random
import re
from threading import Lock
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

logger = logging.getLogger("thevilla.booking_assignments")
MANILA = ZoneInfo("Asia/Manila")
SOURCE = "automatic-booking-preparation"
ASSIGNMENT_TYPE = "housekeeping-pre-arrival"
ACTIVE_STATES = ("Pending", "In Progress", "Pending Review")
PREPARATION_MINUTES = 60
_ALLOCATION_LOCK = Lock()
CHECKLIST = (
    "Clean and sanitize bedrooms, bathrooms, kitchen and common areas",
    "Replace bed linens and towels",
    "Restock toiletries and guest amenities",
    "Check pool and guest-use areas for cleanliness and readiness",
    "Report damage, missing items or maintenance concerns",
    "Complete a final readiness check for every villa in this booking",
)


def stable_id(*parts):
    return str(uuid5(NAMESPACE_URL, "thevilla/booking-preparation/" + "/".join(map(str, parts))))


def _rows(response):
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def booking_ready(booking, now=None):
    """A saved Confirmed booking with the required payment; never a draft."""
    now = now or datetime.now(MANILA)
    if str(booking.get("booking_status") or "").strip().lower() != "confirmed":
        return False
    if str(booking.get("stay_status") or "").strip().lower() in {
        "checked in", "checked out", "completed", "cancelled", "canceled",
    }:
        return False
    if str(booking.get("payment_status") or "").strip().lower() not in {"paid", "partial"}:
        return False
    try:
        total, paid = _money(booking.get("total_amount")), _money(booking.get("amount_paid"))
        required = total if str(booking.get("payment_choice") or "half").lower() == "full" else (total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        check_in = date.fromisoformat(str(booking.get("check_in_date"))[:10])
        return bool(booking.get("id")) and total > 0 and paid >= required and check_in >= now.astimezone(MANILA).date()
    except (InvalidOperation, ValueError, TypeError):
        return False


def parse_time(value):
    """Accept existing portal 12-hour shifts and 24-hour task times."""
    value = str(value or "").strip().upper()
    for fmt in ("%I:%M %p", "%I %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    raise ValueError("A valid time is required")


def arrival_at(booking):
    day = date.fromisoformat(str(booking["check_in_date"])[:10])
    return datetime.combine(day, parse_time(booking.get("check_in_time") or "3:00 PM"), MANILA)


def shift_contains(staff, start, end):
    # Unknown/missing shifts are not treated as proof of availability.
    parts = re.split(r"\s*[–—-]\s*", str(staff.get("shift") or ""))
    if len(parts) != 2:
        return False
    try:
        shift_start, shift_end = map(parse_time, parts)
    except ValueError:
        return False
    for day in (start.date(), start.date() - timedelta(days=1)):
        begins = datetime.combine(day, shift_start, MANILA)
        finishes = datetime.combine(day, shift_end, MANILA)
        if finishes <= begins:
            finishes += timedelta(days=1)
        if begins <= start and end <= finishes:
            return True
    return False


def task_window(task):
    """Honor explicit automatic slots; use a conservative hour for manual tasks."""
    for entry in task.get("status_history") or []:
        window = entry.get("preparationWindow") or {}
        if window.get("start") and window.get("end"):
            try:
                start, end = (datetime.fromisoformat(window[key]).astimezone(MANILA) for key in ("start", "end"))
                # A rescheduled task must use its edited schedule, not its original slot.
                if (end.date().isoformat() == str(task.get("due_date"))[:10]
                        and end.time().replace(tzinfo=None) == parse_time(task.get("due_time"))):
                    return start, end
            except (ValueError, TypeError):
                pass
    try:
        day = date.fromisoformat(str(task.get("due_date"))[:10])
        end = datetime.combine(day, parse_time(task.get("due_time")), MANILA)
        return end - timedelta(minutes=PREPARATION_MINUTES), end
    except (ValueError, TypeError):
        return None


def choose_staff(booking, staff_rows, tasks, now=None):
    """Randomly choose available staff, using their latest free preparation slot.

    One hour per booked villa is reserved. Existing tasks without a schedule on
    this date block automatic allocation to that staff rather than guessing.
    This is planned availability, not a leave/attendance integration.
    """
    now = (now or datetime.now(MANILA)).astimezone(MANILA)
    arrival = arrival_at(booking)
    villa_ids = booking.get("villa_ids")
    villa_count = max(1, len(set(villa_ids))) if isinstance(villa_ids, list) else 1
    duration = timedelta(minutes=PREPARATION_MINUTES * villa_count)
    # Finish at least one hour before check-in, trying earlier hourly slots.
    latest_end = arrival - timedelta(hours=1)
    candidates = []
    for staff in staff_rows:
        if (str(staff.get("role") or "").lower() != "staff"
                or str(staff.get("department") or "").lower() != "housekeeping"
                or staff.get("is_active") is not True
                or str(staff.get("account_status") or "").lower() != "active"):
            continue
        own = [t for t in tasks if str(t.get("assigned_staff_id")) == str(staff["id"])
               and t.get("status") in ACTIVE_STATES]
        daily = [t for t in own if str(t.get("due_date") or "")[:10] == arrival.date().isoformat()]
        if any(task_window(task) is None for task in daily):
            continue
        for hours in range(24):
            end = latest_end - timedelta(hours=hours)
            start = end - duration
            if start.date() != arrival.date() or start < now or not shift_contains(staff, start, end):
                continue
            if any(window and start < window[1] and end > window[0] for window in map(task_window, own)):
                continue
            candidates.append((staff, start, end))
            break
    if not candidates:
        return None
    # Exactly one candidate per staff member: equal chance regardless of how
    # many free windows they have. Repeated booking events honor the saved task.
    return random.choice(candidates)


def _notify(client, recipient, key, title, message, task_id=None):
    # ignore_duplicates preserves read state on repeated worker passes.
    result = client.table("admin_notifications").upsert({
        "id": stable_id("notification", key, recipient),
        "recipient_staff_account_id": recipient,
        "title": title, "message": message, "type": "assignment", "icon": "task",
        "task_id": task_id, "is_read": False,
    }, on_conflict="id", ignore_duplicates=True).execute()
    from live_updates import emit_table
    if result.data:
        emit_table("admin_notifications", {"recipient_staff_account_id": recipient})


def _admins(client):
    return _rows(client.table("staff_accounts").select("id").eq("role", "admin")
                 .eq("is_active", True).eq("account_status", "Active").execute())


def _notify_outcome(client, booking, task=None, staff=None, reason=None):
    booking_id = str(booking["id"])
    reference = booking.get("booking_code") or booking_id
    if task:
        key = f"assigned/{booking_id}"
        message = f"{staff.get('full_name') or 'Housekeeping staff'} was automatically assigned to prepare {booking.get('villa_name') or 'the booked villas'} for {reference}, due {task['due_date']} at {task['due_time']}."
        _notify(client, str(staff["id"]), key, "New Pre-arrival Assignment", message, task["id"])
        title = "Housekeeping Automatically Assigned"
    else:
        key = f"needs-staff/{booking_id}"
        title = "Pre-arrival Staff Assignment Needed"
        message = f"{reference}: {reason} Assign Housekeeping staff or adjust the schedule in the Assignment Monitor. The booking remains confirmed."
    for admin in _admins(client):
        _notify(client, str(admin["id"]), key, title, message, task["id"] if task else None)
        if task:
            client.table("admin_notifications").update({"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}).eq("id", stable_id("notification", f"needs-staff/{booking_id}", admin["id"])).eq("is_read", False).execute()


def _assign(booking, client, now):
    booking_id = str(booking["id"])
    existing = _rows(client.table("admin_tasks").select("*").eq("booking_id", booking_id)
                     .eq("assignment_type", ASSIGNMENT_TYPE).execute())
    # Do not recreate cancelled deterministic tasks or undo admin edits.
    # Any existing noncancelled manual preparation assignment also satisfies it.
    auto_id = stable_id("task", booking_id)
    for task in existing:
        if task.get("id") == auto_id or task.get("status") != "Cancelled":
            if task.get("source") == SOURCE and task.get("status") in ACTIVE_STATES:
                assigned = _rows(client.table("staff_accounts").select("id,full_name").eq("id", task["assigned_staff_id"]).execute())
                if assigned:
                    _notify_outcome(client, booking, task, assigned[0])
            return {"status": "existing", "task_id": task["id"]}
    staff = _rows(client.table("staff_accounts").select("id,full_name,role,department,position,shift,is_active,account_status")
                  .eq("role", "staff").eq("department", "Housekeeping").eq("is_active", True).eq("account_status", "Active").execute())
    if not staff:
        _notify_outcome(client, booking, reason="No active Housekeeping staff member is available.")
        return {"status": "needs_staff"}
    # Fetch all pages: truncating task workload could silently double-book staff.
    tasks = []
    for offset in range(0, 100000, 1000):
        page = _rows(client.table("admin_tasks").select("id,assigned_staff_id,status,due_date,due_time,status_history")
                     .in_("assigned_staff_id", [str(s["id"]) for s in staff]).in_("status", list(ACTIVE_STATES))
                     .order("id").range(offset, offset + 999).execute())
        tasks.extend(page)
        if len(page) < 1000:
            break
    else:
        raise RuntimeError("Task workload is too large to allocate safely")
    selection = choose_staff(booking, staff, tasks, now)
    if not selection:
        _notify_outcome(client, booking, reason="No free Housekeeping preparation window fits the recorded shifts before arrival.")
        return {"status": "needs_staff"}
    person, start, end = selection
    # The deployed schema requires an account FK even for system work. Use an
    # administrator as the record owner (or the assignee if no admin is active).
    # SOURCE and the audit actor identify the actual creator as System; the API
    # deliberately displays System instead of this compatibility account.
    administrators = _admins(client)
    owner_id = min(str(admin['id']) for admin in administrators) if administrators else str(person['id'])
    timestamp = now.astimezone(timezone.utc).isoformat()
    code = "AUTO-" + auto_id.replace("-", "")[:20].upper()
    task = {
        "id": auto_id, "task_code": code, "booking_id": booking_id,
        "booking_code": booking.get("booking_code"), "booking_status": booking.get("booking_status"),
        "booking_payment_status": booking.get("payment_status"),
        "booking_check_in": booking.get("check_in_date"), "booking_check_out": booking.get("check_out_date"),
        "villa_name": booking.get("villa_name"), "guest_name": booking.get("customer_name"),
        "guest_phone": booking.get("customer_phone"), "guest_email": booking.get("customer_email"),
        "assigned_staff_id": str(person["id"]), "created_by_staff_id": owner_id, "updated_by_staff_id": owner_id,
        "assignment_type": ASSIGNMENT_TYPE, "title": f"Pre-arrival preparation – {booking.get('villa_name') or 'Booked villas'}",
        "description": "Clean and prepare every villa in this booking before guest arrival. Report issues for admin review.",
        "department": "Housekeeping", "assigned_role": person.get("position"), "priority": "High",
        "due_date": end.date().isoformat(), "due_time": end.time().replace(tzinfo=None).isoformat(),
        "status": "Pending", "progress": 0, "attachments": [], "from_booking": True, "source": SOURCE,
        "notes": f"Planned preparation: {start.strftime('%Y-%m-%d %I:%M %p')}–{end.strftime('%I:%M %p')} Asia/Manila. Guest arrival: {arrival_at(booking).strftime('%I:%M %p')}. Admin may adjust the assignee or schedule.",
        "checklist": [{"id": f"{code}-{i}", "label": label, "done": False} for i, label in enumerate(CHECKLIST, 1)],
        "status_history": [{"id": stable_id("audit", booking_id), "status": "Pending", "actor": "System",
                            "note": "Automatically assigned after verified booking confirmation.", "timestamp": timestamp,
                            "preparationWindow": {"start": start.isoformat(), "end": end.isoformat()}}],
    }
    # Unique task PK handles repeated events and cross-process races. On conflict,
    # never overwrite an assignee, checklist, progress or schedule edited by admin.
    client.table("admin_tasks").upsert(task, on_conflict="id", ignore_duplicates=True).execute()
    saved = _rows(client.table("admin_tasks").select("*").eq("id", auto_id).execute())
    if not saved:
        raise RuntimeError("Automatic preparation task could not be read after saving")
    task = saved[0]
    from live_updates import emit_table
    emit_table("admin_tasks", task)
    assigned = _rows(client.table("staff_accounts").select("id,full_name").eq("id", task["assigned_staff_id"]).execute())
    if assigned:
        _notify_outcome(client, booking, task, assigned[0])
    return {"status": "assigned", "task_id": task["id"]}


def assign_prearrival_staff(booking, client, now=None):
    """Secondary effects cannot roll back an already verified payment/booking."""
    now = now or datetime.now(MANILA)
    if not booking_ready(booking, now):
        return {"status": "not_eligible"}
    try:
        with _ALLOCATION_LOCK:
            # Payment responses can be stale: re-read before allocating work.
            current = _rows(client.table("bookings").select("*").eq("id", str(booking["id"])).limit(1).execute())
            if not current or not booking_ready(current[0], now):
                return {"status": "not_eligible"}
            return _assign(current[0], client, now)
    except Exception:
        logger.exception("Pre-arrival allocation needs retry for booking %s", booking.get("id"))
        return {"status": "retry"}


def process_confirmed_bookings(client=None, now=None):
    """Recover missed hooks and no-staff outcomes, without requiring a page visit."""
    if client is None:
        from booking import _service
        client = _service()
    now = now or datetime.now(MANILA)
    outcomes = []
    offset = 0
    while True:
        bookings = _rows(client.table("bookings").select("*").eq("booking_status", "Confirmed")
                         .gte("check_in_date", now.astimezone(MANILA).date().isoformat())
                         .order("id").range(offset, offset + 99).execute())
        for booking in bookings:
            outcomes.append(assign_prearrival_staff(booking, client, now))
        if len(bookings) < 100:
            return outcomes
        offset += 100


def schedule_prearrival_assignment(booking, client=None):
    """Assign after confirmation; worker wake-up remains a recovery path."""
    if not booking_ready(booking):
        return {"status": "not_eligible"}
    from live_updates import emit_table
    emit_table("bookings", {"id": booking["id"]})
    if client is None:
        # The payment hooks supply their existing service client. Other callers
        # may still queue recovery without opening another database connection.
        return {"status": "queued"}
    return assign_prearrival_staff(booking, client)
