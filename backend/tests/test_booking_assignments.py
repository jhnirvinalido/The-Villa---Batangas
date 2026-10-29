"""Deterministic local doubles: no live booking/payment or guest data required."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from booking_assignments import (
    MANILA, SOURCE, ASSIGNMENT_TYPE, assign_prearrival_staff,
    booking_ready, choose_staff, process_confirmed_bookings, stable_id,
    schedule_prearrival_assignment,
)

NOW = datetime(2026, 10, 25, 8, tzinfo=MANILA)


def booking(**overrides):
    return dict(id="booking-1", booking_code="TV-1", booking_status="Confirmed",
                payment_status="Partial", payment_choice="half", total_amount=5000,
                amount_paid=2500, check_in_date="2026-10-26", check_out_date="2026-10-27",
                check_in_time="3:00 PM", villa_name="Villa 1", villa_ids=["villa-1"], **overrides)


def person(id="staff-1", **overrides):
    return dict(id=id, full_name=id, role="staff", department="Housekeeping",
                is_active=True, account_status="Active", shift="8:00 AM – 5:00 PM", **overrides)


class Query:
    def __init__(self, db, table):
        self.db, self.name = db, table
        self.filters, self.values, self.operation = [], None, "select"
        self.bounds = None

    def select(self, *_): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self
    def gte(self, key, value):
        self.filters.append(lambda row: str(row.get(key) or "") >= value)
        return self
    def order(self, *_): return self
    def limit(self, n):
        self.bounds = (0, n)
        return self
    def range(self, start, end):
        self.bounds = (start, end + 1)
        return self
    def upsert(self, value, **_):
        self.operation, self.values = "upsert", value
        return self
    def update(self, value):
        self.operation, self.values = "update", value
        return self
    def execute(self):
        if self.db.fail_table == self.name:
            raise RuntimeError("Storage unavailable")
        table = self.db.data.setdefault(self.name, [])
        if self.operation == "upsert":
            if not any(row["id"] == self.values["id"] for row in table):
                table.append(deepcopy(self.values))
            return SimpleNamespace(data=[])
        rows = [row for row in table if all(test(row) for test in self.filters)]
        if self.operation == "update":
            for row in rows: row.update(self.values)
        if self.bounds: rows = rows[slice(*self.bounds)]
        return SimpleNamespace(data=deepcopy(rows))


class Database:
    fail_table = None
    def __init__(self, records): self.data = records
    def table(self, name): return Query(self, name)


class BookingAssignmentsTests(unittest.TestCase):
    def setUp(self):
        self.row = booking()
        self.db = Database({"bookings": [self.row], "admin_tasks": [],
                            "staff_accounts": [person(), {"id":"admin-1", "role":"admin", "is_active":True, "account_status":"Active"}],
                            "admin_notifications": []})

    def assign(self): return assign_prearrival_staff(self.row, self.db, NOW)

    def test_payment_hook_attempts_assignment_without_waiting_for_worker(self):
        with patch('booking_assignments.booking_ready', return_value=True), \
             patch('booking_assignments.assign_prearrival_staff', return_value={'status': 'assigned'}) as allocate:
            result = schedule_prearrival_assignment(self.row, self.db)
        allocate.assert_called_once_with(self.row, self.db)
        self.assertEqual(result['status'], 'assigned')

    def test_system_task_has_required_database_account_links(self):
        self.assertEqual(self.assign()['status'], 'assigned')
        task = self.db.data['admin_tasks'][0]
        self.assertEqual(task['created_by_staff_id'], 'admin-1')
        self.assertEqual(task['updated_by_staff_id'], 'admin-1')
        self.assertEqual(task['source'], SOURCE)
        self.assertEqual(task['status_history'][0]['actor'], 'System')

    def test_system_assignment_still_works_without_active_administrator(self):
        self.db.data['staff_accounts'] = [person()]
        self.assertEqual(self.assign()['status'], 'assigned')
        self.assertEqual(self.db.data['admin_tasks'][0]['created_by_staff_id'], 'staff-1')

    def test_unpaid_hook_does_not_attempt_assignment(self):
        with patch('booking_assignments.assign_prearrival_staff') as allocate:
            result = schedule_prearrival_assignment({**self.row, 'amount_paid': 0}, self.db)
        allocate.assert_not_called()
        self.assertEqual(result['status'], 'not_eligible')

    def test_only_saved_confirmed_required_payment_is_eligible(self):
        for field, value in (("booking_status", "Pending Payment"), ("booking_status", "Cancelled"),
                             ("booking_status", "Checked In"), ("payment_status", "Unpaid"),
                             ("amount_paid", 2499), ("payment_choice", "full"),
                             ("check_in_date", "2026-10-24"), ("total_amount", 0)):
            row = {**self.row, field:value}
            self.assertFalse(booking_ready(row, NOW), (field, value))
            self.assertEqual(assign_prearrival_staff(row, self.db, NOW)["status"], "not_eligible")
        self.assertTrue(booking_ready(self.row, NOW))
        self.assertTrue(booking_ready({**self.row, "payment_choice":"full", "amount_paid":5000, "payment_status":"Paid"}, NOW))

    def test_assignment_is_linked_ready_before_arrival_and_notifies_both_roles(self):
        result = self.assign()
        self.assertEqual(result["status"], "assigned")
        task = self.db.data["admin_tasks"][0]
        self.assertEqual(task["booking_id"], self.row["id"])
        self.assertEqual(task["assignment_type"], ASSIGNMENT_TYPE)
        self.assertEqual(task["source"], SOURCE)
        self.assertEqual(task["due_time"], "14:00:00")
        self.assertEqual(task["due_date"], self.row["check_in_date"])
        self.assertEqual(task["status_history"][0]["actor"], "System")
        self.assertTrue(task["checklist"])
        self.assertTrue(all(not item["done"] for item in task["checklist"]))
        self.assertEqual({n["recipient_staff_account_id"] for n in self.db.data["admin_notifications"]}, {"staff-1", "admin-1"})

    def test_repeated_and_concurrent_payment_events_create_only_one_task_and_notice(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.assign(), range(8)))
        self.assertEqual(len(self.db.data["admin_tasks"]), 1)
        self.assertEqual(len(self.db.data["admin_notifications"]), 2)
        self.db.data["admin_notifications"][0]["is_read"] = True
        self.assign()
        self.assertTrue(self.db.data["admin_notifications"][0]["is_read"])

    def test_retries_do_not_overwrite_admin_changes_or_completed_checklist(self):
        self.assign()
        task = self.db.data["admin_tasks"][0]
        task["status"] = "In Progress"
        task["title"] = "Adjusted by admin"
        task["checklist"][0]["done"] = True
        self.assign()
        self.assertEqual(task["title"], "Adjusted by admin")
        self.assertEqual(task["status"], "In Progress")
        self.assertTrue(task["checklist"][0]["done"])

    def test_existing_manual_preparation_is_honored(self):
        self.db.data["admin_tasks"] = [{"id":"manual", "booking_id":self.row["id"],
                                       "assignment_type":ASSIGNMENT_TYPE, "status":"Pending"}]
        self.assertEqual(self.assign(), {"status":"existing", "task_id":"manual"})
        self.assertEqual(len(self.db.data["admin_tasks"]), 1)

    def test_no_staff_alert_is_deduplicated_and_worker_recovers_when_staff_available(self):
        self.db.data["staff_accounts"][0]["is_active"] = False
        self.assertEqual(self.assign()["status"], "needs_staff")
        self.assign()
        self.assertEqual(len(self.db.data["admin_notifications"]), 1)
        self.assertEqual(len(self.db.data["admin_tasks"]), 0)
        self.db.data["staff_accounts"][0]["is_active"] = True
        self.assertEqual(process_confirmed_bookings(self.db, NOW)[0]["status"], "assigned")
        alert = next(n for n in self.db.data["admin_notifications"] if n["title"] == "Pre-arrival Staff Assignment Needed")
        self.assertTrue(alert["is_read"])

    def test_booking_assignment_does_not_require_personal_email(self):
        self.assertEqual(self.assign()["status"], "assigned")
        self.assertEqual(self.db.data["admin_tasks"][0]["assigned_staff_id"], "staff-1")
        self.assertEqual(
            {n["recipient_staff_account_id"] for n in self.db.data["admin_notifications"]},
            {"staff-1", "admin-1"},
        )

    def test_random_selection_includes_available_staff_and_excludes_ineligible_staff(self):
        staff = [person(), person("staff-2"), {**person("disabled"), "is_active":False},
                 {**person("maintenance"), "department":"Maintenance"}, {**person("unknown"), "shift":"TBA"}]
        tasks = [{"assigned_staff_id":"staff-1", "status":"Pending", "due_date":"2026-10-26", "due_time":"09:00"}]
        with patch('booking_assignments.random.choice', side_effect=lambda candidates: candidates[-1]) as choice:
            selected, _, end = choose_staff(self.row, staff, tasks, NOW)
        self.assertEqual([entry[0]['id'] for entry in choice.call_args.args[0]], ['staff-1', 'staff-2'])
        self.assertEqual(selected["id"], "staff-2")
        self.assertEqual(end.hour, 14)

    def test_newly_added_staff_participates_without_reassigning_existing_bookings(self):
        first = self.assign()
        original = self.db.data['admin_tasks'][0]['assigned_staff_id']
        self.db.data['staff_accounts'].append(person('new-staff'))
        with patch('booking_assignments.random.choice', side_effect=lambda candidates: candidates[-1]) as choice:
            self.assertEqual(self.assign()['task_id'], first['task_id'])
            choice.assert_not_called()
            other = {**self.row, 'id': 'booking-new', 'booking_code': 'TV-NEW'}
            self.db.data['bookings'].append(other)
            self.assertEqual(assign_prearrival_staff(other, self.db, NOW)['status'], 'assigned')
            self.assertIn('new-staff', [entry[0]['id'] for entry in choice.call_args.args[0]])
        self.assertEqual(self.db.data['admin_tasks'][0]['assigned_staff_id'], original)
        self.assertEqual(self.db.data['admin_tasks'][1]['assigned_staff_id'], 'new-staff')

    def test_overlapping_slot_moves_preparation_earlier(self):
        self.assign()
        other = {**self.row, "id":"booking-2", "booking_code":"TV-2"}
        self.db.data["bookings"].append(other)
        self.assertEqual(assign_prearrival_staff(other, self.db, NOW)["status"], "assigned")
        tasks = self.db.data["admin_tasks"]
        self.assertEqual({t["due_time"] for t in tasks}, {"13:00:00", "14:00:00"})

    def test_task_with_missing_time_blocks_unsafe_schedule_guess(self):
        tasks = [{"assigned_staff_id":"staff-1", "status":"Pending", "due_date":"2026-10-26", "due_time":None}]
        self.assertIsNone(choose_staff(self.row, [person()], tasks, NOW))

    def test_shift_must_cover_preparation_window_and_multivilla_reserves_more_time(self):
        multi = {**self.row, "villa_ids":["villa-1", "villa-2"]}
        _, start, end = choose_staff(multi, [person()], [], NOW)
        self.assertEqual(end-start, timedelta(hours=2))
        self.assertIsNone(choose_staff(multi, [{**person(), "shift":"1:00 PM – 5:00 PM"}], [], NOW))

    def test_late_same_day_confirmation_requires_manual_action_not_past_due_task(self):
        self.assertIsNone(choose_staff({**self.row, "check_in_date":"2026-10-25"}, [person()], [], NOW.replace(hour=14)))

    def test_current_booking_is_rechecked_after_payment_response(self):
        old = deepcopy(self.row)
        self.row["booking_status"] = "Cancelled"
        self.assertEqual(assign_prearrival_staff(old, self.db, NOW)["status"], "not_eligible")
        self.assertFalse(self.db.data["admin_tasks"])

    def test_assignment_storage_failure_never_undoes_verified_booking(self):
        self.db.fail_table = "admin_tasks"
        with self.assertLogs("thevilla.booking_assignments", level="ERROR"):
            self.assertEqual(self.assign()["status"], "retry")
        self.assertEqual(self.row["booking_status"], "Confirmed")
        self.assertEqual(self.row["amount_paid"], 2500)

    def test_notification_failure_can_be_retried_without_duplicating_task(self):
        self.db.fail_table = "admin_notifications"
        with self.assertLogs("thevilla.booking_assignments", level="ERROR"):
            self.assertEqual(self.assign()["status"], "retry")
        self.assertEqual(len(self.db.data["admin_tasks"]), 1)
        self.db.fail_table = None
        self.assertEqual(self.assign()["status"], "existing")
        self.assertEqual(len(self.db.data["admin_tasks"]), 1)
        self.assertEqual(len(self.db.data["admin_notifications"]), 2)

    def test_worker_skips_unpaid_and_past_bookings(self):
        self.db.data["bookings"] = [{**self.row, "amount_paid":0}, {**self.row, "id":"past", "check_in_date":"2026-10-24"}]
        self.assertEqual(process_confirmed_bookings(self.db, NOW), [{"status":"not_eligible"}])
        self.assertFalse(self.db.data["admin_tasks"])


if __name__ == "__main__": unittest.main()

class NotificationRefreshTests(unittest.TestCase):
    def test_ignored_duplicate_notification_does_not_trigger_dashboard_reload(self):
        from unittest.mock import MagicMock
        from booking_assignments import _notify
        client=MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value=SimpleNamespace(data=[])
        with patch('live_updates.emit_table') as emit:
            _notify(client,'staff-1','assigned/booking-1','Assigned','Test message')
        emit.assert_not_called()

    def test_new_notification_triggers_dashboard_reload(self):
        from unittest.mock import MagicMock
        from booking_assignments import _notify
        client=MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value=SimpleNamespace(data=[{'id':'notice-1'}])
        with patch('live_updates.emit_table') as emit:
            _notify(client,'staff-1','assigned/booking-1','Assigned','Test message')
        emit.assert_called_once_with('admin_notifications',{'recipient_staff_account_id':'staff-1'})
