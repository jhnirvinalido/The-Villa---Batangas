-- Post-stay guest feedback form and email invitation outbox.
-- Reconciled against the schema-only export supplied on 2026-11-02.
-- Apply in Supabase SQL Editor only after reviewing the deployment notes.
begin;

do $$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_attribute a
          on a.attrelid = c.conrelid
         and a.attname = 'id'
         and not a.attisdropped
        where c.conrelid = 'public.bookings'::regclass
          and c.contype in ('p', 'u')
          and c.conkey = array[a.attnum]::smallint[]
    ) then
        raise exception 'public.bookings.id must have a primary-key or unique constraint before applying feedback invitations';
    end if;
end;
$$;

alter table public.bookings
    add column if not exists feedback_token_hash text,
    add column if not exists feedback_token_expires_at timestamptz,
    add column if not exists feedback_token_revoked_at timestamptz;

alter table public.guest_feedback
    add column if not exists hide_identity boolean not null default false,
    add column if not exists private_note text,
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists source text,
    add column if not exists review_date date,
    add column if not exists review_date_label text;

update public.guest_feedback
set source = case when booking_id is null then 'historical_dataset' else 'verified_stay' end
where source is null;

alter table public.guest_feedback
    alter column source set default 'verified_stay',
    alter column source set not null,
    alter column id set default gen_random_uuid();

comment on column public.guest_feedback.hide_identity is
    'When true, guest identity is hidden in staff-facing feedback projections.';
comment on column public.guest_feedback.private_note is
    'Private feedback note; never returned in public review projections or sent for model analysis.';
comment on column public.guest_feedback.source is
    'verified_stay for secure post-stay submissions; historical_dataset for imported legacy reviews.';
comment on column public.guest_feedback.review_date is
    'Original review date when known; null when the historical source supplied no exact date.';

create index if not exists guest_feedback_booking_id_idx
    on public.guest_feedback (booking_id)
    where booking_id is not null;

create table if not exists public.feedback_invitation_outbox (
    id uuid primary key default gen_random_uuid(),
    booking_id uuid not null unique references public.bookings(id) on delete cascade,
    token_nonce text not null,
    message_id text not null unique,
    status text not null default 'pending'
        check (status in ('pending', 'sending', 'accepted', 'retry', 'uncertain', 'suppressed')),
    attempts integer not null default 0 check (attempts >= 0),
    next_attempt_at timestamptz not null default now(),
    claim_id uuid,
    claim_expires_at timestamptz,
    email_accepted_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists feedback_invitation_outbox_due_idx
    on public.feedback_invitation_outbox (next_attempt_at, created_at)
    where status in ('pending', 'retry');

alter table public.guest_feedback enable row level security;
alter table public.feedback_invitation_outbox enable row level security;
revoke all on public.guest_feedback, public.feedback_invitation_outbox from public, anon, authenticated;
grant all on public.guest_feedback, public.feedback_invitation_outbox to service_role;

create or replace function public.feedback_booking_eligible(p_booking_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    b public.bookings%rowtype;
    online_paid numeric := 0;
    desk_paid numeric := 0;
begin
    select * into b
    from public.bookings
    where id = p_booking_id;

    if not found then
        return false;
    end if;

    if not (
        lower(trim(coalesce(b.booking_status, ''))) in ('completed', 'checked out', 'checked-out', 'checked_out')
        or lower(trim(coalesce(b.stay_status, ''))) in ('completed', 'checked out', 'checked-out', 'checked_out')
    ) then
        return false;
    end if;

    if lower(trim(coalesce(b.booking_status, ''))) in
            ('cancelled', 'canceled', 'refunded', 'partially refunded', 'partially_refunded', 'invalid', 'invalidated', 'void', 'voided')
        or lower(trim(coalesce(b.stay_status, ''))) in
            ('cancelled', 'canceled', 'refunded', 'partially refunded', 'partially_refunded', 'invalid', 'invalidated', 'void', 'voided')
        or lower(trim(coalesce(b.payment_status, ''))) in
            ('cancelled', 'canceled', 'refunded', 'partially refunded', 'partially_refunded', 'invalid', 'invalidated', 'void', 'voided')
    then
        return false;
    end if;

    if coalesce(b.total_amount, 0) <= 0
        or coalesce(b.amount_paid, 0) + 0.01 < b.total_amount
        or coalesce(b.balance_amount, b.total_amount) > 0.01
    then
        return false;
    end if;

    if exists (
        select 1
        from public.booking_payments p
        where p.booking_id = p_booking_id
          and lower(trim(coalesce(p.status, ''))) in
              ('refunded', 'partially_refunded', 'partially refunded', 'reversed')
    ) or exists (
        select 1
        from public.front_desk_payments p
        where p.booking_id = p_booking_id
          and lower(trim(coalesce(p.status, ''))) in
              ('refunded', 'partially_refunded', 'partially refunded', 'reversed')
    ) then
        return false;
    end if;

    select coalesce(sum(p.amount), 0)
    into online_paid
    from public.booking_payments p
    where p.booking_id = p_booking_id
      and lower(trim(coalesce(p.status, ''))) in ('paid', 'succeeded', 'success', 'completed', 'complete');

    select coalesce(sum(p.room_balance_amount), 0)
    into desk_paid
    from public.front_desk_payments p
    where p.booking_id = p_booking_id
      and lower(trim(coalesce(p.status, ''))) in ('paid', 'succeeded', 'success', 'completed', 'complete');

    return online_paid + desk_paid + 0.01 >= b.total_amount;
end;
$$;

create or replace function public.queue_guest_feedback_invitation(
    p_booking_id uuid,
    p_nonce text,
    p_token_hash text
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    b public.bookings%rowtype;
begin
    if p_nonce is null or length(p_nonce) < 32 or length(p_nonce) > 200
        or p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
    then
        raise exception 'Invalid invitation capability';
    end if;

    select * into b
    from public.bookings
    where id = p_booking_id
    for update;

    if not found or not coalesce(public.feedback_booking_eligible(p_booking_id), false) then
        raise exception 'Booking is not eligible for feedback';
    end if;

    if exists (
        select 1 from public.guest_feedback f where f.booking_id = p_booking_id
    ) then
        return false;
    end if;

    if exists (
        select 1 from public.feedback_invitation_outbox o where o.booking_id = p_booking_id
    ) then
        return true;
    end if;

    if b.feedback_token_expires_at > now()
        and b.feedback_token_revoked_at is null
    then
        raise exception 'An active feedback token already exists; reconcile it before reissuing';
    end if;

    update public.bookings
    set feedback_token_hash = p_token_hash,
        feedback_token_expires_at = now() + interval '30 days',
        feedback_token_revoked_at = null,
        updated_at = now()
    where id = p_booking_id;

    insert into public.feedback_invitation_outbox (
        booking_id, token_nonce, message_id
    ) values (
        p_booking_id,
        p_nonce,
        format('<feedback-%s@thevilla.local>', p_booking_id)
    );

    return true;
end;
$$;

create or replace function public.guest_feedback_invitation_candidates()
returns setof public.bookings
language sql
security definer
set search_path = public, pg_temp
as $$
    select b.*
    from public.bookings b
    where public.feedback_booking_eligible(b.id)
      and not exists (
          select 1 from public.guest_feedback f where f.booking_id = b.id
      )
      and not exists (
          select 1 from public.feedback_invitation_outbox o where o.booking_id = b.id
      )
    order by b.created_at
    limit 200;
$$;

create or replace function public.claim_guest_feedback_invitation()
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    invitation public.feedback_invitation_outbox%rowtype;
    booking_row public.bookings%rowtype;
begin
    update public.feedback_invitation_outbox
    set status = 'uncertain',
        last_error = 'delivery_uncertain',
        claim_id = null,
        claim_expires_at = null,
        updated_at = now()
    where status = 'sending'
      and claim_expires_at <= now();

    select * into invitation
    from public.feedback_invitation_outbox
    where status in ('pending', 'retry')
      and next_attempt_at <= now()
    order by next_attempt_at, created_at
    for update skip locked
    limit 1;

    if not found then
        return null;
    end if;

    update public.feedback_invitation_outbox
    set status = 'sending',
        attempts = attempts + 1,
        claim_id = gen_random_uuid(),
        claim_expires_at = now() + interval '2 minutes',
        updated_at = now()
    where id = invitation.id
    returning * into invitation;

    select * into booking_row
    from public.bookings
    where id = invitation.booking_id;

    return jsonb_build_object(
        'booking', to_jsonb(booking_row),
        'token_nonce', invitation.token_nonce,
        'message_id', invitation.message_id,
        'claim_id', invitation.claim_id
    );
end;
$$;

create or replace function public.finish_guest_feedback_invitation(
    p_booking_id uuid,
    p_claim uuid,
    p_status text,
    p_error text default null
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    invitation public.feedback_invitation_outbox%rowtype;
begin
    if p_status not in ('accepted', 'retry', 'uncertain', 'suppressed') then
        raise exception 'Invalid invitation state';
    end if;

    update public.feedback_invitation_outbox
    set status = p_status,
        email_accepted_at = case when p_status = 'accepted' then now() else email_accepted_at end,
        last_error = nullif(left(coalesce(p_error, ''), 80), ''),
        next_attempt_at = case
            when p_status = 'retry' then now() + make_interval(
                secs => least(21600::numeric, 60 * power(2::numeric, least(attempts, 8)))::double precision
            )
            else next_attempt_at
        end,
        claim_id = null,
        claim_expires_at = null,
        updated_at = now()
    where booking_id = p_booking_id
      and claim_id = p_claim
      and status = 'sending'
    returning * into invitation;

    return found;
end;
$$;

create or replace function public.submit_verified_guest_feedback(
    p_booking_id uuid,
    p_token_hash text,
    p_feedback jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    b public.bookings%rowtype;
    comments_value text;
    overall_value integer;
    hide_value boolean;
    existing_id uuid;
begin
    select * into b
    from public.bookings
    where id = p_booking_id
    for update;

    if not found
        or b.feedback_token_hash is distinct from p_token_hash
        or b.feedback_token_revoked_at is not null
        or b.feedback_token_expires_at is null
        or b.feedback_token_expires_at <= now()
        or not coalesce(public.feedback_booking_eligible(p_booking_id), false)
    then
        raise exception 'Feedback link unavailable';
    end if;

    select id into existing_id
    from public.guest_feedback
    where booking_id = p_booking_id
    limit 1;

    if found then
        return jsonb_build_object('submitted', true, 'duplicate', true);
    end if;

    if p_feedback is null or jsonb_typeof(p_feedback) <> 'object' then
        raise exception 'Invalid feedback';
    end if;

    comments_value := trim(coalesce(p_feedback->>'comments', ''));
    if length(comments_value) not between 20 and 3000
        or cardinality(regexp_split_to_array(comments_value, '\s+')) < 4
        or coalesce(p_feedback->>'overall_rating', '') !~ '^[1-5]$'
    then
        raise exception 'Invalid feedback';
    end if;

    overall_value := (p_feedback->>'overall_rating')::integer;
    hide_value := coalesce((p_feedback->>'hide_identity')::boolean, false);

    if exists (
        select 1
        from unnest(array['cleanliness_rating', 'service_rating', 'villa_rating', 'value_rating']) as field_name
        where nullif(p_feedback->>field_name, '') is not null
          and (p_feedback->>field_name) !~ '^[1-5]$'
    ) then
        raise exception 'Invalid feedback rating';
    end if;

    if length(coalesce(p_feedback->>'private_note', '')) > 3000 then
        raise exception 'Invalid private note';
    end if;

    insert into public.guest_feedback (
        id, booking_id, booking_code, villa_id, villa_name,
        guest_name, guest_email, overall_rating, cleanliness_rating,
        service_rating, villa_rating, value_rating, would_recommend,
        comments, hide_identity, private_note, source, created_at
    ) values (
        gen_random_uuid(), p_booking_id, b.booking_code, b.villa_id, b.villa_name,
        case when hide_value then 'Anonymous guest' else b.customer_name end,
        case when hide_value then null else b.customer_email end,
        overall_value,
        nullif(p_feedback->>'cleanliness_rating', '')::integer,
        nullif(p_feedback->>'service_rating', '')::integer,
        nullif(p_feedback->>'villa_rating', '')::integer,
        nullif(p_feedback->>'value_rating', '')::integer,
        nullif(p_feedback->>'would_recommend', '')::boolean,
        comments_value, hide_value, nullif(p_feedback->>'private_note', ''),
        'verified_stay', now()
    );

    return jsonb_build_object('submitted', true, 'duplicate', false);
end;
$$;

create or replace function public.list_verified_guest_feedback()
returns setof public.guest_feedback
language sql
security definer
set search_path = public, pg_temp
as $$
    select f.*
    from public.guest_feedback f
    where f.source = 'verified_stay'
    order by f.created_at desc;
$$;

revoke all on function public.feedback_booking_eligible(uuid) from public, anon, authenticated;
revoke all on function public.queue_guest_feedback_invitation(uuid, text, text) from public, anon, authenticated;
revoke all on function public.guest_feedback_invitation_candidates() from public, anon, authenticated;
revoke all on function public.claim_guest_feedback_invitation() from public, anon, authenticated;
revoke all on function public.finish_guest_feedback_invitation(uuid, uuid, text, text) from public, anon, authenticated;
revoke all on function public.submit_verified_guest_feedback(uuid, text, jsonb) from public, anon, authenticated;
revoke all on function public.list_verified_guest_feedback() from public, anon, authenticated;

grant execute on function public.feedback_booking_eligible(uuid) to service_role;
grant execute on function public.queue_guest_feedback_invitation(uuid, text, text) to service_role;
grant execute on function public.guest_feedback_invitation_candidates() to service_role;
grant execute on function public.claim_guest_feedback_invitation() to service_role;
grant execute on function public.finish_guest_feedback_invitation(uuid, uuid, text, text) to service_role;
grant execute on function public.submit_verified_guest_feedback(uuid, text, jsonb) to service_role;
grant execute on function public.list_verified_guest_feedback() to service_role;

commit;
