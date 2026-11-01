ALTER TABLE public.staff_accounts
ADD COLUMN IF NOT EXISTS can_manage_existing_bookings boolean NOT NULL DEFAULT false;

ALTER TABLE public.staff_accounts
ADD COLUMN IF NOT EXISTS walk_in_access_requested boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS can_create_walk_in_bookings boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS payment_access_requested boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS can_process_front_desk_payments boolean NOT NULL DEFAULT false;

UPDATE public.staff_accounts
SET can_manage_existing_bookings = false
WHERE can_manage_existing_bookings = true;

CREATE TABLE IF NOT EXISTS public.front_desk_payment_approval_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    requested_by_staff_id uuid NOT NULL REFERENCES public.staff_accounts(id),
    reviewed_by_staff_id uuid REFERENCES public.staff_accounts(id),
    payment_method text NOT NULL CHECK (payment_method IN ('cash', 'qrph')),
    payment_timing text NOT NULL CHECK (payment_timing IN ('check_in', 'check_out')),
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied', 'processing', 'completed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS front_desk_payment_approval_one_pending_per_booking
    ON public.front_desk_payment_approval_requests (booking_id)
    WHERE status = 'pending';

ALTER TABLE public.front_desk_payment_intents
ADD COLUMN IF NOT EXISTS approval_request_id uuid
    REFERENCES public.front_desk_payment_approval_requests(id);

CREATE UNIQUE INDEX IF NOT EXISTS front_desk_payment_intents_approval_request_unique
    ON public.front_desk_payment_intents (approval_request_id)
    WHERE approval_request_id IS NOT NULL;
