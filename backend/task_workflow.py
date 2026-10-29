"""Checklist rules shared by staff updates, independent of API/database clients."""

from datetime import date, datetime, time as datetime_time
from zoneinfo import ZoneInfo


MANILA_TZ = ZoneInfo("Asia/Manila")


def task_start_is_available(due_date, due_time, now=None):
    if not due_date or not due_time:
        return False
    try:
        scheduled_date = date.fromisoformat(str(due_date)[:10])
        time_value = due_time.isoformat() if isinstance(due_time, datetime_time) else str(due_time)
        scheduled_time = datetime_time.fromisoformat(time_value).replace(tzinfo=None)
    except (TypeError, ValueError):
        return False

    scheduled_at = datetime.combine(scheduled_date, scheduled_time, tzinfo=MANILA_TZ)
    current_time = now or datetime.now(MANILA_TZ)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=MANILA_TZ)
    else:
        current_time = current_time.astimezone(MANILA_TZ)
    return current_time.date() == scheduled_date and current_time <= scheduled_at


def staff_checklist_update(stored, incoming, task_id):
    canonical = [
        {"id": str(item.get("id") or f"{task_id}-check-{index}"),
         "label": str(item.get("label") or item.get("text") or f"Checklist item {index + 1}"),
         "done": bool(item.get("done"))}
        for index, item in enumerate(stored or [])
    ]
    incoming_ids = [str(item.get("id") or "") for item in incoming]
    expected_ids = [item["id"] for item in canonical]
    if len(incoming_ids) != len(set(incoming_ids)) or set(incoming_ids) != set(expected_ids):
        raise ValueError("The checklist changed. Refresh the task and try again. Staff can complete steps but cannot add or remove them.")
    changes = {str(item["id"]): bool(item.get("done")) for item in incoming}
    checklist = [{**item, "done": changes[item["id"]]} for item in canonical]
    progress = round(sum(item["done"] for item in checklist) / len(checklist) * 100) if checklist else 0
    return checklist, progress
