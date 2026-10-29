"""Authenticated SSE invalidations, not database rows or credentials.

API writes publish immediately. A server-only Supabase Realtime subscription
covers background workers, other API processes and external database changes.
Browsers re-fetch through existing authorized endpoints after a change signal.
"""
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
import json
import logging
import os
import ssl
import time
from uuid import uuid4

import certifi

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("thevilla.live_updates")
router = APIRouter(prefix="/live", tags=["Live Updates"])
PUBLIC = frozenset({"catalog", "availability", "reviews"})
STAFF = frozenset({"tasks", "notifications", "messages", "staff", "accounts", "catalog"})
BOOKING = frozenset({"bookings", "payments"})
TABLES = {
    "villa_catalog": {"catalog", "availability"},
    "bookings": {"bookings", "payments", "availability"},
    "booking_payments": {"payments", "bookings", "availability"},
    "front_desk_payments": {"payments", "bookings"},
    "front_desk_payment_items": {"payments"},
    "front_desk_payment_intents": {"payments"},
    "booking_workflow_events": {"bookings", "payments"},
    "public_booking_checkouts": {"bookings", "payments", "availability"},
    "manual_booking_checkouts": {"bookings", "payments", "availability"},
    "admin_tasks": {"tasks"},
    "admin_notifications": {"notifications"},
    "staff_messages": {"messages"},
    "staff_accounts": {"staff", "accounts"},
    "profiles": {"accounts"},
    "staff_settings": {"accounts"},
    "admin_settings": {"accounts"},
    "guest_feedback": {"feedback", "reviews"},
    "companion_feedback": {"feedback"},
    "feedback_recommendation_reports": {"feedback"},
    "feedback_analysis_jobs": {"feedback"},
    "feedback_invitation_outbox": {"feedback"},
    "staff_assignment_email_outbox": {"notifications"},
}
WORKER_TOPICS = {
    "bookings": {"assignments", "feedback", "analysis"},
    "booking_payments": {"assignments", "feedback"},
    "front_desk_payments": {"feedback"},
    "staff_accounts": {"assignments", "emails", "maintenance"},
    "admin_tasks": {"assignments", "emails", "maintenance"},
    "guest_feedback": {"analysis"},
    "staff_assignment_email_outbox": {"emails"},
}


@dataclass(eq=False)
class Subscriber:
    role: str
    account_id: str = ""
    booking_id: str = ""
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))


class LiveHub:
    def __init__(self):
        self.loop = None
        self.subscribers = set()
        self.worker_events = {}
        self.database_connected = False
        self.revision = 0

    def attach(self):
        self.loop = asyncio.get_running_loop()

    def publish(self, domains, staff_ids=None, recipient_ids=None, booking_ids=None):
        if not self.loop or self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(
            self._publish,
            set(domains),
            staff_ids,
            recipient_ids,
            booking_ids,
        )

    def _publish(self, domains, staff_ids=None, recipient_ids=None, booking_ids=None):
        self.revision += 1
        for sub in tuple(self.subscribers):
            if sub.role == "public":
                audience_domains = PUBLIC
            elif sub.role == "staff":
                audience_domains = STAFF
            elif sub.role == "booking":
                audience_domains = BOOKING
            else:
                audience_domains = set().union(*TABLES.values())
            allowed = domains & audience_domains
            if not allowed:
                continue
            if sub.role == "booking" and (
                not booking_ids or sub.booking_id not in booking_ids
            ):
                continue
            if sub.role == "staff" and staff_ids is not None and sub.account_id not in staff_ids:
                continue
            if recipient_ids is not None and sub.role != "public" and sub.account_id not in recipient_ids:
                continue
            # Merge invalidations under backpressure; no unbounded per-client queue.
            if sub.queue.full():
                previous = sub.queue.get_nowait()
                allowed.update(previous["domains"])
            sub.queue.put_nowait({"domains": sorted(allowed), "revision": self.revision})

    def wake(self, topics):
        if not self.loop or self.loop.is_closed():
            return
        def signal():
            for topic in topics:
                self.worker_events.setdefault(topic, asyncio.Event()).set()
        self.loop.call_soon_threadsafe(signal)

    async def wait(self, topic, fallback_seconds):
        event = self.worker_events.setdefault(topic, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), fallback_seconds)
        except asyncio.TimeoutError:
            pass
        event.clear()


hub = LiveHub()


def emit_table(table, record=None, old=None):
    if table not in TABLES:
        return
    record, old = record or {}, old or {}
    staff_ids = None
    recipient_ids = None
    if table == "admin_tasks":
        found = {str(row["assigned_staff_id"]) for row in (record, old) if row.get("assigned_staff_id")}
        staff_ids = found or None
    elif table == "admin_notifications":
        found = {str(row["recipient_staff_account_id"]) for row in (record, old) if row.get("recipient_staff_account_id")}
        recipient_ids = found or None
    elif table == "staff_messages":
        found = {str(row["staff_account_id"]) for row in (record, old) if row.get("staff_account_id")}
        staff_ids = found or None
    elif table in {"staff_accounts", "staff_settings"}:
        key = "id" if table == "staff_accounts" else "staff_account_id"
        found = {str(row[key]) for row in (record, old) if row.get(key)}
        staff_ids = found or None
    booking_ids = {
        str(row.get("id") if table == "bookings" else row.get("booking_id") or row.get("id"))
        for row in (record, old)
        if row.get("id") or row.get("booking_id")
    }
    hub.publish(
        TABLES[table],
        staff_ids,
        recipient_ids,
        booking_ids if booking_ids else None,
    )
    if table == "admin_tasks" and any(row.get("source") == "manual-maintenance-request" for row in (record, old)):
        hub.publish({"catalog", "availability"})
    hub.wake(WORKER_TOPICS.get(table, set()))


def mutation_tables(path):
    """Only business mutations; login, session reads and SSE never invalidate."""
    if path.startswith("/admin/maintenance"):
        return ["admin_tasks"]
    if path.startswith("/admin/tasks") or path.startswith("/staff/tasks"):
        return ["admin_tasks", "admin_notifications"]
    if "/notifications" in path:
        return ["admin_notifications"]
    if "/messages" in path:
        return ["staff_messages", "admin_notifications"]
    if path.startswith("/villa-catalog"):
        return ["villa_catalog"]
    if path.startswith("/public-bookings/") and "/feedback/" in path:
        # Companion handler publishes only a newly accepted internal response.
        return []
    if "guest-feedback" in path or (path.startswith("/public-bookings/") and path.endswith("/feedback")):
        return ["guest_feedback"]
    if path.startswith((
        "/front-desk/",
        "/public-bookings/",
        "/bookings/",
        "/admin/bookings",
        "/admin/manual-bookings",
    )):
        return ["bookings", "booking_payments"]
    if path.startswith(("/admin/staff", "/admin/profile", "/staff/profile", "/staff/settings", "/admin/settings")):
        return ["staff_accounts"]
    return []


async def _stream(request, role, account_id="", booking_id=""):
    hub.attach()
    subscriber = Subscriber(role, account_id, booking_id)
    hub.subscribers.add(subscriber)
    started = time.monotonic()
    try:
        yield "event: ready\ndata: " + json.dumps({"databaseLive": hub.database_connected}) + "\n\n"
        # Bounded streams re-authenticate on reconnect, including changed roles.
        while time.monotonic() - started < 120:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(subscriber.queue.get(), timeout=15)
                yield "event: change\ndata: " + json.dumps(event) + "\n\n"
                if "accounts" in event["domains"]:
                    break
            except asyncio.TimeoutError:
                yield "event: health\ndata: " + json.dumps({"databaseLive": hub.database_connected}) + "\n\n"
    finally:
        hub.subscribers.discard(subscriber)


def _response(request, role, account_id="", booking_id=""):
    return StreamingResponse(
        _stream(request, role, account_id, booking_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/public")
async def public_stream(request: Request):
    return _response(request, "public")


@router.get("/portal")
async def portal_stream(request: Request):
    from staff_admin_auth import validate_portal_access_token
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not auth[7:].strip():
        raise HTTPException(status_code=401, detail="A staff or administrator session is required.")
    # Blocking auth/database reads must never block the streaming event loop.
    account = await asyncio.to_thread(validate_portal_access_token, auth[7:].strip())
    return _response(request, str(account["role"]).lower(), str(account["id"]))


@router.get("/booking/{booking_id}")
async def booking_stream(booking_id: str, request: Request):
    from booking import _require_booking_token, _validate_manual_return_token

    booking_token = request.headers.get("X-Booking-Token", "").strip()
    manual_token = request.headers.get("X-Manual-Booking-Token", "").strip()
    if booking_token:
        await asyncio.to_thread(_require_booking_token, booking_id, booking_token)
    elif manual_token:
        await asyncio.to_thread(_validate_manual_return_token, booking_id, manual_token)
    else:
        raise HTTPException(
            status_code=401,
            detail="A secure booking capability is required.",
        )
    return _response(request, "booking", booking_id=booking_id)


def configure_realtime_certificates():
    """Give WebSocket TLS the CA bundle already used by our HTTP clients.

    Python.org macOS installs may lack a working OpenSSL root bundle. Respect
    an explicitly configured bundle, including private corporate CA chains.
    """
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())


async def database_listener():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        logger.warning("Database live updates need Supabase backend configuration.")
        return
    configure_realtime_certificates()
    supabase = await asyncio.to_thread(import_module, "supabase")
    while True:
        client = None
        try:
            client = await supabase.acreate_client(url, key)
            # Subscribe only to the server service-role connection; never expose rows.
            channel = client.channel("villa-server-" + uuid4().hex)
            channel.on_postgres_changes("*", schema="public", callback=handle_database_change)
            def status(state, error=None):
                hub.database_connected = str(getattr(state, "value", state)).upper() == "SUBSCRIBED"
                if hub.database_connected:
                    hub.publish(set().union(*TABLES.values()))
            await channel.subscribe(status)
            while True:
                await asyncio.sleep(30)
                # The SDK reconnects interrupted sockets and invokes status changes.
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if isinstance(error, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(error):
                logger.warning("Database live TLS verification failed; check SSL_CERT_FILE and the trusted CA bundle. Retrying.")
            else:
                logger.warning("Database live connection unavailable; retrying. Check connectivity, Supabase configuration and realtime publication.")
        finally:
            hub.database_connected = False
            if client:
                with suppress(Exception):
                    await client.remove_all_channels()
                    await client.realtime.close()
        await asyncio.sleep(5)


def handle_database_change(payload):
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    emit_table(data.get("table"), data.get("record"), data.get("old_record"))
