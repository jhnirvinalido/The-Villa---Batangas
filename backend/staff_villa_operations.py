"""The staff and admin villa views share the same maintenance task records."""
from typing import Literal
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from admin import TASK_SELECT, rows, service_client
from staff import require_staff
from maintenance import SOURCE, MaintenanceRequest, create_maintenance, details, technician
from villa_catalog import _read_rows

router = APIRouter(prefix='/staff/villa-operations', tags=['Staff villa operations'])


class VillaReport(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)
    villa_id: str = Field(alias='villaId', min_length=1, max_length=100)
    kind: Literal['Repair', 'Inspection'] = 'Repair'
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5, max_length=5000)
    priority: Literal['High', 'Medium', 'Low'] = 'Medium'
    blocks_booking: bool = Field(default=True, alias='blocksBooking')


def staff_work(row, staff_id):
    meta = details(row)
    assigned = str(row.get('assigned_staff_id')) == str(staff_id)
    on_call = meta.get('onCall') or {}
    broadcast = bool(meta.get('broadcastToMaintenance'))
    can_respond = (
        row.get('status') == 'Pending' and on_call.get('state') == 'Awaiting response'
        and (assigned or (broadcast and str(staff_id) not in (on_call.get('declinedStaffIds') or [])))
    )
    return {
        'id': row['id'], 'taskCode': row.get('task_code'), 'title': row['title'],
        'description': row.get('description'), 'villaName': row.get('villa_name'),
        'status': row['status'], 'priority': row.get('priority'), 'progress': row.get('progress') or 0,
        'assignedToMe': assigned, 'canRespond': can_respond,
        'createdAt': row.get('created_at'), 'updatedAt': row.get('updated_at'),
        'notes': row.get('notes') or '' if assigned else '',
        'checklist': row.get('checklist') or [] if assigned else [],
        'maintenance': {
            'villaId': meta.get('villaId'), 'kind': meta.get('kind', 'Repair'),
            'broadcastToMaintenance': broadcast,
            'blocksBooking': bool(meta.get('blocksBooking')), 'waitingForParts': meta.get('waitingForParts', False),
            'partsNotes': meta.get('partsNotes') or '' if assigned else '',
            'suggestedArrival': meta.get('suggestedArrival'), 'targetBooking': meta.get('targetBooking'),
            'onCall': {key: on_call.get(key) for key in ('state', 'expectedArrival', 'attentionNeeded', 'attentionReason', 'responseNotes')},
        },
    }


@router.get('')
def staff_villas(context=Depends(require_staff)):
    client = service_client()
    # Shared operational summaries let staff see villa readiness; only assignees
    # receive editable checklists and work notes. Admin-created jobs are included.
    work = rows(client.table('admin_tasks').select(TASK_SELECT).eq('source', SOURCE)
                .order('created_at', desc=True).limit(2000).execute())
    from maintenance_oncall import booked_periods
    return {'data': {
        'villas': _read_rows(client),
        'reports': [staff_work(row, context['account']['id']) for row in work],
        'bookedPeriods': booked_periods(client),
    }}


@router.post('', status_code=201)
def report_villa_work(data: VillaReport, context=Depends(require_staff)):
    result = create_maintenance(MaintenanceRequest(
        villaId=data.villa_id, kind=data.kind, title=data.title, description=data.description,
        priority=data.priority, blocksBooking=False,
        reportedBy=context['account'].get('full_name') or 'Staff',
    ), context)
    return {'message': 'Maintenance request sent. Booking availability will pause after the administrator confirms the schedule.',
            'data': {'id': result['data']['id'], 'status': result['data']['status']}}


class StaffAvailability(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)
    expected_updated_at: datetime = Field(alias='expectedUpdatedAt')
    decision: Literal['Accepted', 'Unavailable', 'Proposed time']
    expected_arrival: datetime | None = Field(default=None, alias='expectedArrival')
    notes: str = Field(default='', max_length=2000)


@router.post('/{request_id}/response')
def staff_availability(request_id: UUID, data: StaffAvailability, context=Depends(require_staff)):
    from maintenance_oncall import read_request, record_response, cas, notify_admins, ensure_arrival_not_booked, ensure_arrival_before_booking
    client = service_client()
    row = read_request(client, request_id)
    staff_id = str(context['account']['id'])
    snapshot = details(row)
    on_call = snapshot.get('onCall') or {}
    broadcast = bool(snapshot.get('broadcastToMaintenance'))
    assigned = str(row.get('assigned_staff_id')) == staff_id
    can_claim = (
        broadcast and row.get('status') == 'Pending' and on_call.get('state') == 'Awaiting response'
        and staff_id not in (on_call.get('declinedStaffIds') or [])
    )
    if not assigned and not can_claim:
        raise HTTPException(status_code=403, detail='This maintenance request is assigned to another technician.')
    responder = technician(staff_id)
    if datetime.fromisoformat(str(row.get('updated_at')).replace('Z', '+00:00')) != data.expected_updated_at:
        raise HTTPException(status_code=409, detail='This request changed. Refresh before responding.')
    if row['status'] != 'Pending' or on_call.get('state') != 'Awaiting response':
        raise HTTPException(status_code=409, detail='A response is already recorded or this request has changed.')
    if data.decision != 'Accepted' and len(data.notes) < 3:
        raise HTTPException(status_code=422, detail='Add a short explanation for the administrator.')
    if data.expected_arrival and snapshot.get('villaId'):
        ensure_arrival_not_booked(client, snapshot['villaId'], data.expected_arrival)
        ensure_arrival_before_booking(snapshot, data.expected_arrival)
    if broadcast and data.decision == 'Unavailable':
        on_call['declinedStaffIds'] = list(dict.fromkeys([*(on_call.get('declinedStaffIds') or []), staff_id]))
        on_call.setdefault('teamResponses', []).append({
            'staffId': staff_id, 'decision': data.decision, 'notes': data.notes,
            'respondedAt': datetime.now(timezone.utc).isoformat(),
        })
        saved = cas(client, row, snapshot, f"Technician unavailable: {data.notes}", actor=context['account']['full_name'], actor_id=staff_id)
        if not saved:
            raise HTTPException(status_code=409, detail='This request changed. Refresh before responding.')
        notify_admins(client, saved, 'response', f"{saved['task_code']}: {responder.get('full_name')} is unavailable for this request.")
        return {'message': 'You were marked unavailable. The request remains open for the maintenance team.', 'data': staff_work(saved, staff_id)}
    record_response(snapshot, data.decision, data.expected_arrival, data.notes, 'Maintenance portal')
    changes = {'assigned_staff_id': staff_id, 'assigned_role': responder.get('position')} if broadcast else None
    saved = cas(client, row, snapshot, f'Technician response: {data.decision}. {data.notes}', changes=changes,
                actor=context['account']['full_name'], actor_id=staff_id)
    if not saved:
        raise HTTPException(status_code=409, detail='This request changed. Refresh before responding.')
    notify_admins(client, saved, 'response', f"{saved['task_code']}: technician response — {data.decision}.")
    return {'message': 'Availability recorded.', 'data': staff_work(saved, context['account']['id'])}
