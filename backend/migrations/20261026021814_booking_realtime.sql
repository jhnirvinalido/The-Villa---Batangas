-- Publish checkout drafts and feedback outbox changes for backend-only realtime.
-- The server emits scoped invalidations; table rows are never sent to guests.
begin;
do $$
declare table_name text;
begin
    if not exists (
        select 1 from pg_publication where pubname = 'supabase_realtime'
    ) then
        create publication supabase_realtime;
    end if;

    foreach table_name in array array[
        'public_booking_checkouts',
        'manual_booking_checkouts',
        'feedback_invitation_outbox'
    ] loop
        if to_regclass('public.' || table_name) is not null and not exists (
            select 1 from pg_publication_tables p
            where p.pubname = 'supabase_realtime'
              and p.schemaname = 'public'
              and p.tablename = table_name
        ) then
            execute format(
                'alter publication supabase_realtime add table public.%I',
                table_name
            );
        end if;
    end loop;
end $$;
commit;
