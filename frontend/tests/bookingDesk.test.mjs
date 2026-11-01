import test from 'node:test';
import assert from 'node:assert/strict';
import { filterBookingRecords } from '../src/bookingDesk.mjs';

const booking = { id: 'online', bookingCode: 'TV-01', guestName: 'Alex', villaName: 'Villa One', checkIn: '2026-11-01', checkOut: '2026-11-02', paymentStatus: 'Paid', bookingStatus: 'Confirmed', createdAt: '2026-10-28' };
const rows = [booking, { ...booking, id: 'walk-in', bookingCode: 'TV-02', bookingChannel: 'walk_in' }, { ...booking, id: 'tomorrow', checkIn: '2026-11-02', createdAt: '2026-11-01' }, { ...booking, id: 'past', checkIn: '2026-10-30', bookingStatus: 'Completed' }, { ...booking, id: 'cancelled', bookingStatus: 'Cancelled' }];

test('daily arrivals include online and walk-in stays by check-in date, not creation date', () => {
  assert.deepEqual(filterBookingRecords(rows, { arrivalDate: '2026-11-01' }).map(row => row.id), ['online', 'cancelled', 'walk-in']);
});

test('all bookings and status filters can display historical and cancelled records', () => {
  assert.equal(filterBookingRecords(rows).length, rows.length);
  assert.deepEqual(filterBookingRecords(rows, { status: 'Completed' }).map(row => row.id), ['past']);
  assert.deepEqual(filterBookingRecords(rows, { status: 'Overdue/Cancelled' }).map(row => row.id), ['cancelled']);
  assert.equal(filterBookingRecords([{ ...booking, lifecycleStatus: 'Completed', stayStatus: 'Checked Out' }], { status: 'Completed' }).length, 1);
});

test('arrival date, payment status and guest search work together without changing source records', () => {
  const partial = { ...booking, id: 'partial', guestName: 'Sam Reyes', paymentStatus: '50% Downpayment' };
  const source = [booking, partial];
  assert.deepEqual(filterBookingRecords(source, { arrivalDate: '2026-11-01', status: 'Unpaid', search: ' REYES ' }).map(row => row.id), ['partial']);
  assert.deepEqual(source.map(row => row.id), ['online', 'partial']);
});
