// Both workspaces use the same reservation filters. Arrival date is the stay's
// check-in date, never the date a payment or booking was created.
export function filterBookingRecords(bookings, { search = '', status = 'All', arrivalDate = '' } = {}) {
  const query = search.trim().toLowerCase();
  return bookings.filter(booking => {
    const reservation = String(booking.bookingStatus || booking.status || '').toLowerCase();
    const payment = String(booking.paymentStatus || '').toLowerCase();
    const matchesStatus = status === 'All'
      || (status === 'Paid' && payment === 'paid')
      || (status === 'Partially paid' && /partial|downpayment/.test(payment))
      || (status === 'Unpaid' && /unpaid|partial|downpayment/.test(payment))
      || (status === 'Completed' && (booking.lifecycleStatus === 'Completed' || /completed|checked out/.test(reservation)))
      || (status === 'Overdue/Cancelled' && /overdue|cancelled|canceled|expired/.test(reservation));
    return matchesStatus
      && (!arrivalDate || String(booking.checkIn || '').slice(0, 10) === arrivalDate)
      && (!query || [booking.bookingCode, booking.guestName, booking.villaName, booking.phone, booking.paymentStatus].join(' ').toLowerCase().includes(query));
  }).sort((a, b) => String(a.checkIn || '').localeCompare(String(b.checkIn || ''))
    || String(a.bookingCode || '').localeCompare(String(b.bookingCode || '')));
}
