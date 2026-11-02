-- DESTRUCTIVE RESET, authorized scope:
-- Remove bookings/payment records, all tasks/assignments/messages/notifications,
-- staff and maintenance accounts AND their Supabase Auth logins.
-- Preserve admin accounts, villa catalog, guest/companion feedback, ML data,
-- feedback reports and analysis jobs. Does not refund/cancel PayMongo payments.
--
-- Before running: stop local backend and SUSPEND the Render service so workers
-- cannot recreate operational records. Run as postgres in Supabase SQL Editor.
-- Run the ENTIRE file together. Any error rolls back all changes.
-- A private reset_backup_<timestamp> schema retains pre-reset table copies.
-- Guest feedback booking_id, companion invitation booking_id, and references
-- from retained reports to deleted staff become NULL. Old invitation links stop
-- working. The original associations remain in the backup.
-- Verified feedback also retains an archived_booking_id pointing to a private
-- booking snapshot, so its verified-stay provenance is not discarded.

begin;
set local lock_timeout = '10s';
set local statement_timeout = '120s';

do $reset$
declare
  backup_schema text := 'reset_backup_' || to_char(clock_timestamp(), 'YYYYMMDD_HH24MISS_US');
  table_name text;
  trigger_row record;
  retained record;
  auth_id uuid;
  count_before bigint;
  count_after bigint;
  mismatch boolean;
  feedback_check text;
  tables text[] := array[
    'bookings','booking_payments','booking_checkout_attempts',
    'booking_workflow_events','front_desk_payment_intents',
    'front_desk_payment_approval_requests',
    'front_desk_payments','front_desk_payment_items',
    'admin_tasks','staff_messages','admin_notifications',
    'staff_assignment_email_outbox','feedback_invitation_outbox',
    'public_booking_checkouts','manual_booking_checkouts',
    'staff_accounts','staff_settings','admin_settings','profiles','villa_catalog',
    'guest_feedback','companion_feedback','companion_feedback_invitations',
    'feedback_recommendation_reports','feedback_recommendation_jobs','feedback_analysis_jobs'
  ];
begin
  if not exists(select 1 from public.staff_accounts where lower(role::text)='admin') then
    raise exception 'No admin account found. Reset cancelled.';
  end if;
  if exists(select 1 from public.staff_accounts where role is null or lower(role::text) not in ('admin','staff','maintenance','front_desk')) then
    raise exception 'Unexpected staff role. Reset cancelled for review.';
  end if;

  -- Block concurrent mutations while taking the backup and doing the reset.
  foreach table_name in array tables loop
    if to_regclass(format('public.%I',table_name)) is not null then
      execute format('lock table public.%I in share row exclusive mode',table_name);
    end if;
  end loop;
  lock table auth.users in share row exclusive mode;

  create temporary table reset_staff on commit drop as
    select id,auth_user_id from public.staff_accounts where lower(role::text) in ('staff','maintenance','front_desk');
  if exists(select 1 from reset_staff s join public.staff_accounts a
            on a.auth_user_id=s.auth_user_id where lower(a.role::text)='admin') then
    raise exception 'A staff account shares an admin login. Reset cancelled.';
  end if;
  create temporary table reset_admins on commit drop as
    select id,auth_user_id from public.staff_accounts where lower(role::text)='admin';
  create temporary table reset_admin_auth on commit drop as
    select u.id,to_jsonb(u) as payload from auth.users u
    where u.id in (select auth_user_id from reset_admins);

  execute format('create schema %I',backup_schema);
  execute format('revoke all on schema %I from public,anon,authenticated,service_role',backup_schema);
  foreach table_name in array tables loop
    if to_regclass(format('public.%I',table_name)) is not null then
      execute format('create table %I.%I as table public.%I',backup_schema,table_name,table_name);
      execute format('revoke all on table %I.%I from public,anon,authenticated,service_role',backup_schema,table_name);
    end if;
  end loop;
  -- Only staff user credentials/identities are backed up, never printed.
  execute format('create table %I.staff_auth_users as select u.* from auth.users u where u.id in (select auth_user_id from reset_staff)',backup_schema);
  execute format('create table %I.staff_auth_identities as select i.* from auth.identities i where i.user_id in (select auth_user_id from reset_staff)',backup_schema);
  execute format('revoke all on all tables in schema %I from public,anon,authenticated,service_role',backup_schema);

  -- Disable only business triggers, keeping every FK constraint enforced.
  create temporary table reset_triggers on commit drop as
    select c.relname as table_name,t.tgname,t.tgenabled
    from pg_trigger t join pg_class c on c.oid=t.tgrelid
    join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname=any(tables) and not t.tgisinternal;
  for trigger_row in select * from reset_triggers loop
    execute format('alter table public.%I disable trigger %I',trigger_row.table_name,trigger_row.tgname);
  end loop;

  -- Preserve feedback before deleting any parent bookings.
  if to_regclass('public.guest_feedback') is not null then
    -- Keep evidence for verified-stay feedback outside the active bookings table.
    -- This is not a relabel to historical/imported feedback and does not weaken
    -- the rule for NEW verified feedback without either form of booking evidence.
    create schema if not exists villa_feedback_archive;
    revoke all on schema villa_feedback_archive from public,anon,authenticated,service_role;
    create table if not exists villa_feedback_archive.booking_snapshots (
      booking_id uuid primary key,
      booking_snapshot jsonb not null,
      archived_at timestamptz not null default now(),
      reset_backup_schema text not null
    );
    revoke all on all tables in schema villa_feedback_archive from public,anon,authenticated,service_role;
    insert into villa_feedback_archive.booking_snapshots(booking_id,booking_snapshot,reset_backup_schema)
      select b.id,to_jsonb(b),backup_schema from public.bookings b
      where exists(select 1 from public.guest_feedback f where f.booking_id=b.id)
      on conflict(booking_id) do nothing;
    alter table public.guest_feedback add column if not exists archived_booking_id uuid;
    if not exists(select 1 from pg_constraint where conrelid='public.guest_feedback'::regclass
                  and conname='guest_feedback_archived_booking_id_fkey') then
      alter table public.guest_feedback add constraint guest_feedback_archived_booking_id_fkey
        foreign key(archived_booking_id) references villa_feedback_archive.booking_snapshots(booking_id)
        on delete restrict;
    end if;
    -- Preserve the deployed check expression, adding a narrowly scoped archived
    -- verified-stay case. Other source rules remain exactly as deployed.
    select pg_get_expr(conbin,conrelid) into feedback_check from pg_constraint
      where conrelid='public.guest_feedback'::regclass
        and conname='guest_feedback_source_booking_check' and contype='c';
    if feedback_check is null then
      raise exception 'Expected guest feedback provenance constraint is missing. Reset cancelled.';
    end if;
    if position('archived_booking_id' in feedback_check)=0 then
      alter table public.guest_feedback drop constraint guest_feedback_source_booking_check;
      execute format('alter table public.guest_feedback add constraint guest_feedback_source_booking_check check ((%s) or (source::text = ''verified_stay'' and booking_id is null and archived_booking_id is not null))', feedback_check);
    end if;
    alter table public.guest_feedback alter column booking_id drop not null;
    update public.guest_feedback set archived_booking_id=booking_id,booking_id=null where booking_id is not null;
  end if;
  if to_regclass('public.companion_feedback_invitations') is not null then
    alter table public.companion_feedback_invitations alter column booking_id drop not null;
    update public.companion_feedback_invitations set booking_id=null where booking_id is not null;
  end if;
  if to_regclass('public.feedback_recommendation_reports') is not null then
    alter table public.feedback_recommendation_reports alter column created_by_staff_id drop not null;
    alter table public.feedback_recommendation_reports alter column approved_by_staff_id drop not null;
    update public.feedback_recommendation_reports set created_by_staff_id=null
      where created_by_staff_id in (select id from reset_staff);
    update public.feedback_recommendation_reports set approved_by_staff_id=null
      where approved_by_staff_id in (select id from reset_staff);
  end if;

  foreach table_name in array array[
    'staff_assignment_email_outbox','staff_messages','admin_notifications',
    'admin_tasks','feedback_invitation_outbox','booking_workflow_events',
    'front_desk_payment_items','front_desk_payment_intents',
    'front_desk_payment_approval_requests','front_desk_payments',
    'booking_checkout_attempts','booking_payments',
    'public_booking_checkouts','manual_booking_checkouts','bookings'
  ] loop
    if to_regclass(format('public.%I',table_name)) is not null then
      execute format('delete from public.%I',table_name);
    end if;
  end loop;

  -- Remove staff settings but leave admin settings and admin accounts in place.
  foreach table_name in array array['staff_settings','admin_settings'] loop
    if to_regclass(format('public.%I',table_name)) is not null then
      execute format('delete from public.%I where staff_account_id in (select id from reset_staff)',table_name);
    end if;
  end loop;
  delete from public.staff_accounts where id in (select id from reset_staff);
  for auth_id in select distinct auth_user_id from reset_staff where auth_user_id is not null loop
    delete from auth.users where id=auth_id;
  end loop;

  -- Compare retained contents, excluding only the intentionally detached links.
  for retained in select * from (values
    ('guest_feedback',array['booking_id','archived_booking_id']::text[]),
    ('companion_feedback',array[]::text[]),
    ('companion_feedback_invitations',array['booking_id']::text[]),
    ('feedback_recommendation_reports',array['created_by_staff_id','approved_by_staff_id']::text[]),
    ('feedback_analysis_jobs',array[]::text[])
  ) as expected(name,ignored_columns) loop
    if to_regclass(format('public.%I',retained.name)) is not null then
      execute format('select count(*) from %I.%I',backup_schema,retained.name) into count_before;
      execute format('select count(*) from public.%I',retained.name) into count_after;
      execute format(
        'select exists ((select to_jsonb(x)-$1 from public.%I x except all select to_jsonb(y)-$1 from %I.%I y) union all (select to_jsonb(y)-$1 from %I.%I y except all select to_jsonb(x)-$1 from public.%I x))',
        retained.name,backup_schema,retained.name,backup_schema,retained.name,retained.name
      ) into mismatch using retained.ignored_columns;
      if count_before<>count_after or mismatch then
        raise exception 'Preservation check failed for %. All changes rolled back.',retained.name;
      end if;
    end if;
  end loop;
  if exists(select 1 from reset_admins old left join public.staff_accounts a on a.id=old.id
            where a.id is null or lower(a.role::text)<>'admin' or a.auth_user_id is distinct from old.auth_user_id)
     or exists(select 1 from reset_admin_auth old left join auth.users u on u.id=old.id
               where u.id is null or to_jsonb(u) is distinct from old.payload) then
    raise exception 'Admin preservation check failed. All changes rolled back.';
  end if;
  if exists(select 1 from public.bookings) or exists(select 1 from public.admin_tasks)
     or exists(select 1 from public.staff_accounts where lower(role::text)<>'admin')
     or exists(select 1 from auth.users where id in (select auth_user_id from reset_staff)) then
    raise exception 'Operational records remain. All changes rolled back.';
  end if;

  -- Restore each trigger's exact prior state, including disabled/replica modes.
  for trigger_row in select * from reset_triggers loop
    execute format('alter table public.%I %s trigger %I',trigger_row.table_name,
      case trigger_row.tgenabled when 'D' then 'disable' when 'R' then 'enable replica'
        when 'A' then 'enable always' else 'enable' end,trigger_row.tgname);
  end loop;
  raise notice 'Reset complete. Private backup schema: %. Admin and feedback preservation checks passed.',backup_schema;
end;
$reset$;

commit;

select 'bookings' as category,count(*) as remaining from public.bookings
union all select 'tasks / assignments',count(*) from public.admin_tasks
union all select 'admin accounts',count(*) from public.staff_accounts where lower(role::text)='admin'
union all select 'staff / maintenance accounts',count(*) from public.staff_accounts where lower(role::text)<>'admin';
