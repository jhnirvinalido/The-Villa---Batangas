import { CheckCircle2, Circle, X } from 'lucide-react';
import { deskDate, peso } from './frontDeskModel.mjs';
import { timeLabel } from './taskFlow.mjs';

function Details({ rows }) {
  return <dl className="fd-details">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'Not provided'}</dd></div>)}</dl>;
}

export default function FrontDeskRecordDetails({ task, receipt, staff, bookings, onClose, status, work }) {
  if (task) {
    const member = staff.find(person => person.id === task.assignedStaffId);
    const booking = bookings.find(item => String(item.id) === String(task.bookingId || task.booking_id));
    const checklist = task.checklist || [];
    const done = checklist.filter(item => item.done).length;
    return <>
      <header><div><span className="fd-eyebrow">Staff monitoring · Read only</span><h2>{task.title || `${task.villaName || 'Villa'} preparation`}</h2></div><button type="button" className="fd-icon-button" aria-label="Close assignment details" onClick={onClose}><X size={22}/></button></header>
      <div className="fd-stack">
        <Details rows={[
          ['Villa', task.villaName], ['Booking reference', task.bookingCode || booking?.bookingCode],
          ['Guest', booking?.guestName], ['Assigned staff', task.assignedTo || member?.name || member?.fullName || 'Unassigned'],
          ['Staff shift', member?.shift], ['Scheduled preparation', `${deskDate(task.dueDate)} · ${timeLabel(task.dueTime)}`],
          ['Work type', work], ['Status', status],
        ]}/>
        <section className="fd-record-section"><h3>Instructions</h3><p className="fd-record-copy">{task.description || 'No additional instructions.'}</p></section>
        <section className="fd-record-section"><h3>Checklist · {done} of {checklist.length} complete</h3>
          {checklist.length ? <ul className="fd-task-checklist">{checklist.map((item, index) => <li key={item.id || index}>{item.done ? <CheckCircle2 size={19}/> : <Circle size={19}/>}<span>{item.label || 'Checklist step'}</span><small>{item.done ? 'Complete' : 'Pending'}</small></li>)}</ul> : <p>No checklist steps have been added.</p>}
        </section>
        <section className="fd-record-section"><h3>Handover notes</h3><p className="fd-record-copy">{task.notes || 'No handover notes yet.'}</p></section>
        {task.statusHistory?.length > 0 && <details className="fd-record-section"><summary>Activity history</summary><ol className="fd-record-history">{[...task.statusHistory].reverse().map((entry, index) => <li key={entry.id || index}><strong>{entry.status}</strong><p className="fd-record-copy">{entry.note}</p>{entry.timestamp && <small>{new Date(entry.timestamp).toLocaleString('en-PH', { timeZone: 'Asia/Manila' })}</small>}</li>)}</ol></details>}
        <footer><button type="button" className="fd-button" onClick={onClose}>Close</button></footer>
      </div>
    </>;
  }
  if (receipt) return <>
    <header><div><span className="fd-eyebrow">Recorded front desk payment</span><h2>{receipt.receiptNumber || receipt.reference || 'Receipt details'}</h2></div><button type="button" className="fd-icon-button" aria-label="Close payment details" onClick={onClose}><X size={22}/></button></header>
    <div className="fd-stack"><Details rows={[
      ['Booking reference', receipt.bookingCode], ['Guest', receipt.guestName || receipt.customerName], ['Payer', receipt.payerName], ['Villa', receipt.villaName],
      ['Method', receipt.method], ['Amount received', peso(receipt.amount)], ['Room balance settled', peso(receipt.roomBalance)], ['Additional charges', peso(receipt.otherChargesTotal)],
      ['Cash tendered', receipt.method?.toLowerCase() === 'cash' ? peso(receipt.cashTendered) : 'Not applicable'], ['Change given', receipt.method?.toLowerCase() === 'cash' ? peso(receipt.changeGiven) : 'Not applicable'],
      ['Cashier', receipt.cashierName], ['Processed', receipt.processedAt ? new Date(receipt.processedAt).toLocaleString('en-PH', { timeZone: 'Asia/Manila' }) : 'Recorded'],
      ['Payment reference', receipt.reference], ['Payment timing', receipt.paymentTimingLabel],
    ]}/>
      {receipt.otherCharges?.length > 0 && <section className="fd-record-section"><h3>Additional charges</h3><ul>{receipt.otherCharges.map((charge, index) => <li key={charge.id || index}>{charge.description} · {peso(charge.amount)}</li>)}</ul></section>}
      <section className="fd-record-section"><h3>Notes</h3><p className="fd-record-copy">{receipt.notes || 'No payment notes.'}</p></section>
      <footer><button type="button" className="fd-button" onClick={onClose}>Close</button></footer>
    </div>
  </>;
  return null;
}
