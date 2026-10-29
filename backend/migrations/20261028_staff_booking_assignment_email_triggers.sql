-- Queue eligible assignment emails for both new assignments and later profile updates.
begin;

create or replace function public.queue_staff_assignment_emails()
returns integer language plpgsql security definer set search_path = public
as $$
declare added integer;
begin
    insert into public.staff_assignment_email_outbox(task_id, recipient_staff_account_id)
    select t.id, t.assigned_staff_id
    from public.admin_tasks t
    join public.staff_accounts s on s.id = t.assigned_staff_id
    where t.status in ('Pending', 'In Progress', 'Pending Review')
      and lower(s.role::text) = 'staff'
      and s.is_active is true
      and lower(s.account_status::text) = 'active'
      and coalesce(trim(s.personal_email), '') <> ''
    on conflict (task_id, recipient_staff_account_id) do nothing;
    get diagnostics added = row_count;
    return added;
end;
$$;

create or replace function public.queue_staff_assignment_email_on_task()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
    if new.status in ('Pending', 'In Progress', 'Pending Review') then
        insert into public.staff_assignment_email_outbox(task_id, recipient_staff_account_id)
        select new.id, s.id
        from public.staff_accounts s
        where s.id = new.assigned_staff_id
          and lower(s.role::text) = 'staff'
          and s.is_active is true
          and lower(s.account_status::text) = 'active'
          and coalesce(trim(s.personal_email), '') <> ''
        on conflict (task_id, recipient_staff_account_id) do nothing;
    end if;
    return new;
exception when others then
    raise warning 'Staff assignment email could not be queued; reconciliation required';
    return new;
end;
$$;

drop trigger if exists queue_staff_assignment_email on public.admin_tasks;
create trigger queue_staff_assignment_email
after insert or update of assigned_staff_id on public.admin_tasks
for each row execute function public.queue_staff_assignment_email_on_task();

create or replace function public.queue_staff_assignments_for_personal_email()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
    if coalesce(trim(new.personal_email), '') <> ''
       and lower(new.role::text) = 'staff'
       and new.is_active is true
       and lower(new.account_status::text) = 'active' then
        insert into public.staff_assignment_email_outbox(task_id, recipient_staff_account_id)
        select t.id, new.id
        from public.admin_tasks t
        where t.assigned_staff_id = new.id
          and t.status in ('Pending', 'In Progress', 'Pending Review')
        on conflict (task_id, recipient_staff_account_id) do nothing;
    end if;
    return new;
exception when others then
    raise warning 'Staff assignments could not be queued after personal email update; reconciliation required';
    return new;
end;
$$;

drop trigger if exists queue_staff_assignments_after_personal_email on public.staff_accounts;
create trigger queue_staff_assignments_after_personal_email
after insert or update of personal_email on public.staff_accounts
for each row execute function public.queue_staff_assignments_for_personal_email();

insert into public.staff_assignment_email_outbox(task_id, recipient_staff_account_id)
select t.id, t.assigned_staff_id
from public.admin_tasks t
join public.staff_accounts s on s.id = t.assigned_staff_id
where t.status in ('Pending', 'In Progress', 'Pending Review')
  and lower(s.role::text) = 'staff'
  and s.is_active is true
  and lower(s.account_status::text) = 'active'
  and coalesce(trim(s.personal_email), '') <> ''
on conflict (task_id, recipient_staff_account_id) do nothing;

revoke all on function public.queue_staff_assignment_emails() from public, anon, authenticated;
revoke all on function public.queue_staff_assignment_email_on_task() from public, anon, authenticated;
revoke all on function public.queue_staff_assignments_for_personal_email() from public, anon, authenticated;
grant execute on function public.queue_staff_assignment_emails() to service_role;

commit;
