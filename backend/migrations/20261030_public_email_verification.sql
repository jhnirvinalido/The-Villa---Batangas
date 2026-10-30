-- Store only keyed email/code hashes for guest booking email verification.
begin;

create table if not exists public.public_email_verifications (
    email_hash text primary key,
    code_hash text not null,
    expires_at timestamptz not null,
    last_sent_at timestamptz not null,
    send_window_started_at timestamptz not null,
    sends_in_window integer not null default 1,
    attempts integer not null default 0,
    verified_at timestamptz
);

create table if not exists public.public_email_verification_ip_limits (
    ip_hash text primary key,
    window_started_at timestamptz not null,
    sends_in_window integer not null default 1
);

alter table public.public_email_verifications enable row level security;
alter table public.public_email_verification_ip_limits enable row level security;
revoke all on public.public_email_verifications from public, anon, authenticated;
revoke all on public.public_email_verification_ip_limits from public, anon, authenticated;
grant all on public.public_email_verifications to service_role;
grant all on public.public_email_verification_ip_limits to service_role;

create index if not exists public_email_verifications_expires_idx
    on public.public_email_verifications (expires_at);
create index if not exists public_email_verification_ip_limits_window_idx
    on public.public_email_verification_ip_limits (window_started_at);

create or replace function public.issue_public_email_verification(
    p_email_hash text,
    p_code_hash text,
    p_ip_hash text,
    p_now timestamptz,
    p_expires_at timestamptz
) returns text
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    ip_allowed boolean := false;
    email_issued boolean := false;
    previous_send timestamptz;
begin
    insert into public.public_email_verification_ip_limits (
        ip_hash, window_started_at, sends_in_window
    ) values (p_ip_hash, p_now, 1)
    on conflict (ip_hash) do update
      set window_started_at = case
            when public.public_email_verification_ip_limits.window_started_at <= p_now - interval '1 hour'
              then p_now
            else public.public_email_verification_ip_limits.window_started_at
          end,
          sends_in_window = case
            when public.public_email_verification_ip_limits.window_started_at <= p_now - interval '1 hour'
              then 1
            else public.public_email_verification_ip_limits.sends_in_window + 1
          end
      where public.public_email_verification_ip_limits.window_started_at <= p_now - interval '1 hour'
         or public.public_email_verification_ip_limits.sends_in_window < 10
    returning true into ip_allowed;

    if not coalesce(ip_allowed, false) then
        return 'ip_rate_limited';
    end if;

    delete from public.public_email_verifications
      where expires_at < p_now - interval '1 day';
    delete from public.public_email_verification_ip_limits
      where window_started_at < p_now - interval '2 days';

    insert into public.public_email_verifications (
        email_hash, code_hash, expires_at, last_sent_at,
        send_window_started_at, sends_in_window, attempts, verified_at
    ) values (
        p_email_hash, p_code_hash, p_expires_at, p_now,
        p_now, 1, 0, null
    )
    on conflict (email_hash) do update
      set code_hash = excluded.code_hash,
          expires_at = excluded.expires_at,
          last_sent_at = excluded.last_sent_at,
          send_window_started_at = case
            when public.public_email_verifications.send_window_started_at <= p_now - interval '1 hour'
              then p_now
            else public.public_email_verifications.send_window_started_at
          end,
          sends_in_window = case
            when public.public_email_verifications.send_window_started_at <= p_now - interval '1 hour'
              then 1
            else public.public_email_verifications.sends_in_window + 1
          end,
          attempts = 0,
          verified_at = null
      where public.public_email_verifications.last_sent_at <= p_now - interval '1 minute'
        and (
          public.public_email_verifications.send_window_started_at <= p_now - interval '1 hour'
          or public.public_email_verifications.sends_in_window < 5
        )
    returning true into email_issued;

    if coalesce(email_issued, false) then
        return 'sent';
    end if;

    select last_sent_at into previous_send
      from public.public_email_verifications
      where email_hash = p_email_hash;
    if previous_send > p_now - interval '1 minute' then
        return 'cooldown';
    end if;
    return 'email_rate_limited';
end;
$$;

create or replace function public.verify_public_email_verification(
    p_email_hash text,
    p_code_hash text,
    p_now timestamptz
) returns text
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    verification public.public_email_verifications%rowtype;
begin
    select * into verification
      from public.public_email_verifications
      where email_hash = p_email_hash
      for update;

    if not found or verification.expires_at <= p_now then
        return 'expired';
    end if;
    if verification.attempts >= 5 then
        return 'locked';
    end if;
    if verification.code_hash <> p_code_hash then
        update public.public_email_verifications
          set attempts = attempts + 1
          where email_hash = p_email_hash;
        return 'invalid';
    end if;
    if verification.verified_at is not null then
        return 'verified';
    else
        update public.public_email_verifications
          set verified_at = p_now
          where email_hash = p_email_hash;
        return 'verified';
    end if;
end;
$$;

revoke all on function public.issue_public_email_verification(text,text,text,timestamptz,timestamptz) from public, anon, authenticated;
revoke all on function public.verify_public_email_verification(text,text,timestamptz) from public, anon, authenticated;
grant execute on function public.issue_public_email_verification(text,text,text,timestamptz,timestamptz) to service_role;
grant execute on function public.verify_public_email_verification(text,text,timestamptz) to service_role;

commit;
