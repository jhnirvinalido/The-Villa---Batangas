import { useState } from 'react';
import { Search } from 'lucide-react';
import { assignmentKind, bookingsNeedingStaff, isPreparation } from './bookingPreparation.mjs';
import { dateLabel, isLate, orderTasks, timeLabel } from './taskFlow.mjs';

const views = [
  { label: 'Active', statuses: ['Pending', 'In Progress'] },
  { label: 'For review', statuses: ['Pending Review'] },
  { label: 'Approved', statuses: ['Completed'] },
];

export default function AdminTaskHub({ tasks, bookings = [], staff, openTask, openBooking, manageStaff }) {
  const [view, setView] = useState('Active');
  const [owner, setOwner] = useState('');
  const [search, setSearch] = useState('');
  const query = search.trim().toLowerCase();
  const filtered = tasks.filter(task => (!owner || task.assignedStaffId === owner)
    && `${task.title} ${task.assignedTo || ''} ${task.villaName || ''} ${task.bookingCode || ''}`.toLowerCase().includes(query));
  const selected = views.find(item => item.label === view);
  const visible = orderTasks(filtered.filter(task => selected.statuses.includes(task.status)));
  const missing = bookingsNeedingStaff(bookings, tasks);

  return <div className="team-work-hub">
    {missing.length > 0 && <details className="assignment-staffing-alert">
      <summary>{missing.length} booking{missing.length === 1 ? '' : 's'} need preparation staff</summary>
      <div className="assignment-staffing-content">
        <div className="assignment-staffing-heading"><span>Check Housekeeping shifts and scheduled work.</span><button className="admin-btn-ghost" onClick={manageStaff}>Staff directory</button></div>
        {missing.map(booking => <div className="assignment-staffing-row" key={booking.id}><span><strong>{booking.villaName}</strong><small>{booking.bookingCode} · Arrival {dateLabel(booking.checkIn)}</small></span><button className="admin-btn-ghost" onClick={() => openBooking?.(booking)}>View booking</button></div>)}
      </div>
    </details>}
    <div className="team-work-filters">
      <label className="work-search"><Search size={16}/><input aria-label="Search assignments" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search villa, booking or staff…"/></label>
      <select aria-label="Filter by staff member" value={owner} onChange={event => setOwner(event.target.value)}><option value="">All staff</option>{staff.map(member => <option key={member.id} value={member.id}>{member.name}</option>)}</select>
    </div>
    <div className="assignment-status-tabs assignment-essential-tabs" role="group" aria-label="Assignment status">
      {views.map(item => <button type="button" key={item.label} className={`assignment-status-tab${view === item.label ? ' is-active' : ''}`} aria-pressed={view === item.label} onClick={() => setView(item.label)}><span>{item.label}</span><small>{filtered.filter(task => item.statuses.includes(task.status)).length}</small></button>)}
    </div>
    <section className="assignment-status-screen" aria-label={`${view} assignments`}>
      {visible.length ? <div className="assignment-table-wrap"><table className="assignment-table">
        <thead><tr><th>Villa / booking</th><th>Staff</th><th>Prepare by</th><th>Status</th><th>Checklist</th></tr></thead>
        <tbody>{visible.map(task => <tr key={task.id}>
          <td><button className="assignment-table-task" aria-label={`Open ${task.title}`} onClick={() => openTask(task.id)}><span>{task.villaName || task.title}</span><small>{task.bookingCode || task.title}</small></button><small className="assignment-table-secondary">{assignmentKind(task)}</small>{isPreparation(task) && task.bookingCheckIn && <small className="assignment-table-secondary">Arrival {dateLabel(task.bookingCheckIn)}</small>}</td>
          <td>{task.assignedTo || 'Unassigned'}</td>
          <td className={isLate(task) ? 'is-overdue' : ''}>{dateLabel(task.dueDate)}<small className="assignment-table-secondary">{timeLabel(task.dueTime)}</small></td>
          <td>{isLate(task) ? 'Overdue' : task.status === 'Pending' ? 'Assigned' : task.status === 'Pending Review' ? 'For review' : task.status === 'Completed' ? 'Approved' : task.status}</td>
          <td><div className="assignment-table-progress"><span>{(task.checklist || []).filter(item => item.done).length} / {(task.checklist || []).length} steps</span><progress value={task.progress || 0} max="100"/></div></td>
        </tr>)}</tbody>
      </table></div> : <div className="assignment-table-empty">{search || owner ? 'No matching assignments.' : `No ${view.toLowerCase()} assignments.`}</div>}
    </section>
  </div>;
}
