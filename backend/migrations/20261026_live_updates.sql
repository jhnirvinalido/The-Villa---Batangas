-- Add existing application tables to Supabase Realtime. Run after application
-- schema migrations. Database rows are consumed only by the backend service role.
-- This migration does NOT grant clients new SELECT permissions or weaken RLS.
begin;
do $$
declare table_name text;
begin
    if not exists(select 1 from pg_publication where pubname='supabase_realtime') then
        create publication supabase_realtime;
    end if;
    foreach table_name in array array[
        'villa_catalog','bookings','booking_payments','front_desk_payments',
        'front_desk_payment_items','front_desk_payment_intents','booking_workflow_events',
        'admin_tasks','admin_notifications','staff_messages','staff_accounts',
        'profiles','staff_settings','admin_settings','guest_feedback',
        'feedback_recommendation_reports','feedback_analysis_jobs',
        'feedback_invitation_outbox','staff_assignment_email_outbox'
    ] loop
        if to_regclass('public.' || table_name) is not null and not exists (
            select 1 from pg_publication_tables p where p.pubname='supabase_realtime'
                and p.schemaname='public' and p.tablename=table_name
        ) then
            execute format('alter publication supabase_realtime add table public.%I', table_name);
        end if;
    end loop;
end $$;
commit;
