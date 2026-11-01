import { dateKey } from './taskFlow.mjs';

const label = value => String(value || '').trim().toLowerCase().replace(/[_-]+/g, ' ');
export const peso = value => new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' }).format(Number(value || 0));
export const deskDate = value => value ? new Date(`${String(value).slice(0, 10)}T00:00:00+08:00`).toLocaleDateString('en-PH', { timeZone: 'Asia/Manila', month: 'short', day: 'numeric', year: 'numeric' }) : 'Not scheduled';

export function normalizeDeskBooking(row) {
  const totalAmount = Number(row.total_amount ?? row.totalAmount ?? 0);
  const amountPaid = Number(row.amount_paid ?? row.amountPaid ?? 0);
  const balanceAmount = Math.max(0, Number(row.balance_amount ?? row.balanceAmount ?? totalAmount - amountPaid));
  const bookingStatus = row.booking_status || row.bookingStatus || 'Pending';
  const stayStatus = row.stay_status || row.stayStatus || bookingStatus;
  const bookingChannel = label(row.booking_channel || row.bookingChannel);
  const external = bookingChannel === 'airbnb';
  const checkedOut = Boolean(row.checked_out_at || row.checkedOutAt) || [stayStatus, bookingStatus].some(value => ['completed', 'checked out', 'checkout'].includes(label(value)));
  const checkedIn = !checkedOut && [stayStatus, bookingStatus].some(value => ['checked in', 'check in', 'checkin'].includes(label(value)));
  const cancelled = ['cancelled', 'canceled', 'expired', 'refunded'].includes(label(bookingStatus));
  const paymentChoice = label(row.payment_choice || row.paymentChoice || (amountPaid >= totalAmount ? 'full' : 'half'));
  const verified = external || (totalAmount > 0 && amountPaid >= (paymentChoice === 'full' ? totalAmount : totalAmount / 2));
  return {
    ...row, id: row.id, bookingCode: row.booking_code || row.bookingCode || row.id,
    guestName: row.customer_name || row.guest_name || row.guestName || 'Guest',
    phone: row.customer_phone || row.phone || '', email: row.customer_email || row.email || '',
    villaName: row.villa_name || row.villaName || 'Villa',
    checkIn: String(row.check_in_date || row.checkIn || '').slice(0, 10),
    checkOut: String(row.check_out_date || row.checkOut || '').slice(0, 10),
    guestCount: row.guest_count || row.guestCount || 1,
    totalAmount, amountPaid, balanceAmount, bookingStatus, stayStatus, paymentChoice,
    checkedIn, checkedOut, cancelled, verified, external,
    paymentTiming: row.front_desk_balance_timing || row.balancePaymentTiming || '',
    walkIn: bookingChannel === 'walk in' || String(row.notes || '').includes('[Walk-in booking staff:'),
    paymentStatus: external ? 'Handled by Airbnb' : balanceAmount <= 0 && amountPaid > 0 ? 'Paid' : amountPaid > 0 ? 'Partially paid' : 'Unpaid',
  };
}

export function deskBookingAction(booking, today = dateKey()) {
  if (booking.cancelled || booking.checkedOut) return '';
  if (booking.checkedIn) return !booking.external && booking.balanceAmount > 0 ? 'payment' : 'checkout';
  if (!booking.verified || label(booking.bookingStatus) !== 'confirmed' || booking.checkIn !== today) return '';
  if (!booking.external && booking.balanceAmount > 0 && booking.paymentTiming !== 'check_out') return 'payment';
  return 'checkin';
}

export function bookingReadiness(booking, tasks) {
  const preparation = tasks.filter(task => String(task.bookingId || task.booking_id) === String(booking.id)
    && (task.assignmentType || task.assignment_type) === 'housekeeping-pre-arrival'
    && task.status !== 'Cancelled');
  if (booking.checkedIn) return { label: 'Guest in house', staff: '', tone: 'neutral' };
  if (!preparation.length) return { label: 'No preparation assigned', staff: '', tone: 'warning' };
  const ready = preparation.every(task => task.status === 'Completed');
  return { label: ready ? 'Ready · approved' : preparation.some(task => task.status === 'Pending Review') ? 'Awaiting approval' : 'Preparation in progress', staff: [...new Set(preparation.map(task => task.assignedTo).filter(Boolean))].join(', '), tone: ready ? 'success' : 'warning' };
}

export function minimumVillaCount(guests, villas) {
  let capacity = 0;
  const sizes = villas.filter(villa => villa.available).map(villa => Number(villa.capacity || 0)).sort((a, b) => b - a);
  for (let index = 0; index < sizes.length; index++) {
    capacity += sizes[index];
    if (capacity >= Number(guests)) return index + 1;
  }
  return Infinity;
}
