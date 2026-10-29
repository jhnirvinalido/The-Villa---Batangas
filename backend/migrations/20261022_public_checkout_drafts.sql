-- Public payment attempts are isolated from bookings and admin reports.
-- Apply before deploying the updated public booking endpoints.
begin;
create table if not exists public.public_booking_checkouts (
    id uuid primary key,
    booking_payload jsonb not null,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
alter table public.public_booking_checkouts enable row level security;
revoke all on public.public_booking_checkouts from anon, authenticated;
grant all on public.public_booking_checkouts to service_role;

create or replace function public.finalize_public_booking_checkout(
    p_checkout_id uuid, p_booking_update jsonb, p_payment jsonb
) returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
    draft public.public_booking_checkouts%rowtype;
    payload jsonb;
    saved jsonb;
    column_names text;
begin
    select * into draft from public.public_booking_checkouts where id=p_checkout_id for update;
    if not found then
        select to_jsonb(b) into saved from public.bookings b where id=p_checkout_id;
        if saved is null then raise exception 'Checkout draft not found'; end if;
        return saved;
    end if;
    if p_booking_update->>'booking_status' <> 'Confirmed'
       or p_payment->>'status' <> 'paid'
       or upper(p_payment->>'currency') <> 'PHP'
       or (p_payment->>'amount')::numeric <> (draft.booking_payload->>'payment_due_amount')::numeric
       or p_payment->>'paymongo_checkout_session_id' is distinct from draft.booking_payload->>'paymongo_checkout_session_id'
       or nullif(p_payment->>'paymongo_payment_id','') is null then
        raise exception 'Payment does not match checkout';
    end if;
    -- Serialize against booking writes so concurrent paid checkouts cannot
    -- promote overlapping reservations. A failed transaction retains the draft.
    lock table public.bookings in share row exclusive mode;
    payload := draft.booking_payload || p_booking_update || jsonb_build_object('id',p_checkout_id);
    if exists (
        select 1 from public.bookings b
        where lower(b.booking_status) not in ('cancelled','canceled','expired','rejected')
          and b.check_in_date < (payload->>'check_out_date')::date
          and b.check_out_date > (payload->>'check_in_date')::date
          and exists (
              select 1 from jsonb_array_elements_text(coalesce(nullif(to_jsonb(b)->'villa_ids','null'::jsonb),jsonb_build_array(b.villa_id))) as existing_villa(villa_id)
              where existing_villa.villa_id in (select jsonb_array_elements_text(payload->'villa_ids'))
          )
    ) then
        raise exception 'Payment received but villa is no longer available; merchant review required';
    end if;
    select string_agg(quote_ident(key), ',') into column_names
      from jsonb_object_keys(payload) key
      where key in (select column_name from information_schema.columns where table_schema='public' and table_name='bookings');
    execute format('insert into public.bookings (%s) select %s from jsonb_populate_record(null::public.bookings,$1) returning to_jsonb(bookings.*)', column_names,column_names)
        into saved using payload;
    payload := p_payment || jsonb_build_object('booking_id',p_checkout_id);
    select string_agg(quote_ident(key), ',') into column_names
      from jsonb_object_keys(payload) key
      where key in (select column_name from information_schema.columns where table_schema='public' and table_name='booking_payments');
    execute format('insert into public.booking_payments (%s) select %s from jsonb_populate_record(null::public.booking_payments,$1)',column_names,column_names) using payload;
    delete from public.public_booking_checkouts where id=p_checkout_id;
    return saved || '{"_checkout_finalized":true}'::jsonb;
end;
$$;
revoke all on function public.finalize_public_booking_checkout(uuid,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.finalize_public_booking_checkout(uuid,jsonb,jsonb) to service_role;
commit;
