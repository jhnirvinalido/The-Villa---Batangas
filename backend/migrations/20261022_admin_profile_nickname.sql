-- Nicknames are separate from usernames used for sign-in.
alter table public.staff_accounts add column if not exists nickname text;
