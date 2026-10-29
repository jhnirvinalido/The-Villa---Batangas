"""Ensure approved admin tasks cannot be edited or deleted."""
import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock


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
        env = {
            "Depends": lambda _: None,
            "require_admin": None,
            "HTTPException": HTTPError,
            "service_client": lambda: self.client,
            "fetch_task": lambda _: self.current,
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

    def test_approved_task_cannot_be_edited(self):
        with self.assertRaises(HTTPError) as caught:
            self.update("task-1", object(), self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.client.table.assert_not_called()

    def test_approved_task_cannot_be_deleted(self):
        with self.assertRaises(HTTPError) as caught:
            self.delete("task-1", self.context)
        self.assertEqual(caught.exception.status_code, 409)
        self.client.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
