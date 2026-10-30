# Airbnb reservations and post-stay feedback

## Integration boundary

The Manual Booking page includes an Airbnb-request availability checker. The
Villa calendar is the source of truth; no Airbnb calendar or API is connected.
The checker includes Villa bookings, maintenance, and internally recorded
Airbnb holds/stays. It reports when the internal calendar was checked, not an
Airbnb sync time. The existing direct manual booking endpoint creates PayMongo
checkout links; do not use it to charge an Airbnb reservation again.

Calendar feeds are not part of this workflow. They do not provide a complete
reservation, guest contact, payment or reviews API, and their refreshes are not
synchronous enough to serve as an atomic availability lock.

Reference: https://www.airbnb.com/help/article/99

## Approval flow

Apply `backend/migrations/20261030_airbnb_stay_holds.sql` and then
`backend/migrations/20261030_airbnb_stay_to_booking.sql` before using this
workflow.

1. Open **Check Airbnb dates** on the Manual Booking page and enter the
   check-in date and guest count. The checker uses the standard 21-hour stay:
   3:00 PM check-in and 12:00 PM checkout the next day. Only proceed when The
   Villa calendar shows enough availability.
2. Select the Villa(s) and create a 10-minute hold. This reserves the chosen
   dates inside The Villa while the admin accepts the request on Airbnb.
3. After accepting it on Airbnb, confirm the hold in The Villa and enter the
   guest's name. Contact details are optional. Confirmation atomically turns
   the hold into a normal confirmed booking, so the booking blocks dates and
   appears in booking operations.
4. Housekeeping preparation is assigned through the normal workflow. The
   Airbnb payment remains external: The Villa records no payment, balance, or
   Airbnb payout. The booking's The Villa catalog price is an internal
   reference only, not the amount Airbnb charged or paid out; exclude Airbnb
   stays from payment and revenue reporting.
5. If the Airbnb request is not accepted, release the hold in The Villa or let
   its 10-minute expiry clear it. A saved Airbnb booking is no longer a hold;
   do not use **Release** on an accepted stay.
6. Airbnb approval still happens on Airbnb. This system does not import Airbnb
   guest details, reservations, reviews, or calendar changes.

## Feedback for an Airbnb guest

Collect a voluntary **The Villa post-stay survey**, rather than presenting it as
an imported Airbnb review. After staff verify the external reservation and mark
the actual stay completed, issue an expiring, stay-scoped, single-use feedback
token. Give the guest its link/QR at checkout, or send it through an authorized
contact channel when their contact is legitimately available.

Use the same rating/comment questions as direct guests. Record booking source,
verification evidence and collection source separately so ML analysis can filter
Airbnb stays versus direct stays without duplicating responses. An imported
calendar event alone must not qualify a survey as verified guest feedback.

The existing feedback eligibility/payment checks need an explicit external-
reservation extension before this workflow can issue valid feedback links.
Do not bypass those checks, fake a PayMongo payment, or fabricate guest reviews.
Importing reviews already posted on Airbnb needs a separately supported data
source/permission; calendar sync does not implement that feature.
