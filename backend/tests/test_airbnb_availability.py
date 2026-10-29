from datetime import date
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from admin import (
    ManualBookingRequest,
    list_manual_airbnb_stays,
    manual_booking_airbnb_availability,
)


class AirbnbAvailabilityTests(TestCase):
    def setUp(self):
        self.catalog = {
            "villa-a": {"name": "Villa A", "capacity": 2},
            "villa-b": {"name": "Villa B", "capacity": 4},
        }

    def test_checker_requires_villas_available_for_every_night(self):
        calendar = {
            "days": {
                "2099-01-01": {
                    "available_villa_ids": ["villa-a", "villa-b"],
                    "booked_villa_ids": [],
                },
                "2099-01-02": {
                    "available_villa_ids": ["villa-a"],
                    "booked_villa_ids": ["villa-b"],
                },
            }
        }
        with patch("booking.public_booking_calendar_availability", return_value=calendar) as check, \
             patch("admin.get_villa_catalog_map", return_value=self.catalog), \
             patch("admin.service_client"):
            result = manual_booking_airbnb_availability(
                check_in_date=date(2099, 1, 1),
                check_out_date=date(2099, 1, 3),
                guest_count=2,
                context={},
            )

        self.assertEqual(check.call_args.kwargs["end_date"], date(2099, 1, 2))
        self.assertTrue(result["available"])
        self.assertEqual(result["available_villa_ids"], ["villa-a"])
        self.assertEqual(result["total_available_capacity"], 2)
        self.assertEqual(result["villas"][1]["reason"], "Booked for part of the stay")

    def test_checker_reports_maintenance_date_as_unavailable(self):
        calendar = {
            "days": {
                "2099-01-01": {
                    "available_villa_ids": ["villa-b"],
                    "booked_villa_ids": [],
                },
            }
        }
        with patch("booking.public_booking_calendar_availability", return_value=calendar), \
             patch("admin.get_villa_catalog_map", return_value=self.catalog), \
             patch("admin.service_client"):
            result = manual_booking_airbnb_availability(
                check_in_date=date(2099, 1, 1),
                check_out_date=date(2099, 1, 2),
                guest_count=5,
                context={},
            )

        self.assertFalse(result["available"])
        self.assertEqual(result["villas"][0]["reason"], "Maintenance or unavailable")

    def test_checker_identifies_internal_airbnb_holds_and_stays(self):
        calendar = {
            "days": {
                "2099-01-01": {
                    "available_villa_ids": ["villa-b"],
                    "booked_villa_ids": [],
                    "airbnb_blocked_villa_ids": ["villa-a"],
                    "unavailable_villa_ids": [],
                },
            }
        }
        with patch("booking.public_booking_calendar_availability", return_value=calendar), \
             patch("admin.get_villa_catalog_map", return_value=self.catalog), \
             patch("admin.service_client"):
            result = manual_booking_airbnb_availability(
                check_in_date=date(2099, 1, 1),
                check_out_date=date(2099, 1, 2),
                guest_count=1,
                context={},
            )

        self.assertEqual(result["villas"][0]["reason"], "Airbnb hold or stay for part of the stay")

    def test_checker_rejects_empty_stay(self):
        with self.assertRaises(HTTPException) as caught:
            manual_booking_airbnb_availability(
                check_in_date=date(2099, 1, 1),
                check_out_date=date(2099, 1, 1),
                guest_count=1,
                context={},
            )
        self.assertEqual(caught.exception.status_code, 422)

    def test_airbnb_stay_list_loads_villa_names_without_maintenance_summary(self):
        class CatalogQuery:
            def select(self, columns):
                self.columns = columns
                return self

            def execute(self):
                return type("Response", (), {
                    "data": [{"id": "villa-1", "title": "Villa One"}]
                })()

        class Client:
            def table(self, name):
                self.table_name = name
                return CatalogQuery()

        stays = [{
            "id": "stay-1",
            "check_in_date": "2099-01-01",
            "check_out_date": "2099-01-02",
            "guest_count": 2,
            "villa_ids": ["villa-1"],
            "status": "confirmed",
            "created_at": "2098-12-01T00:00:00+00:00",
        }]
        with patch("admin.service_client", return_value=Client()), \
             patch("booking._active_airbnb_stays", return_value=stays), \
             patch("admin.villa_business_today", return_value=date(2098, 12, 31)):
            result = list_manual_airbnb_stays(context={})

        self.assertEqual(result["data"][0]["villa_names"], ["Villa One"])

    def test_manual_checkout_only_accepts_qrph(self):
        payload = {
            "first_name": "Guest",
            "last_name": "One",
            "email": "guest@example.com",
            "phone": "09123456789",
            "villa_ids": ["villa-a"],
            "check_in_date": date(2099, 1, 1),
            "guest_count": 1,
        }
        self.assertEqual(ManualBookingRequest(**payload).payment_method, "qrph")
        with self.assertRaises(ValidationError):
            ManualBookingRequest(**payload, payment_method="gcash")
