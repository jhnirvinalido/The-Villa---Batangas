begin;

update public.villa_catalog as villa
set status = 'Available',
    updated_at = now()
where villa.id = 'villa-1'
  and lower(trim(coalesce(villa.status, ''))) = 'under maintenance'
  and not exists (
      select 1
      from public.admin_tasks as task
      where task.source = 'manual-maintenance-request'
        and task.status not in ('Completed', 'Cancelled')
        and exists (
            select 1
            from jsonb_array_elements(
                coalesce(task.status_history, '[]'::jsonb)
            ) as event
            where event->'maintenance'->>'villaId' = 'villa-1'
              and event->'maintenance'->>'blocksBooking' = 'true'
        )
  );

commit;
