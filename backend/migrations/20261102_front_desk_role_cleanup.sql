UPDATE public.staff_accounts
SET walk_in_access_requested = false,
    can_create_walk_in_bookings = false,
    payment_access_requested = false,
    can_process_front_desk_payments = false,
    can_manage_existing_bookings = false
WHERE role = 'staff'
  AND (
      walk_in_access_requested
      OR can_create_walk_in_bookings
      OR payment_access_requested
      OR can_process_front_desk_payments
      OR can_manage_existing_bookings
  );
