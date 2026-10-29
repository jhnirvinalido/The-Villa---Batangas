import { dateKey } from './taskFlow.mjs';

export const isPreparation = task => (task.assignmentType || task.assignment_type) === 'housekeeping-pre-arrival';
export const isAutomatic = task => task.source === 'automatic-booking-preparation';
export function assignmentKind(task) {
  if (isPreparation(task)) return isAutomatic(task) ? 'Automatic preparation' : 'Arrival preparation';
  return (task.assignmentType || task.assignment_type) === 'housekeeping-turnover' ? 'Checkout turnover' : 'Operations';
}

// Match the allocator's confirmation/payment rules using normalized bookings.
// A cancelled preparation task is an explicit admin override, not a retry job.
export function bookingsNeedingStaff(bookings, tasks, today = dateKey()) {
  return bookings.filter(booking => {
    const total = Number(booking.totalAmount || booking.total_amount || 0);
    const paid = Number(booking.amountPaid ?? booking.amount_paid ?? 0);
    const required = booking.paymentChoice === 'full' ? total : Math.round(total * 50) / 100;
    return booking.bookingStatus === 'Confirmed' && total > 0 && paid >= required
      && ['Paid', 'Partial', 'Partially Paid', '50% Downpayment'].includes(booking.paymentStatus)
      && booking.checkIn >= today
      && !['Checked In', 'Checked Out', 'Completed', 'Cancelled'].includes(booking.stayStatus)
      && !tasks.some(task => String(task.bookingId) === String(booking.id) && isPreparation(task)
        && (task.status !== 'Cancelled' || isAutomatic(task)));
  }).sort((a, b) => a.checkIn.localeCompare(b.checkIn));
}
