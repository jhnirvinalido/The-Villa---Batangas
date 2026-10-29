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

export function bookingAnalytics(bookings, villas, year) {
  const monthlyBookings = Array(12).fill(0), monthlyRevenue = Array(12).fill(0);
  const bookingStatus = {Pending:0, Confirmed:0, 'Checked In':0, Completed:0, Cancelled:0};
  const paymentStatus = {Paid:0, Partial:0, Unpaid:0};
  const performance = new Map(villas.map(v => [v.id, {name:v.title || v.name, value:0, revenue:0}]));
  const guests = new Map(), nights = new Set(), seenPayments = new Set();
  const start = Date.UTC(year,0,1)/86400000, end = Date.UTC(year+1,0,1)/86400000;
  for (const b of bookings) {
    const checkIn = dayNumber(b.checkIn), checkOut = dayNumber(b.checkOut);
    const status = String(b.bookingStatus || '').toLowerCase();
    const cancelled = /cancel|expired|refund/.test(status);
    const confirmed = !cancelled && (/confirm|checked|complet/.test(status) || Number(b.amountPaid)>0);
    const ids = b.villaIds?.length ? b.villaIds : [b.villaName];
    // Payments are dated by receipt, not by the reservation's future stay date.
    for (const p of b.paymentHistory || []) {
      const key = `${b.id}:${p.id}`;
      if (seenPayments.has(key)) continue;
      seenPayments.add(key);
      const paidDay = dayNumber(p.processedAt);
      if (paidDay >= start && paidDay < end) {
        monthlyRevenue[new Date(paidDay*86400000).getUTCMonth()] += Number(p.amount)||0;
        // Allocate a multi-villa receipt equally; never count its full value once per villa.
        for (const id of ids) {
          const villa = performance.get(id);
          if (villa) villa.revenue += (Number(p.amount)||0)/ids.length;
        }
      }
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
    const paid = Number(b.amountPaid)||0, total=Number(b.totalAmount)||0;
    paymentStatus[paid>0 && total>0 && paid>=total ? 'Paid' : paid>0 ? 'Partial' : 'Unpaid']++;
    if (!confirmed) continue;
    monthlyBookings[new Date(checkIn*86400000).getUTCMonth()]++;
    for (const id of ids) {
      if (!performance.has(id)) performance.set(id,{name:b.villaName || id,value:0,revenue:0});
      performance.get(id).value++;
    }
    const guest=String(b.email && b.email!=='No email address' ? b.email : b.phone && b.phone!=='No contact number' ? b.phone : b.guestName).trim().toLowerCase();
    guests.set(guest,(guests.get(guest)||0)+1);
  }
  const villaChart=[...performance.values()].sort((a,b)=>b.value-a.value);
  return {year, months:MONTHS, monthlyBookings, monthlyRevenue, villaChart, bookingStatus, paymentStatus,
    totalGuests:guests.size, repeatGuests:[...guests.values()].filter(n=>n>1).length,
    occupancyRate:villas.length ? Math.round(nights.size/((end-start)*villas.length)*100) : 0,
    mostBookedVilla:villaChart.some(v=>v.value>0) ? villaChart[0].name : '-',
    leastBookedVilla:villaChart.length ? villaChart.at(-1).name : '-'};
}
