begin;

alter table public.bookings
    add column if not exists booking_channel text;

alter table public.airbnb_stays
    add column if not exists booking_id uuid references public.bookings(id);

alter table public.airbnb_stays
    drop constraint if exists airbnb_stays_status_check;
alter table public.airbnb_stays
    add constraint airbnb_stays_status_check
    check (status in ('held', 'confirmed', 'booked', 'released'));

alter table public.airbnb_stays
    drop constraint if exists airbnb_stays_booking_link_check;
alter table public.airbnb_stays
    add constraint airbnb_stays_booking_link_check
    check (
        (status = 'booked' and booking_id is not null)
        or (status <> 'booked' and booking_id is null)
    );

create or replace function public.confirm_airbnb_stay_booking(
    p_stay_id uuid,
    p_booking jsonb,
    p_actor_id uuid
) returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
    stay public.airbnb_stays%rowtype;
    saved jsonb;
    column_names text;
    payload_villas text[];
begin
    lock table public.bookings in share row exclusive mode;
    lock table public.airbnb_stays in share row exclusive mode;

    select * into stay
    from public.airbnb_stays
    where id = p_stay_id
    for update;

    if not found then
        raise exception 'Airbnb hold not found';
    end if;

    if stay.status = 'booked' and stay.booking_id is not null then
        select to_jsonb(b) into saved
        from public.bookings b
        where b.id = stay.booking_id;
        if saved is null then
            raise exception 'Linked Airbnb booking not found';
        end if;
        return saved;
    end if;

    if stay.status not in ('held', 'confirmed')
       or (stay.status = 'held' and stay.expires_at <= now()) then
        raise exception 'Airbnb hold expired or unavailable';
    end if;

    select array(select jsonb_array_elements_text(p_booking->'villa_ids'))
      into payload_villas;
    if p_booking->>'id' is null
       or p_booking->>'booking_channel' <> 'airbnb'
       or nullif(trim(p_booking->>'customer_name'), '') is null
       or (p_booking->>'check_in_date')::date <> stay.check_in_date
       or (p_booking->>'check_out_date')::date <> stay.check_out_date
       or payload_villas is distinct from stay.villa_ids then
        raise exception 'Airbnb booking details do not match the held stay';
    end if;

    if exists (
        select 1
        from public.bookings b
        where lower(coalesce(to_jsonb(b)->>'booking_status', '')) not in
              ('cancelled', 'canceled', 'expired', 'rejected')
          and (to_jsonb(b)->>'check_in_date')::date < stay.check_out_date
          and (to_jsonb(b)->>'check_out_date')::date > stay.check_in_date
          and exists (
              select 1
              from jsonb_array_elements_text(
                  coalesce(
                      nullif(to_jsonb(b)->'villa_ids', 'null'::jsonb),
                      jsonb_build_array(to_jsonb(b)->>'villa_id')
                  )
              ) existing_villa(villa_id)
              where existing_villa.villa_id = any(stay.villa_ids)
          )
    ) then
        raise exception 'Airbnb booking conflicts with a booking';
    end if;

    update public.airbnb_stays
    set status = 'released',
        expires_at = null,
        updated_by_staff_id = p_actor_id,
        updated_at = now()
    where id = p_stay_id;

    select string_agg(quote_ident(k.column_name), ',')
      into column_names
      from jsonb_object_keys(p_booking) as k(column_name)
      where k.column_name in (
          select column_name
          from information_schema.columns
          where table_schema = 'public' and table_name = 'bookings'
      );

    if column_names is null then
        raise exception 'Airbnb booking could not be stored';
    end if;

    execute format(
        'insert into public.bookings (%1$s) select %1$s from jsonb_populate_record(null::public.bookings,$1) returning to_jsonb(bookings.*)',
        column_names
    ) into saved using p_booking;

    update public.airbnb_stays
    set status = 'booked',
        booking_id = (p_booking->>'id')::uuid,
        updated_by_staff_id = p_actor_id,
        updated_at = now()
    where id = p_stay_id;

    return saved;
end;
$$;

revoke all on function public.confirm_airbnb_stay_booking(uuid,jsonb,uuid)
    from public, anon, authenticated;
grant execute on function public.confirm_airbnb_stay_booking(uuid,jsonb,uuid)
    to service_role;

commit;
