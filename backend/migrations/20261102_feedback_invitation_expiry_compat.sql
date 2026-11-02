-- Align older feedback invitation outboxes with the current queue RPC contract.
begin;

alter table public.feedback_invitation_outbox
    add column if not exists expires_at timestamptz;

update public.feedback_invitation_outbox as invitation
set expires_at = coalesce(
    invitation.expires_at,
    booking.feedback_token_expires_at,
    invitation.created_at + interval '30 days'
)
from public.bookings as booking
where booking.id = invitation.booking_id
  and invitation.expires_at is null;

alter table public.feedback_invitation_outbox
    alter column expires_at set default (now() + interval '30 days'),
    alter column expires_at set not null;

commit;
