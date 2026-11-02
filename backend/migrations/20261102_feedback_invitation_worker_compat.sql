-- Align pre-existing feedback outboxes with the worker's lease columns.
begin;

alter table public.feedback_invitation_outbox
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists claim_id uuid,
    add column if not exists claim_expires_at timestamptz,
    add column if not exists email_accepted_at timestamptz,
    add column if not exists last_error text,
    add column if not exists updated_at timestamptz default now();

update public.feedback_invitation_outbox
set id = coalesce(id, gen_random_uuid()),
    updated_at = coalesce(updated_at, now())
where id is null or updated_at is null;

alter table public.feedback_invitation_outbox
    alter column id set default gen_random_uuid(),
    alter column id set not null,
    alter column updated_at set default now(),
    alter column updated_at set not null;

create unique index if not exists feedback_invitation_outbox_id_key
    on public.feedback_invitation_outbox (id);

commit;
