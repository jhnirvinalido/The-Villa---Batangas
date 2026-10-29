"""Durable staff assignment email, independently retried from booking success.

The existing SMTP configuration is reused. No email is sent from a guest-facing
request or browser. SQL leases deduplicate delivery across background workers.
"""
import logging
import smtplib
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode, urlparse

from email_validator import validate_email, EmailNotValidError

logger = logging.getLogger("thevilla.staff_assignment_email")


def _first(response):
    data = getattr(response, "data", None)
    return data[0] if isinstance(data, list) and data else None


def build_assignment_message(staff, task, frontend_url, sender, sender_name, job_id):
    recipient = validate_email(str(staff.get("personal_email") or ""), check_deliverability=False).normalized
    origin = frontend_url.rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("A valid frontend URL is required")
    link = f"{origin}/staff?{urlencode({'task':str(task['id'])})}"
    name = str(staff.get("full_name") or "Team member")
    title = str(task.get("title") or "New assignment")
    villa = str(task.get("villa_name") or "See assignment details")
    due = f"{task.get('due_date') or 'See schedule'} {task.get('due_time') or ''} (Asia/Manila)".strip()
    reference = str(task.get("booking_code") or "Not linked to a booking")
    msg = EmailMessage()
    msg["Subject"] = "The Villa — New Staff Assignment"
    msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
    msg["To"] = recipient
    domain = sender.rsplit("@", 1)[-1]
    msg["Message-ID"] = f"<villa-assignment-{job_id}@{domain}>"
    msg.set_content(
        f"Hello {name},\n\nYou have a new assignment at The Villa.\n\n"
        f"Assignment: {title}\nVilla: {villa}\nBooking reference: {reference}\nDue: {due}\n\n"
        f"Open your staff portal to review the checklist and current schedule:\n{link}\n\n"
        "Sign in with your staff account. Assignment details may be updated by the administrator.\n\nThe Villa Management"
    )
    # Guest contact details, access tokens and private notes never enter this email.
    msg.add_alternative(f'''<!doctype html><html><body style="margin:0;background:#fbfaf8;color:#292522;font-family:Arial,sans-serif;padding:24px">
    <div style="max-width:560px;margin:auto;background:white;border:1px solid #e5ded7;border-radius:16px;padding:32px">
    <p style="color:#8b5e3c;font-size:12px;letter-spacing:2px">THE VILLA · STAFF</p>
    <h1 style="font-size:25px">You have a new assignment</h1><p>Hello {escape(name)},</p>
    <h2 style="font-size:19px">{escape(title)}</h2>
    <p><strong>Villa:</strong> {escape(villa)}<br><strong>Booking:</strong> {escape(reference)}<br><strong>Due:</strong> {escape(due)}</p>
    <p style="margin:28px 0"><a href="{escape(link, quote=True)}" style="background:#8b5e3c;color:white;padding:14px 22px;border-radius:8px;text-decoration:none;display:inline-block">View assignment</a></p>
    <p style="font-size:13px;color:#756e68">Sign in to review your checklist and current schedule. Contact your administrator if you cannot complete this assignment.</p></div></body></html>''', subtype="html")
    return msg


def _finish(client, job, status, error=None):
    return client.rpc("finish_staff_assignment_email", {
        "p_id": job["id"], "p_lease": job["lease_token"], "p_status": status, "p_error": error,
    }).execute().data


def deliver_assignment_email(client, job, config):
    try:
        staff = _first(client.table("staff_accounts").select("id,full_name,personal_email,role,is_active,account_status")
                       .eq("id", job["recipient_staff_account_id"]).limit(1).execute())
        task = _first(client.table("admin_tasks").select("id,title,villa_name,booking_code,due_date,due_time,status,assigned_staff_id,source,status_history")
                      .eq("id", job["task_id"]).limit(1).execute())
    except Exception:
        _finish(client, job, "retry", "Assignment data could not be loaded")
        return "retry"
    if (not staff or not task or staff.get("is_active") is not True
            or str(staff.get("role") or "").lower() != "staff"
            or str(staff.get("account_status") or "").lower() != "active"
            or str(task.get("assigned_staff_id")) != str(staff["id"])
            or task.get("status") not in {"Pending", "In Progress", "Pending Review"}):
        _finish(client, job, "suppressed", "Task no longer assigned to an eligible active staff member")
        return "suppressed"
    if task.get("source") == "manual-maintenance-request" and any(
        (event.get("maintenance") or {}).get("onCall") for event in task.get("status_history") or [] if isinstance(event, dict)
    ):
        _finish(client, job, "suppressed", "On-call maintenance sends its own availability request")
        return "suppressed"
    try:
        message = build_assignment_message(staff, task, config.FRONTEND_URL, config.SMTP_FROM, config.SMTP_FROM_NAME, job["id"])
    except (EmailNotValidError, ValueError):
        _finish(client, job, "failed", "Invalid recipient address or frontend URL")
        return "failed"
    sending = False
    accepted = False

    def mark_sending():
        nonlocal sending
        sending = True

    def record_acceptance(refused):
        nonlocal accepted
        if refused:
            return
        accepted = True
        if not _finish(client, job, "accepted"):
            raise RuntimeError("Email acceptance could not be recorded")

    try:
        import booking
        refused = booking._send_email_message(
            message,
            host=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USER,
            password=config.SMTP_PASSWORD,
            on_sending=mark_sending,
            on_accepted=record_acceptance,
        )
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
        return "accepted"
    except smtplib.SMTPRecipientsRefused:
        if accepted:
            return "accepted"
        _finish(client, job, "failed", "SMTP rejected recipient")
        return "failed"
    except smtplib.SMTPDataError:
        if accepted:
            return "accepted"
        _finish(client, job, "retry", "SMTP rejected email data")
        return "retry"
    except Exception:
        # Never include addresses, SMTP responses or credentials in logs/outbox.
        if accepted:
            logger.warning("Assignment email accepted; completion needs reconciliation for job %s", job["id"])
            return "accepted"
        state = "uncertain" if sending else "retry"
        _finish(client, job, state, "SMTP submission outcome uncertain" if sending else "SMTP connection or authentication unavailable")
        return state


def process_assignment_emails(client=None, config=None):
    if config is None:
        import booking as config
    if not config._smtp_configured():
        return []  # Preserve queued work until SMTP is configured.
    client = client if client is not None else config._service()
    client.rpc("queue_staff_assignment_emails", {}).execute()
    response = client.rpc("claim_staff_assignment_emails", {"p_limit": 10}).execute()
    outcomes = []
    for job in response.data or []:
        try:
            outcomes.append(deliver_assignment_email(client, job, config))
        except Exception:
            logger.warning("Assignment email job %s could not complete; inspect its delivery state", job.get("id"))
            # Conservatively preserve unknown outcomes; never blindly resend a
            # message whose SMTP submission might already have succeeded.
            try:
                _finish(client, job, "uncertain", "Delivery outcome needs review")
            except Exception:
                pass
    return outcomes
