import test from 'node:test';
import assert from 'node:assert/strict';
import { bookingsNeedingStaff, assignmentKind } from '../src/bookingPreparation.mjs';

const booking = {id:'b1', bookingStatus:'Confirmed', paymentStatus:'50% Downpayment', paymentChoice:'half', totalAmount:5000, amountPaid:2500, checkIn:'2026-10-27', stayStatus:'Not Checked In'};
const today = '2026-10-26';
test('staffing exceptions include sufficiently paid future bookings, not drafts or checked-in stays', () => {
  const rows = [booking, {...booking,id:'unpaid',amountPaid:0}, {...booking,id:'past',checkIn:'2026-10-25'}, {...booking,id:'arrived',stayStatus:'Checked In'}, {...booking,id:'draft',bookingStatus:'Pending Payment'}, {...booking,id:'full',paymentChoice:'full'}];
  assert.deepEqual(bookingsNeedingStaff(rows,[],today).map(row=>row.id), ['b1']);
});
test('preparation task and explicit cancellation suppress retry warning; turnover does not', () => {
  for (const status of ['Pending','In Progress','Pending Review','Completed','Cancelled']) {
    assert.equal(bookingsNeedingStaff([booking],[{bookingId:'b1',assignmentType:'housekeeping-pre-arrival',source:'automatic-booking-preparation',status}],today).length,0);
  }
  assert.equal(bookingsNeedingStaff([booking],[{bookingId:'b1',assignmentType:'housekeeping-turnover'}],today).length,1);
  assert.equal(bookingsNeedingStaff([booking],[{bookingId:'b1',assignmentType:'housekeeping-pre-arrival',status:'Cancelled'}],today).length,1);
});
test('arrival preparation and post-checkout turnover have distinct labels', () => {
  assert.equal(assignmentKind({assignmentType:'housekeeping-pre-arrival',source:'automatic-booking-preparation'}),'Automatic preparation');
  assert.equal(assignmentKind({assignmentType:'housekeeping-turnover'}),'Checkout turnover');
});
