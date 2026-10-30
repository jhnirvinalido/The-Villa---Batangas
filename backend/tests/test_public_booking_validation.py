import ast
import re
import unittest
from pathlib import Path


class PublicBookingValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parents[1] / "booking.py"
        tree = ast.parse(source.read_text())
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "validate_public_booking_phone"
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

if __name__ == "__main__":
    unittest.main()
