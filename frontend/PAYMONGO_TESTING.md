# PayMongo Test Checklist

## GCash

1. Create a booking and select GCash.
2. The Villa saves the booking as Pending Payment.
3. PayMongo opens the GCash sandbox authorization screen.
4. Choose Authorize.
5. Return to The Villa.
6. Confirm My Bookings changes to Confirmed and Partial/Paid.
7. Confirm the receipt appears only after the paid webhook/status check.
8. Repeat and choose Fail. The booking must remain unpaid and reusable.

## Maya

Repeat the GCash checklist using Maya. No real Maya wallet is needed in
test mode.

## Card

Use a PayMongo test card. Complete or fail 3D Secure according to the test
case. The Villa must never render its own card-number, expiry, or CVC fields.

## QR Ph

1. Create a booking and select QR Ph.
2. Open PayMongo sandbox checkout.
3. Do not scan the displayed sandbox QR with a real wallet or bank.
4. Use PayMongo's test simulation controls.
5. Confirm the receipt remains hidden until server-side paid confirmation.

## Cancellation

Close or cancel each checkout. The reservation must remain saved as Pending
Payment and the customer must be able to select another method in My
Bookings.

## Remaining balance

1. Complete a 50% payment.
2. Confirm the booking is Confirmed and payment status is Partial.
3. Choose Pay Remaining Balance.
4. Select any enabled method, even if it differs from the first payment.
5. Complete payment.
6. Confirm payment status becomes Paid and balance becomes zero.

## Webhook safety

- Invalid signature: HTTP 401
- Duplicate delivery: accepted without recording the payment twice
- Return URL without paid webhook/status: no receipt
- Paid webhook: payment recorded once and receipt released
