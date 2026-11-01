import ast
import re
import unittest
from datetime import date, timedelta
from pathlib import Path


class PublicBookingValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parents[1] / "booking.py"
        tree = ast.parse(source.read_text())
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {
                "validate_public_booking_phone",
                "_normalized_status",
                "_availability_blocks_booking",
                "_villa_date_conflict",
            }
        ]
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                *nodes,
            ],
            type_ignores=[],
        )
        cls.env = {
            "re": re,
            "date": date,
            "timedelta": timedelta,
            "AVAILABILITY_RELEASE_STATUSES": {
                "cancelled",
                "completed",
                "checked out",
                "expired",
                "rejected",
            },
        }
        exec(
            compile(ast.fix_missing_locations(module), str(source), "exec"),
            cls.env,
        )

    def test_phone_accepts_common_philippine_formats(self):
        validate = self.env["validate_public_booking_phone"]
        self.assertEqual(validate("0912 345 6789"), "0912 345 6789")
        self.assertEqual(validate("+63 (912) 345-6789"), "+63 (912) 345-6789")

    def test_phone_rejects_letters_and_invalid_lengths(self):
        validate = self.env["validate_public_booking_phone"]
        for value in ("0912abc3456789", "091234567", "12345678901", "+ +639123456789"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(value)

    def test_booking_blocks_the_same_villa_for_the_same_day_and_time(self):
        conflicts = self.env["_villa_date_conflict"]
        booked = {
            "villa_id": "villa-1",
            "check_in_date": "2026-11-01",
            "check_out_date": "2026-11-02",
            "booking_status": "Confirmed",
        }

        self.assertTrue(
            conflicts(booked, date(2026, 11, 1), date(2026, 11, 2))
        )
        self.assertFalse(
            conflicts(booked, date(2026, 11, 2), date(2026, 11, 3))
        )
        self.assertFalse(
            conflicts(
                {**booked, "booking_status": "Cancelled"},
                date(2026, 11, 1),
                date(2026, 11, 2),
            )
        )

if __name__ == "__main__":
    unittest.main()
