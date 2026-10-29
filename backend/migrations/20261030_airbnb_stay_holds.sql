begin;

create table if not exists public.airbnb_stays (
    id uuid primary key,
    check_in_date date not null,
    check_out_date date not null,
    guest_count integer not null check (guest_count between 1 and 32),
    villa_ids text[] not null check (cardinality(villa_ids) > 0),
    status text not null check (status in ('held', 'confirmed', 'released')),
    expires_at timestamptz,
    created_by_staff_id uuid not null,
    updated_by_staff_id uuid not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint airbnb_stays_valid_dates check (check_out_date > check_in_date),
    constraint airbnb_stays_hold_expiry check (
        (status = 'held' and expires_at is not null)
        or (status <> 'held' and expires_at is null)
    )
);

create index if not exists airbnb_stays_date_status_idx
    on public.airbnb_stays (check_in_date, check_out_date, status);
create index if not exists airbnb_stays_villa_ids_idx
    on public.airbnb_stays using gin (villa_ids);

alter table public.airbnb_stays enable row level security;
revoke all on public.airbnb_stays from anon, authenticated;
grant all on public.airbnb_stays to service_role;

create or replace function public.create_airbnb_stay_hold(
    p_id uuid,
    p_check_in_date date,
    p_check_out_date date,
    p_guest_count integer,
    p_villa_ids text[],
    p_created_by_staff_id uuid,
    p_expires_at timestamptz
) returns public.airbnb_stays
language plpgsql security definer set search_path = public
as $$
declare saved public.airbnb_stays%rowtype;
begin
    if p_check_out_date <= p_check_in_date
       or p_check_out_date - p_check_in_date > 63
       or p_guest_count not between 1 and 32
       or coalesce(cardinality(p_villa_ids), 0) = 0
       or p_expires_at <= now() then
        raise exception 'Invalid Airbnb hold details';
    end if;

    -- Serialize hold creation against booking confirmation and other holds.
    lock table public.bookings in share row exclusive mode;
    lock table public.airbnb_stays in share row exclusive mode;

    if exists (
        select 1
        from public.bookings b
        where lower(coalesce(to_jsonb(b)->>'booking_status', '')) not in
              ('cancelled', 'canceled', 'expired', 'rejected')
          and (to_jsonb(b)->>'check_in_date')::date < p_check_out_date
          and (to_jsonb(b)->>'check_out_date')::date > p_check_in_date
          and exists (
              select 1
              from jsonb_array_elements_text(
                  coalesce(
                      nullif(to_jsonb(b)->'villa_ids', 'null'::jsonb),
                      jsonb_build_array(to_jsonb(b)->>'villa_id')
                  )
              ) existing_villa(villa_id)
              where existing_villa.villa_id = any(p_villa_ids)
          )
    ) then
        raise exception 'Airbnb hold conflicts with a booking';
    end if;

    if exists (
        select 1
        from public.airbnb_stays s
        where (s.status = 'confirmed' or (s.status = 'held' and s.expires_at > now()))
          and s.check_in_date < p_check_out_date
          and s.check_out_date > p_check_in_date
          and s.villa_ids && p_villa_ids
    ) then
        raise exception 'Airbnb hold conflicts with an existing hold or stay';
    end if;

    insert into public.airbnb_stays (
        id, check_in_date, check_out_date, guest_count, villa_ids, status,
        expires_at, created_by_staff_id, updated_by_staff_id
    ) values (
        p_id, p_check_in_date, p_check_out_date, p_guest_count, p_villa_ids,
        'held', p_expires_at, p_created_by_staff_id, p_created_by_staff_id
    ) returning * into saved;

    return saved;
end;
$$;

revoke all on function public.create_airbnb_stay_hold(uuid,date,date,integer,text[],uuid,timestamptz)
    from public, anon, authenticated;
grant execute on function public.create_airbnb_stay_hold(uuid,date,date,integer,text[],uuid,timestamptz)
    to service_role;

create or replace function public.prevent_booking_during_airbnb_stay()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
    if lower(coalesce(to_jsonb(new)->>'booking_status', '')) in
       ('cancelled', 'canceled', 'expired', 'rejected') then
        return new;
    end if;

    if exists (
        select 1
        from public.airbnb_stays s
        where (s.status = 'confirmed' or (s.status = 'held' and s.expires_at > now()))
          and s.check_in_date < (to_jsonb(new)->>'check_out_date')::date
          and s.check_out_date > (to_jsonb(new)->>'check_in_date')::date
          and s.villa_ids && array(
              select jsonb_array_elements_text(
                  coalesce(
                      nullif(to_jsonb(new)->'villa_ids', 'null'::jsonb),
                      jsonb_build_array(to_jsonb(new)->>'villa_id')
                  )
              )
          )
    ) then
        raise exception 'Booking conflicts with an active Airbnb hold or stay'
            using errcode = '23505';
    end if;
    return new;
end;
$$;

drop trigger if exists bookings_prevent_airbnb_stay_conflict on public.bookings;
create trigger bookings_prevent_airbnb_stay_conflict
    before insert or update of booking_status, check_in_date, check_out_date, villa_id, villa_ids
    on public.bookings
    for each row execute function public.prevent_booking_during_airbnb_stay();

revoke all on function public.prevent_booking_during_airbnb_stay() from public, anon, authenticated;

commit;
