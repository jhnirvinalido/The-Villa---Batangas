import { assignmentKind, isPreparation } from './bookingPreparation.mjs';
import { dateLabel } from './taskFlow.mjs';

export default function BookingPreparationContext({ task }) {
  const arrival = task.bookingCheckIn || task.booking_check_in;
  return <div className="preparation-context">
    <span className="preparation-kind">{assignmentKind(task) === 'Automatic preparation' ? 'System assigned' : assignmentKind(task)}</span>
    <span>{task.bookingCode || 'General assignment'}</span>
    {isPreparation(task) && arrival && <span>Guest arrival · {dateLabel(arrival)}</span>}
  </div>;
}
