CREATE TABLE IF NOT EXISTS public.staff_time_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_account_id uuid NOT NULL REFERENCES public.staff_accounts(id) ON DELETE CASCADE,
    clock_in_at timestamptz NOT NULL DEFAULT now(),
    clock_out_at timestamptz,
    review_status text NOT NULL DEFAULT 'open'
        CHECK (review_status IN ('open', 'pending_review', 'approved', 'needs_correction')),
    review_note text,
    reviewed_by_staff_id uuid REFERENCES public.staff_accounts(id) ON DELETE SET NULL,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT staff_time_records_clock_range_valid
        CHECK (clock_out_at IS NULL OR clock_out_at >= clock_in_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS staff_time_records_one_open_per_staff
    ON public.staff_time_records (staff_account_id)
    WHERE clock_out_at IS NULL;

CREATE INDEX IF NOT EXISTS staff_time_records_staff_clock_in_idx
    ON public.staff_time_records (staff_account_id, clock_in_at DESC);

CREATE INDEX IF NOT EXISTS staff_time_records_review_idx
    ON public.staff_time_records (review_status, clock_in_at DESC);

ALTER TABLE public.staff_time_records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.staff_time_records FROM anon, authenticated;
GRANT ALL ON public.staff_time_records TO service_role;
