"""Ensure completed admin tasks cannot be edited or deleted."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from booking_assignments import find_schedule_conflict, task_window


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


class CompletedTaskGuards(unittest.TestCase):
    def test_manual_task_creation_route_is_removed(self):
        source = ast.parse((Path(__file__).parents[1] / "admin.py").read_text())
        task_post_routes = [
            decorator
            for node in source.body
            if isinstance(node, ast.FunctionDef)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "post"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and decorator.args[0].value == "/tasks"
        ]
        self.assertEqual(task_post_routes, [])

    def setUp(self):
        source = ast.parse((Path(__file__).parents[1] / "admin.py").read_text())
        routes = [
            node
            for node in source.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"update_task", "delete_task", "task_api", "maintenance_on_call"}
        ]
        for route in routes:
            route.decorator_list = []
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                *routes,
            ],
            type_ignores=[],
        )
        self.client = MagicMock()
        self.current = {"id": "task-1", "status": "Completed", "title": "Approved"}
        self.active_tasks = []
        env = {
            "Depends": lambda _: None,
            "require_admin": None,
            "HTTPException": HTTPError,
            "service_client": lambda: self.client,
            "fetch_task": lambda _: self.current,
            "fetch_staff": lambda staff_id: {
                "id": str(staff_id), "full_name": "Staff Member", "is_active": True,
            },
            "model_values": lambda data: {
                key: value for key, value in vars(data).items() if value is not None
            },
            "find_schedule_conflict": find_schedule_conflict,
            "load_active_staff_tasks": lambda client, staff_ids: self.active_tasks,
            "task_window": task_window,
        }
        exec(compile(ast.fix_missing_locations(module), "admin.py", "exec"), env)
        self.update = env["update_task"]
        self.delete = env["delete_task"]
        self.task_api = env["task_api"]
        self.context = {"account": {"id": "admin-1", "full_name": "Administrator"}}

    def test_task_response_includes_current_assignee_photo(self):
        result = self.task_api(
            {"id": "task-1", "assigned_staff_id": "staff-1"},
            {"full_name": "Staff Member", "avatar_url": "https://example.test/staff.png"},
        )
        self.assertEqual(result["assignedStaffAvatarUrl"], "https://example.test/staff.png")

    def test_maintenance_changes_use_their_own_validated_route(self):
        self.current.update(source="manual-maintenance-request", status="In Progress")
        for action in (lambda: self.update("task-1", object(), self.context), lambda: self.delete("task-1", self.context)):
            with self.subTest(action=action), self.assertRaises(HTTPError) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 409)
        self.client.table.assert_not_called()

    def test_completed_task_cannot_be_edited(self):
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", object(), self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.client.table.assert_not_called()

    def test_completed_task_cannot_be_deleted(self):
        with self.assertRaises(HTTPError) as caught:
            self.delete("task-1", self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.client.table.assert_not_called()

    def test_admin_cannot_complete_an_assignment_on_staffs_behalf(self):
        self.current.update(status="Pending Review", assigned_staff_id="staff-1")
        data = SimpleNamespace(
            status="Completed", review_note=None, assigned_staff_id=None, title=None,
            description=None, department=None, priority=None, due_date=None, due_time=None,
            progress=None, checklist=None, attachments=None, notes=None,
        )
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", data, self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("cannot move from Pending Review to Completed", str(caught.exception))

    def test_admin_cannot_put_an_assignment_into_review(self):
        self.current.update(status="In Progress", assigned_staff_id="staff-1")
        data = SimpleNamespace(
            status="Pending Review", review_note=None, assigned_staff_id=None, title=None,
            description=None, department=None, priority=None, due_date=None, due_time=None,
            progress=None, checklist=None, attachments=None, notes=None,
        )
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", data, self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("cannot move from In Progress to Pending Review", str(caught.exception))

    def test_rescheduling_rejects_an_overlapping_staff_assignment(self):
        self.current.update(
            status="Pending", assigned_staff_id="staff-1",
            due_date="2026-10-26", due_time="14:00:00",
        )
        self.active_tasks = [{
            "id": "task-2", "title": "Existing preparation", "status": "Pending",
            "due_date": "2026-10-26", "due_time": "14:30:00",
        }]
        data = SimpleNamespace(
            status=None, review_note=None, assigned_staff_id="staff-2", title=None,
            description=None, department=None, priority=None, due_date=None, due_time=None,
            progress=None, checklist=None, attachments=None, notes=None,
        )
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", data, self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("already has overlapping work", str(caught.exception))

    def test_staff_assignment_cannot_be_saved_without_a_due_time(self):
        self.current.update(
            status="Pending", assigned_staff_id="staff-1",
            due_date="2026-10-26", due_time=None,
        )
        data = SimpleNamespace(
            status=None, review_note=None, assigned_staff_id="staff-2", title=None,
            description=None, department=None, priority=None, due_date=None, due_time=None,
            progress=None, checklist=None, attachments=None, notes=None,
        )
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", data, self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("valid due date and time", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
