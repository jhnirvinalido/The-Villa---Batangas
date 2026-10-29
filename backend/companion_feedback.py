"""Per-companion capabilities; responses remain internal and outside public ratings."""
from uuid import UUID
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
import booking
from admin import require_admin
from feedback_service import token_for

router = APIRouter(tags=['Companion feedback'])

class InvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


def companion_token(booking_id, slot, parent_hash):
    return token_for(str(booking_id), f'companion-v1:{slot}:{parent_hash}')


@router.post('/public-bookings/{booking_id}/feedback/companions')
def invite_companions(booking_id: UUID, data: InvitationRequest):
    record = booking._require_feedback_booking(str(booking_id), data.token)
    capacity = max(0, int(record.get('guest_count') or 1) - 1)
    if capacity > 1000:
        raise HTTPException(422, 'Please contact The Villa to arrange feedback for this group size.')
    parent_hash = booking._token_hash(data.token)
    tokens = {slot: companion_token(booking_id, slot, parent_hash) for slot in range(1, capacity + 1)}
    try:
        result = booking._service().rpc('issue_companion_feedback_links', {
            'p_booking_id': str(booking_id), 'p_parent_hash': parent_hash,
            'p_tokens': [{'slot': slot, 'token_hash': booking._token_hash(token)} for slot, token in tokens.items()],
        }).execute().data
        if not isinstance(result, list):
            raise ValueError('Invalid invitation response')
        links = [{'slot': row['slot'], 'submitted': bool(row['submitted']), 'expires_at': row['expires_at'],
                  'url': f'{booking.FRONTEND_URL.rstrip("/")}/feedback?{urlencode({"booking":str(booking_id),"companion":"1"})}#token={tokens[row["slot"]]}'} for row in result]
        return {'invitations': links, 'capacity': capacity}
    except Exception:
        raise HTTPException(503, 'Companion invitations are unavailable. Please try again later or contact The Villa.') from None


def access(booking_id, token, feedback=None):
    if not token or not 20 <= len(token) <= 200:
        raise HTTPException(401, 'This companion feedback link is incomplete.')
    try:
        result = booking._service().rpc('access_companion_feedback', {
            'p_booking_id': str(booking_id), 'p_token_hash': booking._token_hash(token), 'p_feedback': feedback,
        }).execute().data
        if not isinstance(result, dict) or 'submitted' not in result:
            raise ValueError('Invalid response')
        return result
    except Exception:
        raise HTTPException(409, 'This companion link is unavailable or expired. Ask the booking guest for a current link, or try again later.') from None


@router.get('/public-bookings/{booking_id}/feedback/companion')
def companion_form(booking_id: UUID, x_feedback_token: str | None = Header(default=None)):
    return access(booking_id, x_feedback_token)


@router.post('/public-bookings/{booking_id}/feedback/companion')
def submit_companion(booking_id: UUID, data: booking.GuestFeedbackRequest):
    result = access(booking_id, data.token, data.model_dump(exclude={'token'}))
    if not result.get('submitted'):
        raise HTTPException(503, 'Your feedback could not be saved. Please try again.')
    if not result.get('duplicate'):
        from live_updates import emit_table
        emit_table('companion_feedback', {})
    return {'submitted': True, 'message': 'Thank you for sharing your experience with our team.'}


@router.get('/admin/guest-feedback/companions')
def list_companion_feedback(context=Depends(require_admin)):
    from admin import service_client, rows
    from feedback_policy import admin_feedback_projection
    try:
        records = rows(service_client().table('companion_feedback').select('id,overall_rating,comments,created_at').order('created_at', desc=True).limit(500).execute())
        return {'data': [admin_feedback_projection({**row, 'hide_identity': True, 'source': 'companion', 'analysis_status': 'internal_only'}) for row in records]}
    except Exception:
        raise HTTPException(503, 'Companion feedback is unavailable. Confirm the companion feedback migration is installed.') from None
