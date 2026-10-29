-- Queue active assignments when a staff member saves a personal email.
-- This covers tasks assigned before the notification address was provided.
begin;

create or replace function public.queue_staff_assignments_for_personal_email()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
    if coalesce(trim(new.personal_email), '') <> ''
       and lower(new.role) = 'staff'
       and new.is_active is true
       and lower(new.account_status) = 'active' then
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

revoke all on function public.queue_staff_assignments_for_personal_email() from public, anon, authenticated;

commit;
