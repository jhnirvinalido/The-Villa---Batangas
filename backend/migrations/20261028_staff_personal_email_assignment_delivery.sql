    -- Send staff assignment email only to the personal address entered in the staff profile.
    begin;

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
        and coalesce(trim(s.personal_email),'') <> ''
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
            and coalesce(trim(s.personal_email),'') <> ''
            on conflict (task_id,recipient_staff_account_id) do nothing;
        end if;
        return new;
    exception when others then
        raise warning 'Staff assignment email could not be queued; reconciliation required';
        return new;
    end;
    $$;

    commit;
