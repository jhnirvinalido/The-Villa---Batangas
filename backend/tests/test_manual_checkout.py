"""Isolated payment-flow regression tests; no credentials or live payments needed."""
import ast
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def load_functions():
    source = ast.parse((Path(__file__).parents[1] / "booking.py").read_text())
    names = {"_apply_payment", "_finalize_manual_checkout", "sync_manual_checkout_payment"}
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    env = {"_assign_prearrival_staff": MagicMock(), "HTTPException": HTTPError, "Decimal": Decimal, "datetime": datetime, "timezone": timezone,
           "_money": lambda value: Decimal(str(value or 0)).quantize(Decimal(".01")),
           "_first": lambda response: next(iter(response.data or []), None),
           "_attr": lambda obj, key, default=None: getattr(obj, key, default),
           "_normalized_status": lambda value: str(value or "").lower(),
           "_payment_method_code": lambda _: "qrph", "_method_label": lambda _: "QR Ph",
           "_paymongo_mode": lambda: "test", "PAYMONGO_RETRIEVE_CHECKOUT_URL": "https://payment.test/checkout"}
    exec(compile(ast.fix_missing_locations(module), "booking.py", "exec"), env)
    return env


class ManualCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.env = load_functions()
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
        self.booking = {"id": "draft-id", "booking_code": "V-1", "user_id": None,
                        "amount_paid": 0, "total_amount": 1000, "payment_due_amount": 500,
                        "payment_method_code": "qrph", "booking_status": "Pending Payment",
                        "paymongo_checkout_session_id": "cs_1"}
        self.draft = {"booking_payload": self.booking}
        self.session = {"id": "cs_1", "attributes": {}}
        self.payment = {"id": "pay_1", "attributes": {"amount": 50000, "currency": "PHP", "status": "paid"}}
        self.env.update(_service=lambda: self.client, _manual_checkout_draft=lambda *_: self.draft,
                        _paymongo_request=lambda *_args, **_kw: {"data": self.session})

    def test_unpaid_checkout_never_creates_booking_or_payment(self):
        self.env["_session_payment_state"] = lambda _: {"paid": False, "state": "pending", "message": "Awaiting payment"}
        result = self.env["sync_manual_checkout_payment"]("draft-id")
        self.assertEqual(result["state"], "pending")
        self.assertEqual([call.args[0] for call in self.client.table.call_args_list], ["manual_booking_checkouts"])
        self.client.rpc.assert_not_called()
        self.env["_assign_prearrival_staff"].assert_not_called()

    def test_verified_payment_uses_single_atomic_finalization(self):
        saved = {**self.booking, "booking_status": "Confirmed", "amount_paid": 500}
        self.client.rpc.return_value.execute.return_value = SimpleNamespace(data=saved)
        self.env["_session_payment_state"] = lambda _: {"paid": True, "payment": self.payment}
        result = self.env["sync_manual_checkout_payment"]("draft-id")
        self.assertEqual(result["booking"], saved)
        self.env["_assign_prearrival_staff"].assert_called_once_with(saved, self.client)
        name, params = self.client.rpc.call_args.args
        self.assertEqual(name, "finalize_manual_booking_checkout")
        self.assertEqual(params["p_booking_update"]["payment_status"], "Partial")
        self.assertEqual(params["p_payment"]["amount"], 500)
        self.assertEqual([call.args[0] for call in self.client.table.call_args_list], ["booking_payments"])

    def test_wrong_amount_currency_or_session_cannot_finalize(self):
        for key, value in [("amount", 1), ("currency", "USD")]:
            with self.subTest(key=key), self.assertRaises(HTTPError):
                payment = {"id": "pay_1", "attributes": {**self.payment["attributes"], key: value}}
                self.env["_finalize_manual_checkout"](self.client, self.draft, self.session, payment)
        with self.assertRaises(HTTPError):
            self.env["_finalize_manual_checkout"](self.client, self.draft, {"id": "another"}, self.payment)
        self.client.rpc.assert_not_called()

    def test_failed_atomic_save_does_not_fall_back_to_partial_writes(self):
        self.client.rpc.return_value.execute.side_effect = RuntimeError("Database transaction failed")
        with self.assertRaises(RuntimeError):
            self.env["_finalize_manual_checkout"](self.client, self.draft, self.session, self.payment)
        self.client.table.return_value.insert.assert_not_called()
        self.client.table.return_value.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
