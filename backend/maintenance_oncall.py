"""Durable on-call dispatch and scoped technician replies on existing task records.

Compare-and-set task revisions arbitrate replies, dispatches and worker leases.
A notification acknowledgement never establishes technician availability.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import smtplib
import ssl
import time as clock_time
import threading
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode, urlparse
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

import maintenance as domain
from admin import TASK_SELECT, SUPABASE_SERVICE_ROLE_KEY, rows, service_client, require_admin
from live_updates import emit_table

logger = logging.getLogger('thevilla.maintenance.oncall')
public_router = APIRouter(prefix='/maintenance-response', tags=['Maintenance response'])
_reply_requests = {}
_reply_lock = threading.Lock()


def limit_replies(request: Request):
    # Do not trust forwarded addresses supplied by a caller.
    key = request.client.host if request.client else 'unknown'
    now = clock_time.monotonic()
    with _reply_lock:
        for address, (_, started) in list(_reply_requests.items()):
            if now - started > 60:
                _reply_requests.pop(address, None)
        count, started = _reply_requests.get(key, (0, now))
        if count >= 60 or (key not in _reply_requests and len(_reply_requests) >= 10000):
            raise HTTPException(status_code=429, detail='Too many requests. Please try again in a minute.')
        _reply_requests[key] = (count + 1, started)


public_router.dependencies.append(Depends(limit_replies))


def utcnow(): return datetime.now(timezone.utc)
def stamp(value): return value.astimezone(timezone.utc).isoformat()
def parse(value): return datetime.fromisoformat(str(value).replace('Z', '+00:00')) if value else None


def booked_periods(client):
    from booking import _availability_blocks_booking

    periods = []
    offset = 0
    try:
        while True:
            batch = rows(client.table('bookings')
                         .select('id,villa_id,villa_ids,check_in_date,check_out_date,check_in_time,booking_status')
                         .order('id').range(offset, offset + 499).execute())
            for booking in batch:
                if not _availability_blocks_booking(booking) or not booking.get('check_in_date'):
                    continue
                villa_ids = booking.get('villa_ids') or [booking.get('villa_id')]
                for villa_id in villa_ids:
                    if villa_id:
                        periods.append({
                            'bookingId': str(booking.get('id') or ''),
                            'villaId': str(villa_id),
                            'checkInDate': str(booking['check_in_date']),
                            'checkOutDate': str(booking.get('check_out_date') or booking['check_in_date']),
                            'checkInTime': str(booking.get('check_in_time') or ''),
                        })
            if len(batch) < 500:
                break
            offset += 500
    except Exception as error:
        logger.exception('Could not load villa booking periods for maintenance scheduling.')
        raise HTTPException(status_code=503, detail='Booked villa dates could not be checked. Please retry.') from error
    return periods


def _period_bounds(period):
    from booking_assignments import MANILA, parse_time

    check_in = datetime.combine(
        date.fromisoformat(period['checkInDate']),
        parse_time(period.get('checkInTime') or '3:00 PM'),
        MANILA,
    )
    check_out_date = date.fromisoformat(period['checkOutDate'])
    check_out_time = period.get('checkOutTime')
    check_out = (
        datetime.combine(check_out_date, parse_time(check_out_time), MANILA)
        if check_out_time
        else datetime.combine(check_out_date + timedelta(days=1), time.min, MANILA)
    )
    return check_in, check_out


def suggest_maintenance_schedule(client, villa_id, *, now=None):
    from booking_assignments import MANILA

    now = now or datetime.now(MANILA)
    periods = [period for period in booked_periods(client) if period['villaId'] == str(villa_id)]
    upcoming = []
    for period in periods:
        check_in, _ = _period_bounds(period)
        if check_in > now:
            upcoming.append((check_in, period))
    target = min(upcoming, key=lambda value: value[0])[1] if upcoming else None
    target_check_in = min(upcoming, key=lambda value: value[0])[0] if upcoming else None

    if target_check_in:
        latest_day = target_check_in.date() - timedelta(days=1)
        candidate_days = (
            latest_day - timedelta(days=offset)
            for offset in range((latest_day - now.date()).days + 1)
        )
    else:
        first_day = now.date() + timedelta(days=1)
        candidate_days = iter((first_day,))

    for candidate_day in candidate_days:
        if candidate_day < now.date():
            break
        for candidate_time in (time(9), time(13), time(16)):
            candidate = datetime.combine(candidate_day, candidate_time, MANILA)
            if candidate <= now + timedelta(minutes=30):
                continue
            if target_check_in and candidate >= target_check_in:
                continue
            if any(_period_bounds(period)[0] <= candidate < _period_bounds(period)[1] for period in periods):
                continue
            target_booking = None
            if target:
                target_booking = {
                    'bookingId': target.get('bookingId'),
                    'checkInDate': target['checkInDate'],
                    'checkInTime': target.get('checkInTime') or '3:00 PM',
                }
            return {'suggestedArrival': stamp(candidate), 'targetBooking': target_booking}
    return {'suggestedArrival': None, 'targetBooking': {
        'bookingId': target.get('bookingId'),
        'checkInDate': target['checkInDate'],
        'checkInTime': target.get('checkInTime') or '3:00 PM',
    } if target else None}


def ensure_arrival_before_booking(snapshot, arrival):
    from booking_assignments import MANILA, parse_time

    target = snapshot.get('targetBooking') or {}
    if not target.get('checkInDate'):
        return
    deadline = datetime.combine(
        date.fromisoformat(target['checkInDate']),
        parse_time(target.get('checkInTime') or '3:00 PM'),
        MANILA,
    )
    if arrival.astimezone(MANILA) >= deadline:
        raise HTTPException(
            status_code=409,
            detail=f'Choose a maintenance arrival before the guest checks in on {deadline.isoformat()}.',
        )


def ensure_arrival_not_booked(client, villa_id, arrival):
    from booking_assignments import MANILA

    local_arrival = arrival.astimezone(MANILA)
    for period in booked_periods(client):
        if period['villaId'] != str(villa_id):
            continue
        check_in, check_out = _period_bounds(period)
        if check_in <= local_arrival < check_out:
            raise HTTPException(
                status_code=409,
                detail=(
                    f'This villa has a guest booking from {check_in.isoformat()} '
                    f'to {check_out.isoformat()}. Choose an arrival outside that time.'
                ),
            )


def origin():
    import booking
    value = (os.getenv('MAINTENANCE_FRONTEND_URL', '').strip() or booking.FRONTEND_URL).rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('A valid maintenance website address is required.')
    return value


def link_configuration_error():
    try:
        host = urlparse(origin()).hostname or ''
        if host.lower() == 'localhost' or host.lower().endswith('.localhost') or host in {'0.0.0.0', '::'}:
            return 'Response links need a website address the technician can open. The current address is local to this computer.'
        try:
            if ipaddress.ip_address(host).is_loopback:
                return 'Response links need a website address the technician can open. The current address is local to this computer.'
        except ValueError:
            pass
    except ValueError as error:
        return str(error)
    return ''


def signing_secret():
    secret = os.getenv('MAINTENANCE_TOKEN_SECRET', '').strip() or SUPABASE_SERVICE_ROLE_KEY
    if not secret:
        raise HTTPException(status_code=503, detail='Technician response links are not configured.')
    return secret


def response_token(row):
    state = domain.details(row).get('onCall') or {}
    payload = f"maintenance-response-v1:{row['id']}:{row['assigned_staff_id']}:{state.get('nonce')}:{state.get('expiresAt')}"
    return hmac.new(signing_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()


def response_url(row):
    return f"{origin()}/maintenance-response?{urlencode({'request': str(row['id'])})}#token={response_token(row)}"


def begin_dispatch(row, snapshot, *, now=None, window=None):
    now = now or utcnow()
    previous = snapshot.get('onCall') or {}
    minutes = window or previous.get('responseWindowMinutes') or {'High': 15, 'Medium': 30, 'Low': 60}.get(row.get('priority'), 30)
    attempted = list(dict.fromkeys([*(previous.get('attemptedStaffIds') or []), str(row['assigned_staff_id'])]))
    snapshot['onCall'] = {
        'state': 'Awaiting response', 'round': int(previous.get('round', 0)) + 1,
        'nonce': secrets.token_urlsafe(24), 'expiresAt': stamp(now + timedelta(hours=24)),
        'responseWindowMinutes': int(minutes), 'requestedAt': stamp(now),
        'responseDeadlineAt': None, 'expectedArrival': None, 'responseNotes': '',
        'respondedAt': None, 'respondedVia': None, 'reminderCount': 0,
        'attemptedStaffIds': attempted, 'attentionNeeded': False, 'attentionReason': '',
        'notification': {'state': 'pending', 'nextAttemptAt': stamp(now), 'attempts': 0},
    }
    return snapshot


def choose_technician(client, *, exclude=()):
    candidates = rows(client.table('staff_accounts').select('id,full_name,position,personal_email,role,department,is_active,account_status')
                      .eq('role', 'staff').eq('department', 'Maintenance').eq('is_active', True).eq('account_status', 'Active').execute())
    candidates = [person for person in candidates
                  if str(person['id']) not in exclude and str(person.get('personal_email') or '').strip()]
    if not candidates:
        return None
    tasks = rows(client.table('admin_tasks').select('assigned_staff_id,status,status_history').eq('source', domain.SOURCE)
                 .in_('status', ['Pending', 'In Progress', 'Pending Review']).execute())
    workload = {}
    for task in tasks:
        if (domain.details(task).get('onCall') or {}).get('state') == 'Accepted' or task.get('status') in {'In Progress', 'Pending Review'}:
            key = str(task.get('assigned_staff_id')); workload[key] = workload.get(key, 0) + 1
    return min(candidates, key=lambda person: (workload.get(str(person['id']), 0), str(person['id'])))


def read_request(client, request_id):
    found = rows(client.table('admin_tasks').select(TASK_SELECT).eq('id', str(request_id)).eq('source', domain.SOURCE).limit(1).execute())
    if not found:
        raise HTTPException(status_code=404, detail='Maintenance request was not found.')
    return found[0]


def cas(client, row, snapshot, note, *, changes=None, actor='System', actor_id=None, now=None):
    now = now or utcnow()
    previous_version = parse(row.get('updated_at'))
    if previous_version and now <= previous_version:
        now = previous_version + timedelta(microseconds=1)
    event = {'id': str(uuid4()), 'status': (changes or {}).get('status', row['status']),
             'actor': actor, 'actorStaffId': str(actor_id) if actor_id else None,
             'timestamp': stamp(now), 'note': note, 'maintenance': deepcopy(snapshot)}
    values = {**(changes or {}), 'updated_at': stamp(now),
              'status_history': [*(row.get('status_history') or []), event]}
    query = client.table('admin_tasks').update(values).eq('id', row['id']).eq('source', domain.SOURCE)
    query = query.eq('updated_at', row['updated_at']) if row.get('updated_at') else query.is_('updated_at', 'null')
    saved = rows(query.select(TASK_SELECT).execute())
    if saved:
        emit_table('admin_tasks', saved[0], row)
    return saved[0] if saved else None


def arrival_time(value, now=None):
    now = now or utcnow()
    if value is None or value.tzinfo is None:
        raise HTTPException(status_code=422, detail='Enter an arrival time, including its time zone.')
    if value < now - timedelta(minutes=2):
        raise HTTPException(status_code=422, detail='Choose an arrival time that is not in the past.')
    return stamp(value)


def record_response(snapshot, decision, arrival, notes, via, *, now=None):
    now = now or utcnow(); state = snapshot['onCall']
    state.update(state=decision, expectedArrival=arrival_time(arrival, now) if decision in {'Accepted', 'Proposed time'} else None,
                 responseNotes=notes, respondedAt=stamp(now), respondedVia=via,
                 responseDeadlineAt=None, attentionNeeded=decision in {'Unavailable', 'Proposed time', 'No response'},
                 attentionReason={'Unavailable': 'The technician is unavailable. Checking backup contacts.',
                                  'Proposed time': 'The technician proposed another arrival time. Administrator approval is needed.',
                                  'No response': 'No technician response was received. Administrator follow-up is needed.'}.get(decision, ''))
    state.pop('arrivalAlerted', None)
    # Sending jobs may finish, but their old link can no longer submit a second reply.
    return snapshot


class TechnicianReply(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', str_strip_whitespace=True)
    decision: Literal['Accepted', 'Unavailable', 'Proposed time']
    expected_arrival: datetime | None = Field(default=None, alias='expectedArrival')
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def require_details(self):
        if self.decision in {'Accepted', 'Proposed time'} and self.expected_arrival is None:
            raise ValueError('Provide your estimated arrival time.')
        if self.decision != 'Accepted' and len(self.notes) < 3:
            raise ValueError('Add a short note for the administrator.')
        return self


def authorize_reply(client, request_id, token):
    if not token or len(token) != 64:
        raise HTTPException(status_code=403, detail='This response link is invalid. Contact the administrator.')
    row = read_request(client, request_id)
    state = domain.details(row).get('onCall') or {}
    if not state.get('nonce') or not hmac.compare_digest(response_token(row), token):
        raise HTTPException(status_code=403, detail='This response link is invalid or has been replaced.')
    if not state.get('expiresAt') or parse(state['expiresAt']) <= utcnow() or row['status'] in {'Completed', 'Cancelled'}:
        raise HTTPException(status_code=410, detail='This response link has expired or the request is closed. Contact the administrator.')
    # A disabled account cannot accept a request through an older invitation.
    domain.technician(row['assigned_staff_id'])
    return row


@public_router.get('/{request_id}')
def get_response_request(request_id: UUID, response: Response, x_maintenance_token: str = Header(default='')):
    response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'})
    row = authorize_reply(service_client(), request_id, x_maintenance_token)
    state = domain.details(row)['onCall']
    return {'data': {'id': row['id'], 'reference': row['task_code'], 'title': row['title'],
                     'location': row.get('villa_name'), 'equipment': domain.details(row).get('equipment'),
                     'description': row['description'], 'priority': row['priority'],
                     'state': state['state'], 'expectedArrival': state.get('expectedArrival'),
                     'responseNotes': state.get('responseNotes'), 'canRespond': row['status'] == 'Pending' and state['state'] == 'Awaiting response'}}


@public_router.post('/{request_id}')
def submit_response(request_id: UUID, data: TechnicianReply, response: Response, x_maintenance_token: str = Header(default='')):
    response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    client = service_client(); row = authorize_reply(client, request_id, x_maintenance_token)
    snapshot = domain.details(row)
    if row['status'] != 'Pending' or snapshot['onCall']['state'] != 'Awaiting response':
        raise HTTPException(status_code=409, detail='A response has already been recorded or this request has changed.')
    record_response(snapshot, data.decision, data.expected_arrival, data.notes, 'Response link')
    staff = domain.technician(row['assigned_staff_id'])
    saved = cas(client, row, snapshot, f"Technician response: {data.decision}. {data.notes}", actor=staff.get('full_name') or 'Technician', actor_id=staff['id'])
    if not saved:
        raise HTTPException(status_code=409, detail='This request changed. Open the latest link or contact the administrator.')
    notify_admins(client, saved, 'response', f"{saved['task_code']}: technician response — {data.decision}.")
    return {'message': 'Your response was recorded. The administrator has been notified.',
            'data': {'state': data.decision, 'expectedArrival': snapshot['onCall'].get('expectedArrival')}}


@domain.router.get('/{request_id}/response-link')
def admin_response_link(request_id: UUID, context=Depends(require_admin)):
    row = read_request(service_client(), request_id)
    state = domain.details(row).get('onCall') or {}
    if row['status'] != 'Pending' or state.get('state') != 'Awaiting response' or not state.get('expiresAt') or parse(state['expiresAt']) <= utcnow():
        raise HTTPException(status_code=409, detail='Request technician availability again to create a current response link.')
    return {'url': response_url(row), 'configurationNotice': link_configuration_error()}


def notify_admins(client, row, kind, message):
    state = domain.details(row).get('onCall') or {}
    key = f"maintenance:{row['id']}:{state.get('round', 0)}:{kind}"
    recipients = rows(client.table('staff_accounts').select('id').eq('role', 'admin').eq('is_active', True).eq('account_status', 'Active').execute())
    for recipient in recipients:
        client.table('admin_notifications').upsert({
            'id': str(uuid5(NAMESPACE_URL, key + ':' + str(recipient['id']))),
            'recipient_staff_account_id': recipient['id'], 'title': 'Maintenance follow-up',
            'message': message, 'type': 'assignment', 'icon': 'task', 'task_id': row['id'], 'is_read': False,
        }, on_conflict='id', ignore_duplicates=True).execute()
        emit_table('admin_notifications', {'recipient_staff_account_id': recipient['id']})


def notify_maintenance_team(client, row):
    snapshot = domain.details(row)
    suggested = parse(snapshot.get('suggestedArrival'))
    when = suggested.astimezone(ZoneInfo('Asia/Manila')).strftime('%b %d at %I:%M %p') if suggested else 'a date before the next guest check-in'
    recipients = rows(client.table('staff_accounts').select('id').eq('role', 'staff')
                      .eq('department', 'Maintenance').eq('is_active', True)
                      .eq('account_status', 'Active').execute())
    for recipient in recipients:
        client.table('admin_notifications').upsert({
            'id': str(uuid5(NAMESPACE_URL, f"maintenance-broadcast:{row['id']}:{recipient['id']}")),
            'recipient_staff_account_id': recipient['id'], 'title': 'New maintenance request',
            'message': f"{row['task_code']}: {row['title']} at {row.get('villa_name') or 'the property'}. Suggested availability: {when}.",
            'type': 'assignment', 'icon': 'task', 'task_id': row['id'], 'is_read': False,
        }, on_conflict='id', ignore_duplicates=True).execute()
        emit_table('admin_notifications', {'recipient_staff_account_id': recipient['id']})


def send_notice(row, staff):
    """Return acknowledgement, never presumed delivery/acceptance by a technician."""
    problem = link_configuration_error()
    if problem: return 'blocked', 'Email', problem
    import booking
    try:
        recipient = validate_email(str(staff.get('personal_email') or ''), check_deliverability=False).normalized
    except EmailNotValidError:
        return 'failed', 'Email', 'The technician email address is invalid.'
    if not booking._smtp_configured():
        return 'blocked', 'Email', 'Email service is unavailable; administrator follow-up is needed.'
    link = response_url(row)
    state = domain.details(row)['onCall']; reminder = state.get('reminderCount', 0)
    text = (f"The Villa {'reminder' if reminder else 'maintenance request'} {row['task_code']}: "
            f"{row['title']} at {row.get('villa_name') or 'the property'}. Priority: {row['priority']}. "
            f"Please confirm availability and arrival time before attending: {link}")
    message = EmailMessage(); message['Subject'] = f"The Villa — {'Reminder: ' if reminder else ''}On-call maintenance request"
    message['From'] = booking.SMTP_FROM; message['To'] = recipient
    message['Message-ID'] = f"<maintenance-{row['id']}-{state['round']}-{reminder}@{booking.SMTP_FROM.rsplit('@', 1)[-1]}>"
    message.set_content(text + '\n\nThis is a request for availability. Reply using the link; no staff login is needed.')
    sending = False
    accepted = False
    try:
        with smtplib.SMTP(booking.SMTP_HOST, booking.SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            smtp.login(booking.SMTP_USER, booking.SMTP_PASSWORD); sending = True
            refused = smtp.send_message(message)
            if refused: return 'failed', 'Email', 'The email recipient was rejected.'
            accepted = True
        return 'accepted', 'Email', ''
    except Exception:
        if accepted: return 'accepted', 'Email', ''
        return ('uncertain', 'Email', 'Email submission outcome is uncertain. Check before resending.') if sending else ('blocked', 'Email', 'Email service is unavailable; administrator follow-up is needed.')


def finish_notice(client, request_id, lease, result, channel, message, now):
    for _ in range(3):
        row = read_request(client, request_id); snapshot = domain.details(row); state = snapshot.get('onCall') or {}
        notice = state.get('notification') or {}
        if notice.get('lease') != lease: return
        notice.update(state=result, channel=channel, message=message, finishedAt=stamp(now), lease=None)
        if result == 'accepted':
            notice['acceptedAt'] = stamp(now)
            if state.get('state') == 'Awaiting response':
                state['responseDeadlineAt'] = stamp(now + timedelta(minutes=state['responseWindowMinutes']))
                if not state.get('reminderCount'):
                    state.update(attentionNeeded=False, attentionReason='')
        else:
            state.update(attentionNeeded=True, attentionReason=message)
            if result == 'blocked': notice['nextAttemptAt'] = stamp(now + timedelta(minutes=5))
        saved = cas(client, row, snapshot, f"Maintenance alert: {result}{' via ' + channel if channel else ''}.", now=now)
        if saved:
            if result != 'accepted': notify_admins(client, saved, 'delivery', f"{saved['task_code']}: {message}")
            return


def process_one(client, row, now):
    snapshot = domain.details(row); state = snapshot.get('onCall')
    if not state or row['status'] in {'Completed', 'Cancelled'}: return
    if state['state'] == 'Accepted':
        if row['status'] == 'Pending' and state.get('expectedArrival') and parse(state['expectedArrival']) + timedelta(minutes=15) < now and not state.get('arrivalAlerted'):
            state.update(arrivalAlerted=True, attentionNeeded=True, attentionReason='The confirmed arrival time has passed. Contact the technician.')
            saved = cas(client, row, snapshot, 'Confirmed arrival overdue; administrator notified.', now=now)
            if saved: notify_admins(client, saved, 'arrival', f"{saved['task_code']}: confirmed arrival is overdue.")
        return
    if row['status'] != 'Pending': return
    if state['state'] in {'Unavailable', 'No response'}:
        replacement = choose_technician(client, exclude=state.get('attemptedStaffIds') or [])
        if replacement:
            changes = {'assigned_staff_id': str(replacement['id']), 'assigned_role': replacement.get('position')}
            begin_dispatch({**row, **changes}, snapshot, now=now)
            saved = cas(client, row, snapshot, 'Availability request routed to the next Maintenance contact.', changes=changes, now=now)
            if saved: notify_admins(client, saved, 'rerouted', f"{saved['task_code']}: availability requested from a backup technician.")
        elif not state.get('backupChecked'):
            state.update(backupChecked=True, attentionNeeded=True, attentionReason='No uncontacted Maintenance technician remains. Check the Maintenance staff email addresses or assign another technician.')
            saved = cas(client, row, snapshot, 'No backup technician remains; administrator follow-up required.', now=now)
            if saved: notify_admins(client, saved, 'no-backup', f"{saved['task_code']}: no backup technician is available to contact.")
        return
    if state['state'] != 'Awaiting response': return
    if state.get('expiresAt') and parse(state['expiresAt']) <= now:
        record_response(snapshot, 'No response', None, 'The availability link expired without a response.', 'System', now=now)
        saved = cas(client, row, snapshot, 'Availability link expired; backup routing requested.', now=now)
        if saved: notify_admins(client, saved, 'expired', f"{saved['task_code']}: availability link expired without a response.")
        return
    notice = state.get('notification') or {}
    if notice.get('state') == 'sending':
        if parse(notice.get('leaseExpiresAt')) and parse(notice['leaseExpiresAt']) < now:
            notice.update(state='uncertain', message='Alert worker stopped before recording delivery. Check before resending.')
            state.update(attentionNeeded=True, attentionReason=notice['message'])
            saved = cas(client, row, snapshot, 'Alert delivery outcome needs administrator review.', now=now)
            if saved: notify_admins(client, saved, 'delivery', f"{saved['task_code']}: alert delivery outcome needs review.")
        return
    if notice.get('state') in {'pending', 'blocked'} and (not notice.get('nextAttemptAt') or parse(notice['nextAttemptAt']) <= now):
        try: staff = domain.technician(row['assigned_staff_id'])
        except HTTPException:
            record_response(snapshot, 'Unavailable', None, 'Assigned technician account is inactive.', 'System', now=now)
            cas(client, row, snapshot, 'Assigned technician is inactive; backup routing requested.', now=now); return
        lease = str(uuid4()); notice.update(state='sending', lease=lease, leaseExpiresAt=stamp(now + timedelta(minutes=2)), attempts=int(notice.get('attempts', 0)) + 1)
        claimed = cas(client, row, snapshot, 'Maintenance alert queued for delivery.', now=now)
        if not claimed: return
        fresh = read_request(client, row['id']); fresh_state = domain.details(fresh).get('onCall') or {}
        if fresh_state.get('state') != 'Awaiting response' or fresh_state.get('nonce') != state.get('nonce') or fresh['status'] != 'Pending': return
        result, channel, message = send_notice(claimed, staff)
        finish_notice(client, row['id'], lease, result, channel, message, now)
        return
    deadline = parse(state.get('responseDeadlineAt'))
    if notice.get('state') == 'accepted' and deadline and deadline <= now:
        if not state.get('reminderCount'):
            state.update(reminderCount=1, responseDeadlineAt=None, attentionNeeded=True,
                         attentionReason='No response yet. A reminder is being sent; email follow-up may be needed.',
                         notification={'state': 'pending', 'nextAttemptAt': stamp(now), 'attempts': 0})
            saved = cas(client, row, snapshot, 'No response within the response window; one reminder queued.', now=now)
            if saved: notify_admins(client, saved, 'reminder', f"{saved['task_code']}: no technician response yet; reminder queued.")
        else:
            record_response(snapshot, 'No response', None, 'No reply after the reminder window.', 'System', now=now)
            saved = cas(client, row, snapshot, 'No technician response after reminder; backup routing requested.', now=now)
            if saved: notify_admins(client, saved, 'no-response', f"{saved['task_code']}: no technician response after the reminder.")


def process_maintenance_oncall(client=None, now=None):
    client = client or service_client(); now = now or utcnow()
    records = rows(client.table('admin_tasks').select(TASK_SELECT).eq('source', domain.SOURCE)
                   .in_('status', ['Pending', 'In Progress', 'Pending Review']).limit(2000).execute())
    for row in records:
        try: process_one(client, row, now)
        except Exception:
            # Never log recipient data, response links or provider responses.
            logger.warning('Maintenance request %s needs follow-up processing.', row.get('id'))
