from datetime import date
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from admin import (
    ManualBookingRequest,
    AirbnbStayHoldRequest,
    AirbnbStayConfirmRequest,
    confirm_manual_airbnb_stay,
    create_manual_airbnb_stay_hold,
    list_manual_airbnb_stays,
    manual_booking_airbnb_availability,
)


class AirbnbAvailabilityTests(TestCase):
    def setUp(self):
        self.catalog = {
            "villa-a": {"name": "Villa A", "capacity": 2, "price": 2500, "image": "/villa-a.jpg"},
            "villa-b": {"name": "Villa B", "capacity": 4, "price": 4000, "image": "/villa-b.jpg"},
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
        class Query:
            def __init__(self, data):
                self.data = data

            def select(self, columns):
                self.columns = columns
                return self

            def eq(self, *_):
                return self

            def execute(self):
                return type("Response", (), {"data": self.data})()

        class Client:
            def table(self, name):
                data = [{"id": "villa-1", "title": "Villa One"}] if name == "villa_catalog" else []
                return Query(data)

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

    def test_confirmed_airbnb_hold_creates_external_booking_and_assigns_housekeeping(self):
        stay_id = "11111111-1111-4111-8111-111111111111"
        actor_id = "22222222-2222-4222-8222-222222222222"
        stay = {
            "id": stay_id,
            "check_in_date": "2099-01-01",
            "check_out_date": "2099-01-03",
            "guest_count": 2,
            "villa_ids": ["villa-a"],
            "status": "held",
            "expires_at": "2099-01-01T12:00:00+00:00",
        }

        class Query:
            def select(self, *_):
                return self

            def eq(self, *_):
                return self

            def limit(self, *_):
                return self

            def execute(self):
                return type("Response", (), {"data": [stay]})()

        class Client:
            def table(self, _):
                return Query()

            def rpc(self, name, params):
                self.rpc_name = name
                self.rpc_params = params
                return type(
                    "RpcQuery",
                    (),
                    {"execute": lambda _self: type("Response", (), {"data": params["p_booking"]})()},
                )()

        client = Client()
        request = AirbnbStayConfirmRequest(guest_name="Airbnb Guest", guest_email="", guest_phone="")
        with patch("admin.service_client", return_value=client), \
             patch("admin.get_villa_catalog_map", return_value=self.catalog), \
             patch("booking._villa_operational", return_value=True), \
             patch("booking_assignments.schedule_prearrival_assignment", return_value={"status": "assigned"}) as assign:
            result = confirm_manual_airbnb_stay(
                stay_id,
                request,
                {"account": {"id": actor_id}},
            )

        self.assertEqual(client.rpc_name, "confirm_airbnb_stay_booking")
        booking = client.rpc_params["p_booking"]
        self.assertEqual(booking["customer_name"], "Airbnb Guest")
        self.assertEqual(booking["booking_channel"], "airbnb")
        self.assertEqual(booking["payment_status"], "External")
        self.assertEqual(booking["amount_paid"], 0)
        self.assertEqual(booking["balance_amount"], 0)
        self.assertEqual(booking["total_amount"], 5000)
        assign.assert_called_once_with(booking, client)
        self.assertEqual(result["assignment"]["status"], "assigned")

    def test_airbnb_confirmation_requires_guest_name_without_numeric_characters(self):
        with self.assertRaises(ValidationError):
            AirbnbStayConfirmRequest(guest_name="Guest 123")

    def test_create_hold_saves_a_valid_selected_villa(self):
        class RpcQuery:
            def execute(self):
                return type("Response", (), {"data": {}})()

        class Client:
            def rpc(self, name, params):
                self.rpc_name = name
                self.rpc_params = params
                return RpcQuery()

        client = Client()
        data = AirbnbStayHoldRequest(
            check_in_date=date(2099, 1, 1),
            check_out_date=date(2099, 1, 2),
            guest_count=1,
            villa_ids=["villa-a"],
        )
        availability = {
            "villas": [{
                "villa_id": "villa-a",
                "villa_name": "Villa A",
                "capacity": 2,
                "available": True,
            }]
        }
        with patch("admin.villa_business_today", return_value=date(2098, 12, 31)), \
             patch("admin.service_client", return_value=client), \
             patch("admin.manual_booking_airbnb_availability", return_value=availability):
            result = create_manual_airbnb_stay_hold(
                data,
                {"account": {"id": "staff-id"}},
            )

        self.assertEqual(client.rpc_name, "create_airbnb_stay_hold")
        self.assertEqual(client.rpc_params["p_villa_ids"], ["villa-a"])
        self.assertEqual(result["data"]["villa_names"], ["Villa A"])

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
