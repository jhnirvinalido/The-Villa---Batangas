# Paid checkout recovery

A successful PayMongo payment and a saved reservation are separate steps. Never
collect payment again to recover a paid checkout.

The 2026-11-02 investigation confirmed that the reported checkout remains in
`public_booking_checkouts` and PayMongo reports a paid PHP payment matching the
checkout amount. No corresponding booking or receipt exists yet. A completed
booking overlaps its dates. The deployed schema also requires
`front_desk_other_charges` and `front_desk_other_charges_total` without defaults,
while the checkout payload lacks these fields.

The previous finalization function treated completed stays as conflicts even
though application availability releases them. It also omitted the required
charge fields. The repair aligns that availability rule and supplies empty
charges for existing drafts. Active reservation conflicts still prevent booking
promotion. Payment amount, currency, session identity, token checks, locking and
atomic ledger insertion remain in place.

## Deployment

1. Review and apply `backend/migrations/20261102_repair_public_checkout_finalization.sql`
   in Supabase SQL Editor. This replaces the finalization function; it does not
   charge, finalize a draft, or send email by itself.
2. Deploy the backend and frontend changes. The existing reconciliation worker
   retries pending drafts. A guest with their original booking token can also
   use **Check payment again** on the payment return page.
3. Verify that the checkout became one booking and one payment ledger record,
   with its receipt number. Do not manually mark a draft paid or bypass a real
   active booking conflict.
4. Configure `RESEND_API_KEY` and a verified `RESEND_FROM` in Render for HTTPS
   email delivery. SMTP credentials alone do not work on Render Free's blocked
   outbound SMTP ports. The repository cannot establish the deployed secrets.
5. Check mail-provider acceptance and delivery logs. Existing booking receipt
   email delivery is attempted after new finalization; unsuccessful email sends
   are not automatically resent by refreshing an already finalized booking.
   Any recovery resend must be intentional and checked against delivery logs.

Payment receipt email is separate from post-stay feedback email. Feedback is
queued only after actual checkout and full settlement, and requires the
post-stay feedback migration and delivery worker. A reservation payment alone
must not trigger a post-stay invitation.

## Verification

Public checkout regression tests cover a verified payment whose database
finalization fails: it returns `payment_received`, sends no false confirmation,
and preserves the draft for retry. The return page distinguishes verification
failure from payment success and offers a status retry. It does not infer
payment success from redirect query parameters.

The SQL repair has not been applied to production or executed against a local
PostgreSQL instance as part of this change. Review it against the deployed schema
before applying it. No production data was changed during diagnosis.
