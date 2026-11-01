begin;

alter table public.bookings
    add column if not exists airbnb_payment_status text;

alter table public.bookings
    add column if not exists airbnb_payment_recorded_at timestamptz;

alter table public.bookings
    add column if not exists airbnb_payment_recorded_by_staff_id uuid;

alter table public.bookings
    drop constraint if exists bookings_airbnb_payment_status_check;
alter table public.bookings
    add constraint bookings_airbnb_payment_status_check
    check (
        airbnb_payment_status is null
        or airbnb_payment_status in ('unconfirmed', 'paid')
    );

alter table public.bookings
    drop constraint if exists bookings_airbnb_payment_record_check;
alter table public.bookings
    add constraint bookings_airbnb_payment_record_check
    check (
        (airbnb_payment_status = 'paid'
            and airbnb_payment_recorded_at is not null
            and airbnb_payment_recorded_by_staff_id is not null)
        or (airbnb_payment_status is distinct from 'paid'
            and airbnb_payment_recorded_at is null
            and airbnb_payment_recorded_by_staff_id is null)
    );

commit;
