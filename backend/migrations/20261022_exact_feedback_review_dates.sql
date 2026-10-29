-- Original review date, when known. Never substitute the historical import time.
begin;
alter table public.guest_feedback add column if not exists review_date date;
comment on column public.guest_feedback.review_date is
 'Original review date when known. Null means the historical source only supplied month/year.';
commit;
