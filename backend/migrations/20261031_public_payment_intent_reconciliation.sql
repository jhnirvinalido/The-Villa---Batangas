begin;

update public.public_booking_checkouts
set next_check_at = coalesce(next_check_at, now())
where nullif(booking_payload->>'paymongo_payment_intent_id', '') is not null;

drop index if exists public.public_booking_checkouts_reconciliation_idx;
create index if not exists public_booking_checkouts_reconciliation_idx
    on public.public_booking_checkouts (next_check_at)
    where next_check_at is not null;

commit;
