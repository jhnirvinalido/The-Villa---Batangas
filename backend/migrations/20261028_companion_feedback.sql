-- Apply after the existing post-stay feedback schema. Companion feedback is
-- internal only and never inserted into guest_feedback or its public aggregates.
begin;
create table if not exists public.companion_feedback_invitations (
 id uuid primary key default gen_random_uuid(),
 booking_id uuid not null references public.bookings(id) on delete cascade,
 slot integer not null check(slot > 0),
 token_hash text not null,
 parent_token_hash text not null,
 expires_at timestamptz not null,
 created_at timestamptz not null default now(),
 unique(booking_id,slot)
);
create table if not exists public.companion_feedback (
 id uuid primary key default gen_random_uuid(),
 invitation_id uuid not null unique references public.companion_feedback_invitations(id) on delete cascade,
 overall_rating integer not null check(overall_rating between 1 and 5),
 cleanliness_rating integer check(cleanliness_rating between 1 and 5),
 service_rating integer check(service_rating between 1 and 5),
 villa_rating integer check(villa_rating between 1 and 5),
 value_rating integer check(value_rating between 1 and 5),
 would_recommend boolean,
 comments text not null check(length(trim(comments)) between 20 and 3000),
 hide_identity boolean not null default true,
 private_note text check(length(private_note)<=3000),
 created_at timestamptz not null default now()
);
alter table public.companion_feedback_invitations enable row level security;
alter table public.companion_feedback enable row level security;
revoke all on public.companion_feedback_invitations,public.companion_feedback from public,anon,authenticated;
grant all on public.companion_feedback_invitations,public.companion_feedback to service_role;

create or replace function public.issue_companion_feedback_links(p_booking_id uuid,p_parent_hash text,p_tokens jsonb)
returns jsonb language plpgsql security definer set search_path=public as $$
declare b public.bookings%rowtype; t jsonb; capacity integer;
begin
 select * into b from public.bookings where id=p_booking_id for update;
 if not found then raise exception 'Invalid booking'; end if;
 if b.feedback_token_hash is distinct from p_parent_hash or b.feedback_token_revoked_at is not null
    or b.feedback_token_expires_at is null or b.feedback_token_expires_at <= now()
    or not coalesce(public.feedback_booking_eligible(p_booking_id),false) then
   raise exception 'Feedback link unavailable';
 end if;
 capacity:=greatest(coalesce(b.guest_count,1)-1,0);
 if jsonb_typeof(p_tokens)<>'array' or jsonb_array_length(p_tokens)<>capacity then raise exception 'Guest count changed'; end if;
 for t in select value from jsonb_array_elements(p_tokens) loop
   if (t->>'slot')::integer not between 1 and capacity or length(t->>'token_hash')<>64 then raise exception 'Invalid invitation'; end if;
   insert into public.companion_feedback_invitations(booking_id,slot,token_hash,parent_token_hash,expires_at)
   values(p_booking_id,(t->>'slot')::integer,t->>'token_hash',p_parent_hash,b.feedback_token_expires_at)
   on conflict(booking_id,slot) do update set token_hash=excluded.token_hash,parent_token_hash=excluded.parent_token_hash,expires_at=excluded.expires_at;
 end loop;
 return coalesce((select jsonb_agg(jsonb_build_object('slot',i.slot,'submitted',exists(select 1 from public.companion_feedback f where f.invitation_id=i.id),'expires_at',i.expires_at) order by i.slot)
 from public.companion_feedback_invitations i where i.booking_id=p_booking_id and i.slot<=capacity),'[]'::jsonb);
end $$;

-- A booking lock serializes duplicate submissions and invitation changes.
create or replace function public.access_companion_feedback(p_booking_id uuid,p_token_hash text,p_feedback jsonb default null)
returns jsonb language plpgsql security definer set search_path=public as $$
declare b public.bookings%rowtype; i public.companion_feedback_invitations%rowtype; already boolean;
begin
 select * into b from public.bookings where id=p_booking_id for update;
 if not found then raise exception 'Invalid booking'; end if;
 select * into i from public.companion_feedback_invitations where booking_id=p_booking_id and token_hash=p_token_hash;
 if not found then raise exception 'Invalid companion link'; end if;
 if i.expires_at<=now() or i.parent_token_hash is distinct from b.feedback_token_hash
    or b.feedback_token_revoked_at is not null or b.feedback_token_expires_at is null or b.feedback_token_expires_at<=now()
    or i.slot>greatest(coalesce(b.guest_count,1)-1,0)
    or not coalesce(public.feedback_booking_eligible(p_booking_id),false) then raise exception 'Companion link unavailable'; end if;
 already:=exists(select 1 from public.companion_feedback where invitation_id=i.id);
 if p_feedback is not null and not already then
   if length(trim(p_feedback->>'comments')) not between 20 and 3000
      or coalesce((p_feedback->>'overall_rating')::integer,0) not between 1 and 5 then raise exception 'Invalid feedback'; end if;
   insert into public.companion_feedback(invitation_id,overall_rating,cleanliness_rating,service_rating,villa_rating,value_rating,would_recommend,comments,hide_identity,private_note)
   values(i.id,(p_feedback->>'overall_rating')::integer,(p_feedback->>'cleanliness_rating')::integer,(p_feedback->>'service_rating')::integer,(p_feedback->>'villa_rating')::integer,(p_feedback->>'value_rating')::integer,(p_feedback->>'would_recommend')::boolean,p_feedback->>'comments',true,p_feedback->>'private_note');
 end if;
 return jsonb_build_object('submitted',already or p_feedback is not null,'duplicate',already,'booking',jsonb_build_object('villa_name',b.villa_name,'check_in_date',b.check_in_date,'check_out_date',b.check_out_date));
end $$;
revoke all on function public.issue_companion_feedback_links(uuid,text,jsonb) from public,anon,authenticated;
revoke all on function public.access_companion_feedback(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.issue_companion_feedback_links(uuid,text,jsonb) to service_role;
grant execute on function public.access_companion_feedback(uuid,text,jsonb) to service_role;
do $$ begin
 if exists(select 1 from pg_publication where pubname='supabase_realtime') and not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename='companion_feedback') then
  alter publication supabase_realtime add table public.companion_feedback;
 end if;
end $$;
commit;
