import test from 'node:test';
import assert from 'node:assert/strict';
import { bookingAnalytics } from '../src/bookingAnalytics.mjs';

const villas=[{id:'v1',title:'Villa 1'},{id:'v2',title:'Villa 2'}];
const reservation={id:'b',villaIds:['v1'],villaName:'Villa 1',checkIn:'2026-10-30',checkOut:'2026-10-31',
  bookingStatus:'Confirmed',amountPaid:500,totalAmount:1000,email:'guest@example.com',paymentHistory:[]};

test('empty database produces zero charts, not sample values',()=>{
  const data=bookingAnalytics([],villas,2026);
  assert.equal(data.monthlyBookings.reduce((a,b)=>a+b,0),0);
  assert.equal(data.occupancyRate,0);
  assert.equal(data.mostBookedVilla,'-');
});
test('months do not combine years or count cancelled stays as confirmed',()=>{
  const data=bookingAnalytics([reservation,{...reservation,id:'old',checkIn:'2025-10-30'},
    {...reservation,id:'cancel',bookingStatus:'Cancelled'}],villas,2026);
  assert.equal(data.monthlyBookings[9],1);
  assert.equal(data.bookingStatus.Cancelled,undefined);
  assert.equal(data.totalBookings,1);
  assert.equal(data.paymentStatus.Partial,1);
});
test('payment totals use receipt month, not total booking price or stay date',()=>{
  const data=bookingAnalytics([{...reservation,paymentHistory:[{id:'pay',amount:500,processedAt:'2026-09-29',status:'paid'},
    {id:'pay',amount:500,processedAt:'2026-09-29',status:'paid'}]}],villas,2026);
  assert.equal(data.monthlyRevenue[8],500);
  assert.equal(data.monthlyRevenue[9],0);
  assert.equal(data.totalRevenue,500);
});
test('repeat guests count unique returning people and multi-villa stays count each villa',()=>{
  const data=bookingAnalytics([reservation,{...reservation,id:'second',villaIds:['v1','v2']}],villas,2026);
  assert.equal(data.totalGuests,1);
  assert.equal(data.repeatGuests,1);
  assert.deepEqual(data.villaChart.map(v=>v.value),[2,1]);
});
test('receipt dates use Manila month boundaries',()=>{
  const data=bookingAnalytics([{...reservation,paymentHistory:[{id:'boundary',amount:500,processedAt:'2026-09-30T17:00:00Z',status:'paid'}]}],villas,2026);
  assert.equal(data.monthlyRevenue[8],0);
  assert.equal(data.monthlyRevenue[9],500);
});

test('revenue includes successful online and front-desk receipts only',()=>{
  const data=bookingAnalytics([{...reservation,paymentHistory:[
    {id:'paid',amount:400,processedAt:'2026-10-01',status:'paid'},
    {id:'pending',amount:200,processedAt:'2026-10-02',status:'processing'},
    {id:'refunded',amount:100,processedAt:'2026-10-03',status:'refunded'},
  ]}],villas,2026,[
    {id:'cash',bookingId:'b',amount:300,processedAt:'2026-10-04',status:'Completed'},
  ]);
  assert.equal(data.totalRevenue,700);
  assert.equal(data.monthlyRevenue[9],700);
  assert.equal(data.villaChart.find(v=>v.name==='Villa 1').revenue,700);
});

test('cancelled or refunded reservations do not count as collected revenue',()=>{
  const cancelled={...reservation,bookingStatus:'Cancelled',paymentHistory:[
    {id:'online',amount:400,processedAt:'2026-10-01',status:'paid'},
  ]};
  const data=bookingAnalytics([cancelled],villas,2026,[
    {id:'cash',bookingId:'b',amount:300,processedAt:'2026-10-04',status:'Completed'},
  ]);
  assert.equal(data.totalRevenue,0);
});

test('Airbnb bookings reserve occupancy but never appear as unpaid or Villa revenue',()=>{
  const airbnb={...reservation,id:'airbnb',bookingChannel:'airbnb',amountPaid:0,totalAmount:5000,
    paymentStatus:'External',paymentHistory:[{id:'airbnb-online',amount:5000,processedAt:'2026-10-01',status:'paid'}]};
  const data=bookingAnalytics([airbnb],villas,2026,[
    {id:'airbnb-cash',bookingId:'airbnb',amount:200,processedAt:'2026-10-04',status:'Completed'},
  ]);
  assert.equal(data.bookingStatus.Confirmed,1);
  assert.deepEqual(data.paymentStatus,{Paid:0,Partial:0,Unpaid:0});
  assert.equal(data.totalRevenue,0);
  assert.equal(data.monthlyBookings[9],1);
  assert.equal(data.villaChart.find(v=>v.name==='Villa 1').value,1);
});

test('booking total is defined and cancelled bookings do not inflate pending payments',()=>{
  const data=bookingAnalytics([
    reservation,
    {...reservation,id:'cancelled',bookingStatus:'Cancelled',amountPaid:0},
    {...reservation,id:'pending',bookingStatus:'Pending Payment',amountPaid:0},
  ],villas,2026);
  assert.equal(data.totalBookings,2);
  assert.deepEqual(data.bookingStatus,{Pending:1,Confirmed:1,'Checked In':0,Completed:0});
  assert.deepEqual(data.paymentStatus,{Paid:0,Partial:1,Unpaid:1});
  assert.equal(data.pendingPaymentCount,2);
  assert.equal(data.monthlyBookings[9],1);
});

test('pending payment counts outstanding balances and channel totals exclude cancelled bookings',()=>{
  const data=bookingAnalytics([
    {...reservation,id:'airbnb',bookingChannel:'airbnb',amountPaid:0,totalAmount:5000,balanceAmount:0},
    {...reservation,id:'cancelled-airbnb',bookingChannel:'airbnb',bookingStatus:'Cancelled'},
    {...reservation,id:'paid',amountPaid:1000,balanceAmount:0},
    {...reservation,id:'partial',amountPaid:500,balanceAmount:500},
    {...reservation,id:'unpaid',bookingStatus:'Pending Payment',amountPaid:0,balanceAmount:1000},
    {...reservation,id:'expired',bookingStatus:'Expired',amountPaid:0},
  ],villas,2026,[],{pending:2,inProgress:1,review:1,overdue:1,completed:3});
  assert.equal(data.totalBookings,4);
  assert.deepEqual(data.bookingChannel,{Airbnb:1,'The Villa':3});
  assert.equal(data.pendingPaymentCount,2);
  assert.deepEqual(data.paymentStatus,{Paid:1,Partial:1,Unpaid:1});
  assert.deepEqual(data.assignmentProgress,{
    Pending:2,'In Progress':1,'Pending Review':1,Overdue:1,Completed:3,
  });
});

test('bookings without stable contact details do not merge into one guest',()=>{
  const data=bookingAnalytics([
    {...reservation,email:'',phone:'',guestName:'Villa Guest'},
    {...reservation,id:'second',email:'',phone:'',guestName:'Villa Guest'},
  ],villas,2026);
  assert.equal(data.totalGuests,2);
  assert.equal(data.repeatGuests,0);
});
