-- READ ONLY: run in Supabase SQL Editor before preparing the data reset.
-- Contains schema metadata and counts only, no credentials or guest details.
begin read only;

-- Actual foreign keys, including cascade paths and nullable columns.
select
    con.conrelid::regclass::text as child_table,
    con.confrelid::regclass::text as parent_table,
    con.conname as constraint_name,
    pg_get_constraintdef(con.oid) as definition,
    (select jsonb_object_agg(att.attname, not att.attnotnull)
       from unnest(con.conkey) as k(attnum)
       join pg_attribute att on att.attrelid=con.conrelid and att.attnum=k.attnum
    ) as child_column_nullable
from pg_constraint con
join pg_namespace ns on ns.oid=con.connamespace
where con.contype='f'
  and (ns.nspname='public' or con.confrelid='auth.users'::regclass)
order by parent_table,child_table;

-- Business triggers may recreate assignments or notifications during a reset.
select c.oid::regclass::text as table_name, t.tgname,
       pg_get_triggerdef(t.oid) as trigger_definition,
       pg_get_functiondef(t.tgfoid) as function_definition
from pg_trigger t
join pg_class c on c.oid=t.tgrelid
join pg_namespace n on n.oid=c.relnamespace
where not t.tgisinternal and n.nspname='public'
  and c.relname in (
    'bookings','staff_accounts','admin_tasks','staff_messages',
    'admin_notifications','guest_feedback','companion_feedback',
    'companion_feedback_invitations','booking_payments',
    'front_desk_payments','profiles'
  )
order by table_name,t.tgname;

-- Exact counts, safely accommodating optional tables/migrations.
select name as table_name,
  case when to_regclass(format('public.%I', name)) is not null then
    ((xpath('/row/c/text()', query_to_xml(
      format('select count(*) as c from public.%I', name), false, true, ''
    )))[1]::text)::bigint
  else null end as row_count
from unnest(array[
  'bookings','booking_payments','front_desk_payments','front_desk_payment_items',
  'front_desk_payment_intents','booking_workflow_events','admin_tasks',
  'front_desk_payment_approval_requests',
  'staff_accounts','staff_settings','admin_settings','staff_messages',
  'admin_notifications','staff_assignment_email_outbox','feedback_invitation_outbox',
  'public_booking_checkouts','manual_booking_checkouts','guest_feedback',
  'companion_feedback','companion_feedback_invitations',
  'feedback_recommendation_reports','feedback_recommendation_jobs','feedback_analysis_jobs','profiles'
]) as tables(name)
order by name;

select lower(coalesce(role::text,'')) as role, count(*) as accounts
from public.staff_accounts group by lower(coalesce(role::text,'')) order by role;

commit;
