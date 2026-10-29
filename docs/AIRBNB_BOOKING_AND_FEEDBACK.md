# Airbnb reservations and post-stay feedback

## Integration boundary

This is the proposed workflow, not an installed Airbnb connection. The existing
manual booking endpoint creates PayMongo checkout links; do not use it to charge
an Airbnb reservation again. No Airbnb approval or review import is implemented
by the chart/name/maintenance changes.

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
3. Show the admin a single calendar containing internal reservations, external
   blocks and scheduled maintenance dates. Show each source and last sync time.
4. Refresh external availability before the admin decides. Detect overlapping
   stays using check-in inclusive / checkout exclusive ranges, not equal dates.
5. Approval on Airbnb must use Airbnb or an approved API connection. A button
   in this system must not claim to have approved Airbnb without that connection.
6. Once confirmed, deduplicate by external reservation ID. Store source=Airbnb,
   reservation reference, villa/date range and externally collected payment
   status. Use a separate flow from PayMongo checkout. iCal blocks without
   sufficient reservation evidence stay blocks, not paid revenue records.

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
