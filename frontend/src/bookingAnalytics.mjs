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

function analyticsPeriod(year, period) {
  const unit = ['week', 'month'].includes(period?.unit) ? period.unit : 'year';
  const selectedDay = dayNumber(period?.date || `${year}-01-01`);
  const date = Number.isFinite(selectedDay) ? selectedDay : Date.UTC(year, 0, 1) / 86400000;
  let start, end, labels;

  if (unit === 'week') {
    const weekday = new Date(date * 86400000).getUTCDay();
    start = date - ((weekday + 6) % 7);
    end = start + 7;
    labels = Array.from({length: 7}, (_, index) => {
      const current = new Date((start + index) * 86400000);
      return new Intl.DateTimeFormat('en', {weekday: 'short', day: 'numeric', timeZone: 'UTC'}).format(current);
    });
  } else if (unit === 'month') {
    const current = new Date(date * 86400000);
    const year = current.getUTCFullYear();
    const month = current.getUTCMonth();
    start = Date.UTC(year, month, 1) / 86400000;
    end = Date.UTC(year, month + 1, 1) / 86400000;
    labels = Array.from({length: end - start}, (_, index) => String(index + 1));
  } else {
    const selectedYear = new Date(date * 86400000).getUTCFullYear();
    start = Date.UTC(selectedYear, 0, 1) / 86400000;
    end = Date.UTC(selectedYear + 1, 0, 1) / 86400000;
    labels = MONTHS;
  }

  return {
    unit,
    start,
    end,
    labels,
    bucketIndex(day) {
      return unit === 'year'
        ? new Date(day * 86400000).getUTCMonth()
        : day - start;
    },
  };
}

export function bookingAnalytics(bookings, villas, year, frontDeskPayments = [], assignmentSummary = {}, period = {}) {
  const range = analyticsPeriod(year, period);
  const monthlyBookings = Array(range.labels.length).fill(0), monthlyRevenue = Array(range.labels.length).fill(0);
  const bookingStatus = {Pending:0, Confirmed:0, 'Checked In':0, Completed:0};
  const paymentStatus = {Paid:0, Partial:0};
  const bookingChannel = {Airbnb:0, 'Manual Booking (Messenger)':0, 'The Villa':0};
  const assignmentProgress = {
    Pending: Number(assignmentSummary.pending) || 0,
    'In Progress': Number(assignmentSummary.inProgress) || 0,
    'Pending Review': Number(assignmentSummary.review) || 0,
    Overdue: Number(assignmentSummary.overdue) || 0,
    Completed: Number(assignmentSummary.completed) || 0,
  };
  let pendingPaymentCount = 0, totalOutstandingBalance = 0;
  const performance = new Map(villas.map(v => [v.id, {name:v.title || v.name, value:0, revenue:0}]));
  const guests = new Map(), nights = new Set(), seenPayments = new Set();
  const {start, end} = range;
  const recordPayment = (payment, key, villaIds = []) => {
    if (seenPayments.has(key)) return;
    seenPayments.add(key);
    if (!isSuccessfulPayment(payment.status)) return;
    const amount = Number(payment.amount);
    const paidDay = dayNumber(payment.processedAt ?? payment.processed_at ?? payment.created_at);
    if (!(Number.isFinite(amount) && amount > 0 && paidDay >= start && paidDay < end)) return;
    monthlyRevenue[range.bucketIndex(paidDay)] += amount;
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
    const channel = String(b.bookingChannel ?? b.booking_channel ?? '')
      .trim()
      .toLowerCase()
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ');
    const external = channel === 'airbnb' || channel.includes('airbnb');
    const manual = [
      'manual',
      'manual booking',
      'messenger',
      'messenger booking',
      'manual booking (messenger)',
    ].includes(channel) || channel.includes('manual') || channel.includes('messenger');
    bookingDetails.set(String(b.id), {ids, cancelled, external});
    const paid = Number(b.amountPaid ?? b.amount_paid) || 0;
    const total = Number(b.totalAmount ?? b.total_amount) || 0;
    const storedBalance = Number(b.balanceAmount ?? b.balance_amount);
    const balance = Math.max(
      Number.isFinite(storedBalance) ? storedBalance : 0,
      total - paid,
      0,
    );
    const checkInInPeriod = checkIn >= start && checkIn < end;
    const markedUnpaid = String(b.paymentStatus || '').trim().toLowerCase() === 'unpaid';
    const graphEligible = !markedUnpaid && (external || paid > 0);
    if (!cancelled && checkInInPeriod && !external && balance > 0) {
      pendingPaymentCount++;
      totalOutstandingBalance += balance;
    }
    // Payments are dated by receipt, not by the reservation's future stay date.
    for (const p of b.paymentHistory || []) {
      if (!cancelled && !external) recordPayment(p, `booking:${b.id}:${p.id}`, ids);
    }
    if (cancelled || !checkInInPeriod || !graphEligible) continue;
    if (confirmed && Number.isFinite(checkIn) && Number.isFinite(checkOut)) {
      for (let day=Math.max(start,checkIn); day<Math.min(end,checkOut); day++) {
        for (const id of ids) if (performance.has(id)) nights.add(`${id}:${day}`);
      }
    }
    const bucket = /checked.?in/.test(status) ? 'Checked In'
      : /complet|checked.?out/.test(status) ? 'Completed' : confirmed ? 'Confirmed' : 'Pending';
    bookingStatus[bucket]++;
    if (external) {
      bookingChannel.Airbnb++;
    } else if (manual) {
      bookingChannel['Manual Booking (Messenger)']++;
    } else {
      bookingChannel['The Villa']++;
      paymentStatus[balance <= 0 ? 'Paid' : 'Partial']++;
    }
    if (!confirmed) continue;
    monthlyBookings[range.bucketIndex(checkIn)]++;
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
    if (!booking?.cancelled && !booking?.external) {
      recordPayment(payment, `front-desk:${payment.id}`, booking?.ids || []);
    }
  }
  const villaChart=[...performance.values()].sort((a,b)=>b.value-a.value);
  return {year, months:range.labels, monthlyBookings, monthlyRevenue, totalRevenue:monthlyRevenue.reduce((total, amount)=>total+amount,0),
    totalBookings:Object.values(bookingStatus).reduce((total, count)=>total+count,0), villaChart, bookingStatus, paymentStatus,
    bookingChannel, assignmentProgress, pendingPaymentCount, totalOutstandingBalance,
    totalGuests:guests.size, repeatGuests:[...guests.values()].filter(n=>n>1).length,
    occupancyRate:villas.length ? Math.round(nights.size/((end-start)*villas.length)*100) : 0,
    mostBookedVilla:villaChart.some(v=>v.value>0) ? villaChart[0].name : '-',
    leastBookedVilla:villaChart.length ? villaChart.at(-1).name : '-'};
}
