begin;
alter table public.staff_accounts add column if not exists personal_email text;
comment on column public.staff_accounts.personal_email is 'Staff-provided notification address, separate from the login email.';
commit;
