# Airbnb reservations and post-stay feedback

## Integration boundary

The Manual Booking page now includes a read-only Airbnb availability checker.
It checks requested stay dates against bookings and scheduled maintenance in
The Villa; it does not create a reservation, place a hold, or connect to Airbnb.
The existing direct manual booking endpoint creates PayMongo checkout links;
do not use it to charge an Airbnb reservation again. No Airbnb approval,
reservation import, or review import is implemented.

Calendar import/export is appropriate for blocked nights. It is not a complete
reservation, guest contact, payment or reviews API. Airbnb also exports owner-
blocked dates, so an imported event must not automatically be treated as a paid
reservation or genuine guest. Airbnb refreshes imported calendars periodically,
not synchronously; a feed is not an atomic lock against double booking.

Reference: https://www.airbnb.com/help/article/99

## Approval flow

1. Map each Airbnb listing to a Villa ID and configure its calendar feed or an
   approved channel-manager/API integration. Keep feed URLs private.
2. A request remains pending until approved on Airbnb. An iCal feed alone must
   not be assumed to include pending requests or enough information to approve
   them automatically.
3. Before responding to an Airbnb booking request, use the Manual Booking
   page's availability checker to inspect all requested nights and the party
   size. The checker uses internal reservations and scheduled maintenance only;
   it does not know about other pending Airbnb requests or external blocks.
4. Recheck immediately before approving on Airbnb. This check is not a hold,
   so another booking could be confirmed between the check and approval.
5. Approval on Airbnb must use Airbnb or an approved API connection. A button
   in this system must not claim to have approved Airbnb without that connection.
6. Accepted Airbnb reservations are not currently imported into The Villa.
   Recordkeeping and feedback eligibility need a separate external-reservation
   workflow. Do not treat an iCal block as a paid booking or verified guest.

## Feedback for an Airbnb guest

Collect a voluntary **The Villa post-stay survey**, rather than presenting it as
an imported Airbnb review. After staff verify the external reservation and mark
the actual stay completed, issue an expiring, booking-scoped, single-use feedback
token. Give the guest its link/QR at checkout, or send it through an authorized
contact channel when their contact is legitimately available. Do not assume a
calendar feed provides an email address.

Use the same rating/comment questions as direct guests. Record booking source,
verification evidence and collection source separately so ML analysis can filter
Airbnb stays versus direct stays without duplicating responses. An imported
calendar event alone must not qualify a survey as verified guest feedback.

The existing feedback eligibility/payment checks need an explicit external-
reservation extension before this workflow can issue valid feedback links.
Do not bypass those checks, fake a PayMongo payment, or fabricate guest reviews.
Importing reviews already posted on Airbnb needs a separately supported data
source/permission; calendar sync does not implement that feature.
