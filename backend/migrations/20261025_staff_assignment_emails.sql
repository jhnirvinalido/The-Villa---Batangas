-- Apply in Supabase SQL Editor before enabling assignment email delivery.
-- Existing task/notification APIs remain usable without this migration.
begin;

create table if not exists public.staff_assignment_email_outbox (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null references public.admin_tasks(id) on delete cascade,
    recipient_staff_account_id uuid not null references public.staff_accounts(id) on delete cascade,
    status text not null default 'pending' check (status in ('pending','sending','retry','accepted','suppressed','failed','uncertain')),
    attempts integer not null default 0,
    next_attempt_at timestamptz not null default now(),
    lease_token uuid,
    lease_expires_at timestamptz,
    accepted_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(task_id, recipient_staff_account_id)
);
alter table public.staff_assignment_email_outbox enable row level security;
revoke all on public.staff_assignment_email_outbox from anon, authenticated;
grant all on public.staff_assignment_email_outbox to service_role;
create index if not exists staff_assignment_email_ready_idx
    on public.staff_assignment_email_outbox(status, next_attempt_at);

-- Reconciliation also recovers a missed trigger; one email per task / recipient.
create or replace function public.queue_staff_assignment_emails()
returns integer language plpgsql security definer set search_path = public
as $$
declare added integer;
begin
    insert into public.staff_assignment_email_outbox(task_id,recipient_staff_account_id)
    select t.id,t.assigned_staff_id
    from public.admin_tasks t
    join public.staff_accounts s on s.id=t.assigned_staff_id
    where t.status in ('Pending','In Progress','Pending Review')
      and lower(s.role)='staff' and s.is_active is true and lower(s.account_status)='active'
      and coalesce(trim(s.email),'') <> ''
    on conflict (task_id,recipient_staff_account_id) do nothing;
    get diagnostics added = row_count;
    return added;
end;
$$;

create or replace function public.queue_staff_assignment_email_on_task()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
    if new.status in ('Pending','In Progress','Pending Review') then
        insert into public.staff_assignment_email_outbox(task_id,recipient_staff_account_id)
        select new.id,s.id from public.staff_accounts s
        where s.id=new.assigned_staff_id and lower(s.role)='staff'
          and s.is_active is true and lower(s.account_status)='active'
          and coalesce(trim(s.email),'') <> ''
        on conflict (task_id,recipient_staff_account_id) do nothing;
    end if;
    return new;
exception when others then
    -- The reconciler recovers this; email must never roll back a task assignment.
    raise warning 'Staff assignment email could not be queued; reconciliation required';
    return new;
end;
$$;
drop trigger if exists queue_staff_assignment_email on public.admin_tasks;
create trigger queue_staff_assignment_email after insert or update of assigned_staff_id
    on public.admin_tasks for each row execute function public.queue_staff_assignment_email_on_task();

create or replace function public.claim_staff_assignment_emails(p_limit integer default 10)
returns setof public.staff_assignment_email_outbox
language plpgsql security definer set search_path = public
as $$
begin
    -- A process may have died after SMTP acceptance: do not automatically resend.
    update public.staff_assignment_email_outbox
       set status='uncertain',last_error='Worker lease expired; review before resending',
           lease_token=null,lease_expires_at=null,updated_at=now()
     where status='sending' and lease_expires_at < now();
    return query
    with ready as (
        select o.id from public.staff_assignment_email_outbox o
        where o.status in ('pending','retry') and o.next_attempt_at <= now()
        order by o.created_at,o.id
        for update skip locked limit greatest(1,least(p_limit,50))
    )
    update public.staff_assignment_email_outbox o
       set status='sending',attempts=o.attempts+1,lease_token=gen_random_uuid(),
           lease_expires_at=now()+interval '10 minutes',updated_at=now()
      from ready where o.id=ready.id returning o.*;
end;
$$;

create or replace function public.finish_staff_assignment_email(
    p_id uuid,p_lease uuid,p_status text,p_error text default null
) returns boolean language plpgsql security definer set search_path = public
as $$
declare changed integer;
begin
    if p_status not in ('retry','accepted','suppressed','failed','uncertain') then
        raise exception 'Invalid email delivery status';
    end if;
    update public.staff_assignment_email_outbox
       set status=case when p_status='retry' and attempts>=5 then 'failed' else p_status end,
           accepted_at=case when p_status='accepted' then now() else accepted_at end,
           next_attempt_at=now()+make_interval(secs=>least(3600,60*power(2,least(attempts,6)))::integer),
           last_error=left(p_error,160),lease_token=null,lease_expires_at=null,updated_at=now()
     where id=p_id and status='sending' and lease_token=p_lease;
    get diagnostics changed = row_count;
    return changed=1;
end;
$$;

revoke all on function public.queue_staff_assignment_emails() from public,anon,authenticated;
revoke all on function public.queue_staff_assignment_email_on_task() from public,anon,authenticated;
revoke all on function public.claim_staff_assignment_emails(integer) from public,anon,authenticated;
revoke all on function public.finish_staff_assignment_email(uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.queue_staff_assignment_emails() to service_role;
grant execute on function public.claim_staff_assignment_emails(integer) to service_role;
grant execute on function public.finish_staff_assignment_email(uuid,uuid,text,text) to service_role;
commit;
