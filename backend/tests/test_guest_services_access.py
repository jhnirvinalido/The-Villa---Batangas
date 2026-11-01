import unittest
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parents[1]))

import admin
from admin import (
    PaymentApprovalReviewRequest,
    StaffAccessReviewRequest,
    get_payment_approval_request,
    review_front_desk_payment_approval_request,
    review_staff_access_request,
)
from staff import (
    StaffPaymentApprovalRequest,
    GuestServicesWalkInRequest,
    StaffAccessRequest,
    require_front_desk_payment_access,
    require_walk_in_access,
    request_guest_services_payment_approval,
    request_staff_access,
)


class GuestServicesAccessTests(unittest.TestCase):
    def test_staff_account_schema_accepts_front_desk_role(self):
        request = admin.StaffCreateRequest(
            fullName="Front Desk User",
            email="desk@example.com",
            username="desk.user",
            role="front_desk",
            department="Guest Services",
            position="Front Desk / Operations",
        )

        self.assertEqual(request.role, "front_desk")

    def test_front_desk_role_schema_errors_are_identified_for_migration_guidance(self):
        error = Exception(
            'new row violates check constraint "staff_accounts_role_check": role front_desk'
        )
        self.assertTrue(admin.is_front_desk_role_schema_error(error))
        self.assertFalse(
            admin.is_front_desk_role_schema_error(
                Exception("A staff account already uses this email.")
            )
        )

    def test_legacy_walk_in_permission_does_not_replace_front_desk_role(self):
        context = {
            "account": {
                "department": "Housekeeping",
                "can_create_walk_in_bookings": True,
            }
        }

        with self.assertRaises(HTTPException) as raised:
            require_walk_in_access(context)

        self.assertEqual(raised.exception.status_code, 403)

    def test_unapproved_staff_cannot_create_walk_ins(self):
        context = {"account": {"department": "Housekeeping"}}

        with self.assertRaises(HTTPException) as raised:
            require_walk_in_access(context)

        self.assertEqual(raised.exception.status_code, 403)

    def test_payment_access_is_independent_from_walk_in_permission(self):
        context = {
            "account": {
                "can_create_walk_in_bookings": True,
                "can_process_front_desk_payments": False,
            }
        }

        with self.assertRaises(HTTPException) as raised:
            require_front_desk_payment_access(context)

        self.assertEqual(raised.exception.status_code, 403)

    def test_legacy_payment_permission_does_not_replace_front_desk_role(self):
        context = {
            "account": {
                "department": "Housekeeping",
                "can_process_front_desk_payments": True,
            }
        }

        with self.assertRaises(HTTPException) as raised:
            require_front_desk_payment_access(context)

        self.assertEqual(raised.exception.status_code, 403)

    def test_front_desk_role_can_access_operations_without_staff_grant(self):
        request = object()
        account = {"id": "front-desk-1", "role": "front_desk"}
        with (
            patch("admin.bearer_token", return_value="token"),
            patch("admin.validate_portal_access_token", return_value=account),
            patch("admin.save_session", return_value={}),
        ):
            context = admin.require_front_desk_access(request)

        self.assertEqual(context["account"]["role"], "front_desk")

    def test_front_desk_bootstrap_omits_authentication_identifiers(self):
        context = {"account": {"id": "front-desk-1", "role": "front_desk"}}
        with patch("admin.bootstrap", return_value={"data": {
            "profile": {
                "id": "front-desk-1",
                "name": "On-site",
                "portalRole": "front_desk",
                "authUserId": "auth-secret",
            },
            "staff": [{
                "id": "staff-1",
                "name": "Housekeeper",
                "department": "Housekeeping",
                "authUserId": "auth-secret",
                "email": "housekeeping@example.com",
            }],
            "bookings": [],
            "tasks": [],
            "notifications": [],
            "paymentTransactions": [],
            "snapshotErrors": [],
        }}):
            payload = admin.front_desk_bootstrap(context)

        self.assertNotIn("authUserId", payload["data"]["profile"])
        self.assertNotIn("authUserId", payload["data"]["staff"][0])
        self.assertNotIn("email", payload["data"]["staff"][0])

    def test_front_desk_bootstrap_keeps_failed_snapshots_distinct_from_empty_results(self):
        with patch("admin.bootstrap", return_value={"data": {
            "profile": None,
            "staff": None,
            "tasks": None,
            "bookings": None,
            "bookingError": "Bookings unavailable",
            "snapshotErrors": ["staff", "tasks"],
        }}):
            payload = admin.front_desk_bootstrap({"account": {"role": "front_desk"}})["data"]

        self.assertIsNone(payload["staff"])
        self.assertIsNone(payload["tasks"])
        self.assertIsNone(payload["bookings"])
        self.assertEqual(payload["bookingError"], "Bookings unavailable")

    def test_front_desk_api_rejects_staff_even_with_legacy_payment_grant(self):
        request = object()
        authorized_staff = {
            "id": "staff-1",
            "role": "staff",
            "department": "Housekeeping",
            "can_process_front_desk_payments": True,
        }
        with (
            patch("admin.bearer_token", return_value="token"),
            patch("admin.validate_portal_access_token", return_value=authorized_staff),
            patch("admin.save_session", return_value={}),
            self.assertRaises(HTTPException) as raised,
        ):
            admin.require_front_desk_access(request)
        self.assertEqual(raised.exception.status_code, 403)

    def test_staff_access_request_is_replaced_by_directory_role_assignment(self):
        with self.assertRaises(HTTPException) as raised:
            request_staff_access(
                StaffAccessRequest(area="walk_in"),
                {"account": {"id": "staff-1", "role": "staff"}},
            )

        self.assertEqual(raised.exception.status_code, 403)

    def test_access_review_is_replaced_by_directory_role_assignment(self):
        with self.assertRaises(HTTPException) as raised:
            review_staff_access_request(
                UUID("12345678-1234-5678-1234-567812345678"),
                StaffAccessReviewRequest(area="walk_in", action="approve"),
                {"account": {"id": "admin-1"}},
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_walk_in_request_supports_cash_and_qrph(self):
        base = {
            "first_name": "Ana",
            "last_name": "Guest",
            "email": "ana@example.com",
            "phone": "09123456789",
            "villa_ids": ["villa-1"],
            "check_in_date": "2026-11-02",
            "guest_count": 1,
        }

        self.assertEqual(
            GuestServicesWalkInRequest(**base, payment_method="cash").payment_method,
            "cash",
        )
        self.assertEqual(
            GuestServicesWalkInRequest(**base, payment_method="qrph").payment_method,
            "qrph",
        )

    def test_staff_cannot_settle_without_a_payment_approval_request(self):
        with self.assertRaises(HTTPException) as raised:
            get_payment_approval_request(
                approval_request_id=None,
                booking={"id": "booking-1"},
                context={"account": {"id": "staff-1", "role": "staff"}},
                payment_method="cash",
                payment_timing="check_in",
                amount=Decimal("100.00"),
            )

        self.assertEqual(raised.exception.status_code, 403)

    def test_payment_approval_is_bound_to_staff_booking_method_and_amount(self):
        request_id = UUID("12345678-1234-5678-1234-567812345678")
        request_row = {
            "id": str(request_id),
            "booking_id": "booking-1",
            "requested_by_staff_id": "staff-1",
            "payment_method": "cash",
            "payment_timing": "check_in",
            "amount": "100.00",
            "status": "approved",
        }
        with (
            patch("admin.service_client", return_value=MagicMock()),
            patch("admin.rows", return_value=[request_row]),
        ):
            result = get_payment_approval_request(
                approval_request_id=request_id,
                booking={"id": "booking-1"},
                context={"account": {"id": "staff-1", "role": "staff"}},
                payment_method="cash",
                payment_timing="check_in",
                amount=Decimal("100.00"),
            )

        self.assertEqual(result, request_row)

        with (
            patch("admin.service_client", return_value=MagicMock()),
            patch("admin.rows", return_value=[request_row]),
            self.assertRaises(HTTPException) as raised,
        ):
            get_payment_approval_request(
                approval_request_id=request_id,
                booking={"id": "booking-1"},
                context={"account": {"id": "other-staff", "role": "staff"}},
                payment_method="cash",
                payment_timing="check_in",
                amount=Decimal("100.00"),
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_staff_payment_request_uses_server_balance_and_notifies_admins(self):
        booking_id = UUID("12345678-1234-5678-1234-567812345678")
        request_id = "87654321-4321-8765-4321-876543218765"
        inserted = {
            "id": request_id,
            "booking_id": str(booking_id),
            "requested_by_staff_id": "staff-1",
            "payment_method": "cash",
            "payment_timing": "check_in",
            "amount": 125.0,
            "status": "pending",
        }
        client = MagicMock()
        with (
            patch("staff.service_client", return_value=client),
            patch("staff.rows", side_effect=[[], [inserted]]),
            patch("admin.fetch_booking", return_value={
                "id": str(booking_id),
                "booking_code": "TV-1",
                "booking_status": "Confirmed",
                "payment_choice": "half",
                "amount_paid": 125.0,
                "balance_amount": 125.0,
            }),
            patch("admin.booking_initial_payment_verified", return_value=True),
            patch("admin.validate_payment_timing_for_booking", return_value="check_in"),
            patch("admin.notify_admins") as notify_admins,
        ):
            result = request_guest_services_payment_approval(
                booking_id,
                StaffPaymentApprovalRequest(payment_method="cash", payment_timing="check_in"),
                {"account": {"id": "staff-1", "full_name": "On-site Staff", "role": "staff"}},
            )

        payload = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["amount"], 125.0)
        self.assertEqual(payload["payment_timing"], "check_in")
        self.assertEqual(result["data"]["id"], request_id)
        notify_admins.assert_called_once()

    def test_admin_can_review_a_pending_payment_request_only_once(self):
        request_id = UUID("12345678-1234-5678-1234-567812345678")
        pending = {
            "id": str(request_id),
            "booking_id": "booking-1",
            "requested_by_staff_id": "staff-1",
            "payment_method": "cash",
            "payment_timing": "check_in",
            "amount": "100.00",
            "status": "pending",
        }
        approved = {**pending, "status": "approved", "reviewed_by_staff_id": "admin-1"}
        client = MagicMock()
        with (
            patch("admin.service_client", return_value=client),
            patch("admin.rows", side_effect=[[pending], [approved]]),
            patch("admin.fetch_booking", return_value={
                "id": "booking-1",
                "booking_status": "Confirmed",
                "balance_amount": "100.00",
            }),
            patch("admin.validate_payment_timing_for_booking"),
            patch("admin.create_notification"),
        ):
            result = review_front_desk_payment_approval_request(
                request_id,
                PaymentApprovalReviewRequest(action="approve"),
                {"account": {"id": "admin-1"}},
            )

        self.assertEqual(
            client.table.return_value.update.call_args.args[0]["status"],
            "approved",
        )
        self.assertEqual(result["data"]["status"], "approved")

    def test_admin_front_desk_walk_in_delegates_to_shared_validated_flow(self):
        payload = {
            "first_name": "Ana",
            "last_name": "Guest",
            "email": "ana@example.com",
            "phone": "09123456789",
            "villa_ids": ["villa-1"],
            "check_in_date": "2026-11-02",
            "guest_count": 1,
            "payment_choice": "full",
            "payment_method": "cash",
            "cash_tendered": "1000",
        }
        request = object()
        context = {"account": {"id": "admin-1", "role": "admin"}}
        with patch(
            "staff.create_guest_services_walk_in",
            return_value={"message": "saved"},
        ) as create:
            result = admin.admin_create_front_desk_walk_in(payload, request, context)

        data, passed_request, passed_context = create.call_args.args
        self.assertIsInstance(data, GuestServicesWalkInRequest)
        self.assertEqual(data.payment_method, "cash")
        self.assertIs(passed_request, request)
        self.assertIs(passed_context, context)
        self.assertEqual(result, {"message": "saved"})


if __name__ == "__main__":
    unittest.main()
