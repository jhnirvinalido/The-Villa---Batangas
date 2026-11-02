import test from 'node:test';
import assert from 'node:assert/strict';
import { bookingReadiness, deskBookingAction, matchesVillaFilter, minimumVillaCount, normalizeDeskBooking, VILLA_FILTER_OPTIONS } from '../src/frontDeskModel.mjs';

const day = '2026-11-01';
const raw = { id: 'booking-1', booking_status: 'Confirmed', stay_status: 'Not Checked In', check_in_date: day, check_out_date: '2026-11-02', total_amount: '5000.00', amount_paid: '2500.00', balance_amount: '2500.00', payment_choice: 'half' };

test('arrival operations follow the booked day and verified payment, not the current date alone', () => {
  assert.equal(deskBookingAction(normalizeDeskBooking(raw), day), 'payment');
  assert.equal(deskBookingAction(normalizeDeskBooking(raw), '2026-10-31'), '');
  assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, amount_paid: 0 }), day), '');
  assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, front_desk_balance_timing: 'check_out' }), day), 'checkin');
  assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, amount_paid: 5000, balance_amount: 0 }), day), 'checkin');
});

test('in-house stays remain actionable past checkout, while departed and cancelled stays cannot collect again', () => {
  assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, stay_status: 'Checked In' }), '2026-11-03'), 'payment');
  assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, stay_status: 'Checked In', balance_amount: 0 }), '2026-11-03'), 'checkout');
  for (const booking_status of ['Cancelled', 'Expired', 'Completed']) assert.equal(deskBookingAction(normalizeDeskBooking({ ...raw, booking_status }), day), '');
});

test('Airbnb payments stay external and walk-in markers remain visible', () => {
  const airbnb = normalizeDeskBooking({ ...raw, booking_channel: 'airbnb', amount_paid: 0 });
  assert.equal(airbnb.paymentStatus, 'Handled by Airbnb');
  assert.equal(deskBookingAction(airbnb, day), 'checkin');
  assert.equal(normalizeDeskBooking({ ...raw, notes: '[Walk-in booking staff:staff-1]' }).walkIn, true);
  assert.equal(normalizeDeskBooking({ ...raw, booking_channel: 'walk_in' }).walkIn, true);
});

test('room readiness needs approved preparation for every assigned cleaner', () => {
  const booking = normalizeDeskBooking(raw);
  const task = { bookingId: raw.id, assignmentType: 'housekeeping-pre-arrival', status: 'Pending Review', assignedTo: 'Ana', checklist: [{ done: true }] };
  assert.equal(bookingReadiness(booking, [task]).label, 'Awaiting approval');
  assert.equal(bookingReadiness(booking, [{ ...task, status: 'Completed' }]).label, 'Ready · approved');
  assert.equal(bookingReadiness(booking, [{ ...task, status: 'Completed' }, { ...task, assignedTo: 'Ben', status: 'In Progress' }]).tone, 'warning');
  assert.equal(bookingReadiness(booking, [{ ...task, status: 'Cancelled' }]).label, 'No preparation assigned');
  assert.equal(bookingReadiness(booking, [{ ...task, bookingId: 'other', status: 'Completed' }]).label, 'No preparation assigned');
});

test('villa selection uses available capacity and rejects groups without enough rooms', () => {
  const villas = [{ available: true, capacity: 4 }, { available: true, capacity: 3 }, { available: false, capacity: 20 }];
  assert.equal(minimumVillaCount(4, villas), 1);
  assert.equal(minimumVillaCount(6, villas), 2);
  assert.equal(minimumVillaCount(8, villas), Infinity);
});

test('villa filters stay limited to Villas 1-3 and match combined villa names exactly', () => {
  assert.deepEqual(VILLA_FILTER_OPTIONS, ['Villa 1', 'Villa 2', 'Villa 3']);
  assert.equal(matchesVillaFilter('Villa 2, Villa 1, Villa 3, Villa 4', 'Villa 1'), true);
  assert.equal(matchesVillaFilter('Villa 10, Villa 2', 'Villa 1'), false);
  assert.equal(matchesVillaFilter('Villa 4', 'Villa 3'), false);
  assert.equal(matchesVillaFilter('Villa 4', ''), true);
});
