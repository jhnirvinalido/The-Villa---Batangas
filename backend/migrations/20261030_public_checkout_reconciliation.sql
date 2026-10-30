-- Persist a rate-limited PayMongo reconciliation schedule for public drafts.
begin;

alter table public.public_booking_checkouts
    add column if not exists paymongo_checkout_session_id text,
    add column if not exists next_check_at timestamptz;

update public.public_booking_checkouts
set paymongo_checkout_session_id = booking_payload->>'paymongo_checkout_session_id',
    next_check_at = coalesce(next_check_at, now())
where nullif(booking_payload->>'paymongo_checkout_session_id', '') is not null;

create index if not exists public_booking_checkouts_reconciliation_idx
    on public.public_booking_checkouts (next_check_at)
    where paymongo_checkout_session_id is not null;

commit;
