-- Durable recommendation generation with database-coordinated claims and retries.
-- Apply after the feedback analysis schema that creates feedback_recommendation_reports.
begin;

do $$
begin
    if to_regclass('public.feedback_recommendation_reports') is null then
        raise exception 'Apply the feedback analysis schema before recommendation jobs';
    end if;
    if exists (
        select 1
        from public.feedback_recommendation_reports
        where status in ('draft', 'approved')
        group by evidence_fingerprint
        having count(*) > 1
    ) then
        raise exception 'Resolve duplicate active recommendation reports by evidence_fingerprint before applying recommendation jobs';
    end if;
end;
$$;

create unique index if not exists feedback_recommendation_reports_one_per_evidence_idx
    on public.feedback_recommendation_reports (evidence_fingerprint)
    where status in ('draft', 'approved');

create table if not exists public.feedback_recommendation_jobs (
    id uuid primary key default gen_random_uuid(),
    evidence_fingerprint text not null unique,
    created_by_staff_id uuid not null,
    filters jsonb not null,
    evidence_summary jsonb not null,
    model_version text not null,
    status text not null default 'queued'
        check (status in ('queued', 'processing', 'retry', 'completed', 'failed')),
    attempts integer not null default 0 check (attempts >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 5),
    next_attempt_at timestamptz not null default now(),
    claim_id uuid,
    claim_expires_at timestamptz,
    report_id uuid,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists feedback_recommendation_jobs_due_idx
    on public.feedback_recommendation_jobs (next_attempt_at, created_at)
    where status in ('queued', 'retry', 'processing');

alter table public.feedback_recommendation_jobs enable row level security;
revoke all on public.feedback_recommendation_jobs from public, anon, authenticated;
grant all on public.feedback_recommendation_jobs to service_role;

create or replace function public.enqueue_feedback_recommendation_job(p_job jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    job public.feedback_recommendation_jobs%rowtype;
begin
    insert into public.feedback_recommendation_jobs (
        evidence_fingerprint, created_by_staff_id, filters, evidence_summary,
        model_version, status
    ) values (
        p_job->>'evidence_fingerprint',
        (p_job->>'created_by_staff_id')::uuid,
        p_job->'filters',
        p_job->'evidence_summary',
        p_job->>'model_version',
        'queued'
    )
    on conflict (evidence_fingerprint) do update
       set created_by_staff_id = excluded.created_by_staff_id,
           filters = excluded.filters,
           evidence_summary = excluded.evidence_summary,
           model_version = excluded.model_version,
           status = 'queued',
           attempts = 0,
           next_attempt_at = now(),
           claim_id = null,
           claim_expires_at = null,
           report_id = null,
           last_error = null,
           updated_at = now()
     where feedback_recommendation_jobs.status in ('failed', 'completed')
    returning * into job;

    if not found then
        select * into job
        from public.feedback_recommendation_jobs
        where evidence_fingerprint = p_job->>'evidence_fingerprint';
    end if;
    return to_jsonb(job);
end;
$$;

create or replace function public.claim_feedback_recommendation_job()
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    job public.feedback_recommendation_jobs%rowtype;
begin
    update public.feedback_recommendation_jobs
       set status = 'failed',
           claim_id = null,
           claim_expires_at = null,
           last_error = 'Worker lease expired after the final attempt.',
           updated_at = now()
     where status = 'processing'
       and claim_expires_at <= now()
       and attempts >= max_attempts;

    select * into job
    from public.feedback_recommendation_jobs
    where (
        (status in ('queued', 'retry') and next_attempt_at <= now())
        or (status = 'processing' and claim_expires_at <= now() and attempts < max_attempts)
    )
    order by next_attempt_at, created_at
    limit 1
    for update skip locked;

    if not found then
        return null;
    end if;

    update public.feedback_recommendation_jobs
       set status = 'processing',
           attempts = attempts + 1,
           claim_id = gen_random_uuid(),
           claim_expires_at = now() + interval '2 minutes',
           updated_at = now()
     where id = job.id
    returning * into job;
    return to_jsonb(job);
end;
$$;

create or replace function public.finish_feedback_recommendation_job(
    p_job_id uuid,
    p_claim_id uuid,
    p_status text,
    p_report_id uuid default null,
    p_error text default null,
    p_retryable boolean default false
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    job public.feedback_recommendation_jobs%rowtype;
    next_status text;
    delay_seconds integer;
begin
    select * into job
    from public.feedback_recommendation_jobs
    where id = p_job_id and claim_id = p_claim_id and status = 'processing'
    for update;
    if not found then
        return false;
    end if;

    if p_status = 'completed' and p_report_id is not null then
        next_status := 'completed';
        delay_seconds := 0;
    elsif p_retryable and job.attempts < job.max_attempts then
        next_status := 'retry';
        delay_seconds := least(300, 30 * (2 ^ greatest(job.attempts - 1, 0)))::integer;
    else
        next_status := 'failed';
        delay_seconds := 0;
    end if;

    update public.feedback_recommendation_jobs
       set status = next_status,
           report_id = case when next_status = 'completed' then p_report_id else report_id end,
           next_attempt_at = case when next_status = 'retry'
                                  then now() + make_interval(secs => delay_seconds)
                                  else next_attempt_at end,
           claim_id = null,
           claim_expires_at = null,
           last_error = case when next_status = 'completed' then null
                             else left(coalesce(p_error, 'Recommendation generation failed.'), 400) end,
           updated_at = now()
     where id = p_job_id;
    return true;
end;
$$;

create or replace function public.persist_feedback_recommendation_report(p_report jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    report public.feedback_recommendation_reports%rowtype;
    fingerprint text := p_report->>'evidence_fingerprint';
begin
    if fingerprint is null or fingerprint = '' then
        raise exception 'Recommendation evidence fingerprint is required';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(fingerprint, 0));
    select * into report
    from public.feedback_recommendation_reports
    where evidence_fingerprint = fingerprint
    order by created_at desc
    limit 1;

    if found then
        return jsonb_build_object('created', false, 'report', to_jsonb(report));
    end if;

    insert into public.feedback_recommendation_reports (
        created_by_staff_id, filters, evidence_fingerprint, evidence_summary,
        model_version, recommendation, status
    ) values (
        (p_report->>'created_by_staff_id')::uuid,
        p_report->'filters',
        fingerprint,
        p_report->'evidence_summary',
        p_report->>'model_version',
        p_report->'recommendation',
        'draft'
    )
    returning * into report;
    return jsonb_build_object('created', true, 'report', to_jsonb(report));
end;
$$;

revoke all on function public.enqueue_feedback_recommendation_job(jsonb) from public, anon, authenticated;
revoke all on function public.claim_feedback_recommendation_job() from public, anon, authenticated;
revoke all on function public.finish_feedback_recommendation_job(uuid, uuid, text, uuid, text, boolean) from public, anon, authenticated;
revoke all on function public.persist_feedback_recommendation_report(jsonb) from public, anon, authenticated;
grant execute on function public.enqueue_feedback_recommendation_job(jsonb) to service_role;
grant execute on function public.claim_feedback_recommendation_job() to service_role;
grant execute on function public.finish_feedback_recommendation_job(uuid, uuid, text, uuid, text, boolean) to service_role;
grant execute on function public.persist_feedback_recommendation_report(jsonb) to service_role;

commit;
