"""Timekeeping route contracts, using an isolated database double."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call

ROOT = Path(__file__).parents[1]
STAMP = "2026-11-02T08:00:00+00:00"


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def load_functions(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, filename, "exec"), namespace)


class StaffTimeRecordTests(unittest.TestCase):
    def setUp(self):
        self.query = MagicMock()
        for method in ["select", "eq", "is_", "limit", "order", "insert", "update"]:
            getattr(self.query, method).return_value = self.query
        self.client = MagicMock()
        self.client.table.return_value = self.query
        self.env = {
            "Depends": lambda _: None, "Query": lambda **_: None,
            "require_staff": None, "require_admin": None,
            "HTTPException": HTTPError, "service_client": lambda: self.client,
            "rows": lambda response: response.data, "now_iso": lambda: STAMP,
            "STAFF_TIME_RECORD_SELECT": "*",
        }
        load_functions("admin.py", {"staff_time_record_api", "review_staff_time_record"}, self.env)
        load_functions("staff.py", {"staff_list_time_records", "staff_clock_in", "staff_clock_out"}, self.env)
        self.context = {"account": {"id": "staff-a"}}
        self.record = {"id": "time-a", "staff_account_id": "staff-a", "clock_in_at": STAMP, "review_status": "open"}

    def results(self, *records):
        self.query.execute.side_effect = [SimpleNamespace(data=value) for value in records]

    def test_staff_list_is_scoped_and_uses_the_frontend_contract(self):
        self.results([self.record])
        result = self.env["staff_list_time_records"](self.context)
        self.query.eq.assert_called_with("staff_account_id", "staff-a")
        self.assertEqual(result["data"][0]["clockInAt"], STAMP)
        self.assertEqual(result["data"][0]["reviewStatus"], "open")

    def test_clock_in_rejects_a_second_open_record(self):
        self.results([self.record])
        with self.assertRaises(HTTPError) as error:
            self.env["staff_clock_in"](self.context)
        self.assertEqual(error.exception.status_code, 409)
        self.query.insert.assert_not_called()

    def test_clock_in_uses_server_time_and_the_current_staff_account(self):
        self.results([], [self.record])
        self.env["staff_clock_in"](self.context)
        self.query.insert.assert_called_once_with({"staff_account_id": "staff-a", "clock_in_at": STAMP, "review_status": "open"})

    def test_clock_out_is_scoped_and_submitted_for_review(self):
        self.results([self.record], [{**self.record, "clock_out_at": STAMP, "review_status": "pending_review"}])
        result = self.env["staff_clock_out"](self.context)
        self.assertEqual(result["data"]["reviewStatus"], "pending_review")
        self.assertIn(call("staff_account_id", "staff-a"), self.query.eq.call_args_list)
        self.assertIn(call("review_status", "open"), self.query.eq.call_args_list)
        self.assertEqual(self.query.update.call_args.args[0]["clock_out_at"], STAMP)

    def test_clock_out_requires_an_open_record(self):
        self.results([])
        with self.assertRaises(HTTPError) as error:
            self.env["staff_clock_out"](self.context)
        self.assertEqual(error.exception.status_code, 409)
        self.query.update.assert_not_called()

    def review(self, status="approved", note=""):
        return self.env["review_staff_time_record"]("time-a", SimpleNamespace(review_status=status, review_note=note), {"account": {"id": "admin-a"}})

    def test_flagging_requires_an_explanation(self):
        with self.assertRaises(HTTPError) as error:
            self.review("needs_correction")
        self.assertEqual(error.exception.status_code, 422)
        self.client.table.assert_not_called()

    def test_an_open_shift_cannot_be_approved(self):
        self.results([self.record])
        with self.assertRaises(HTTPError) as error:
            self.review()
        self.assertEqual(error.exception.status_code, 409)
        self.query.update.assert_not_called()

    def test_approval_records_the_administrator_and_server_time(self):
        closed = {**self.record, "clock_out_at": STAMP, "review_status": "pending_review"}
        self.results([closed], [{**closed, "review_status": "approved"}])
        result = self.review(note="Checked against the shift")
        update = self.query.update.call_args.args[0]
        self.assertEqual(update["reviewed_by_staff_id"], "admin-a")
        self.assertEqual(update["reviewed_at"], STAMP)
        self.assertEqual(result["data"]["reviewStatus"], "approved")

    def test_a_stale_approval_does_not_overwrite_a_reviewed_record(self):
        closed = {**self.record, "clock_out_at": STAMP, "review_status": "pending_review"}
        self.results([closed], [])
        with self.assertRaises(HTTPError) as error:
            self.review()
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn(call("review_status", "pending_review"), self.query.eq.call_args_list)


if __name__ == "__main__":
    unittest.main()
