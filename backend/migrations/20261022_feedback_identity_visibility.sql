-- CSV reviews stay anonymous. System submissions retain their anonymity choice.
begin;
update public.guest_feedback
set hide_identity=true,guest_name='Anonymous guest'
where source='historical_dataset';
-- Restore a missing display name only where the system guest allowed it.
update public.guest_feedback f
set guest_name=b.customer_name
from public.bookings b
where f.booking_id=b.id
 and coalesce(f.source,'verified_stay')<>'historical_dataset'
 and f.hide_identity=false
 and nullif(trim(b.customer_name),'') is not null
 and (nullif(trim(f.guest_name),'') is null
      or lower(trim(f.guest_name)) in ('anonymous','anonymous guest','guest'));
commit;
