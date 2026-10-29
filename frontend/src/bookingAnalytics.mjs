const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dayNumber = value => {
  let text = String(value || '');
  if (text.includes('T')) {
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return NaN;
    const parts = new Intl.DateTimeFormat('en', {timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(parsed);
    const part = type => parts.find(p=>p.type===type).value;
    text = `${part('year')}-${part('month')}-${part('day')}`;
  }
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? Date.UTC(+match[1], +match[2] - 1, +match[3]) / 86400000 : NaN;
};

const isSuccessfulPayment = value =>
  ['paid','completed','succeeded','success','settled'].includes(String(value || '').trim().toLowerCase());

export function bookingAnalytics(bookings, villas, year, frontDeskPayments = []) {
  const monthlyBookings = Array(12).fill(0), monthlyRevenue = Array(12).fill(0);
  const bookingStatus = {Pending:0, Confirmed:0, 'Checked In':0, Completed:0, Cancelled:0};
  const paymentStatus = {Paid:0, Partial:0, Unpaid:0};
  const performance = new Map(villas.map(v => [v.id, {name:v.title || v.name, value:0, revenue:0}]));
  const guests = new Map(), nights = new Set(), seenPayments = new Set();
  const start = Date.UTC(year,0,1)/86400000, end = Date.UTC(year+1,0,1)/86400000;
  const recordPayment = (payment, key, villaIds = []) => {
    if (seenPayments.has(key)) return;
    seenPayments.add(key);
    if (!isSuccessfulPayment(payment.status)) return;
    const amount = Number(payment.amount);
    const paidDay = dayNumber(payment.processedAt ?? payment.processed_at ?? payment.created_at);
    if (!(Number.isFinite(amount) && amount > 0 && paidDay >= start && paidDay < end)) return;
    monthlyRevenue[new Date(paidDay*86400000).getUTCMonth()] += amount;
    const ids = [...new Set(villaIds)];
    for (const id of ids) {
      const villa = performance.get(id);
      if (villa) villa.revenue += amount / ids.length;
    }
  };
  const bookingDetails = new Map();
  for (const b of bookings) {
    const checkIn = dayNumber(b.checkIn), checkOut = dayNumber(b.checkOut);
    const status = String(b.bookingStatus || '').toLowerCase();
    const cancelled = /cancel|expired|refund/.test(status) ||
      /refund/.test(String(b.paymentStatus || '').toLowerCase()) ||
      Number(b.refundedAmount || b.refunded_amount || 0) > 0;
    const confirmed = !cancelled && /confirm|checked|complet/.test(status);
    const ids = [...new Set(b.villaIds?.length ? b.villaIds : [b.villaName])];
    bookingDetails.set(String(b.id), {ids, cancelled});
    // Payments are dated by receipt, not by the reservation's future stay date.
    for (const p of b.paymentHistory || []) {
      if (!cancelled) recordPayment(p, `booking:${b.id}:${p.id}`, ids);
    }
    if (confirmed && Number.isFinite(checkIn) && Number.isFinite(checkOut)) {
      for (let day=Math.max(start,checkIn); day<Math.min(end,checkOut); day++) {
        for (const id of ids) if (performance.has(id)) nights.add(`${id}:${day}`);
      }
    }
    if (!(checkIn >= start && checkIn < end)) continue;
    const bucket = cancelled ? 'Cancelled' : /checked.?in/.test(status) ? 'Checked In'
      : /complet|checked.?out/.test(status) ? 'Completed' : confirmed ? 'Confirmed' : 'Pending';
    bookingStatus[bucket]++;
    if (!cancelled) {
      const paid = Number(b.amountPaid)||0, total=Number(b.totalAmount)||0;
      paymentStatus[paid>0 && total>0 && paid>=total ? 'Paid' : paid>0 ? 'Partial' : 'Unpaid']++;
    }
    if (!confirmed) continue;
    monthlyBookings[new Date(checkIn*86400000).getUTCMonth()]++;
    for (const id of ids) {
      if (!performance.has(id)) performance.set(id,{name:b.villaName || id,value:0,revenue:0});
      performance.get(id).value++;
    }
    const email = String(b.email || '').trim().toLowerCase();
    const phone = String(b.phone || '').replace(/\D/g, '');
    const guestKey = email && email !== 'no email address' ? `email:${email}`
      : phone && phone !== 'no contact number' ? `phone:${phone}`
      : `booking:${b.id}`;
    guests.set(guestKey,(guests.get(guestKey)||0)+1);
  }
  for (const payment of frontDeskPayments) {
    const bookingId = payment.bookingId ?? payment.booking_id;
    const booking = bookingDetails.get(String(bookingId));
    if (!booking?.cancelled) {
      recordPayment(payment, `front-desk:${payment.id}`, booking?.ids || []);
    }
  }
  const villaChart=[...performance.values()].sort((a,b)=>b.value-a.value);
  return {year, months:MONTHS, monthlyBookings, monthlyRevenue, totalRevenue:monthlyRevenue.reduce((total, amount)=>total+amount,0),
    totalBookings:Object.values(bookingStatus).reduce((total, count)=>total+count,0), villaChart, bookingStatus, paymentStatus,
    totalGuests:guests.size, repeatGuests:[...guests.values()].filter(n=>n>1).length,
    occupancyRate:villas.length ? Math.round(nights.size/((end-start)*villas.length)*100) : 0,
    mostBookedVilla:villaChart.some(v=>v.value>0) ? villaChart[0].name : '-',
    leastBookedVilla:villaChart.length ? villaChart.at(-1).name : '-'};
}
