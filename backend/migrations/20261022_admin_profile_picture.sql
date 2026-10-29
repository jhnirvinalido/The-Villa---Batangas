-- Profile photos are resized JPEGs saved with the staff account.
alter table public.staff_accounts add column if not exists avatar_url text;
