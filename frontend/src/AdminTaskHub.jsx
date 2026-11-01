import RecordViewToggle from "./RecordViewToggle";
import { TaskCard } from "./StaffTaskBoard";
import { useState } from 'react';
import { Search } from 'lucide-react';
import { assignmentKind, bookingsNeedingStaff, isPreparation } from './bookingPreparation.mjs';
import { dateLabel, isLate, orderTasks, timeLabel } from './taskFlow.mjs';
import { RecordPagination } from './RecordListControls';
import { paginateRecords } from './recordListModel.mjs';
import { deskTableRows } from './frontDeskTableModel.mjs';

const views = [
  { label: 'Active', statuses: ['Pending', 'In Progress'] },
  { label: 'For review', statuses: ['Pending Review'] },
  { label: 'Approved', statuses: ['Completed'] },
];

export default function AdminTaskHub({ tasks, bookings = [], staff, openTask, openBooking, manageStaff, readOnly = false, initialDay = '' }) {
  const [layout, setLayout] = useState('table');
  const [view, setView] = useState('Active');
  const [owner, setOwner] = useState('');
  const [search, setSearch] = useState('');
  const [day, setDay] = useState(initialDay);
  const [sort, setSort] = useState({ key: '', direction: 'asc' });
  const [pageSize, setPageSize] = useState(10);
  const [position, setPosition] = useState({ signature: '', page: 0 });
  const query = search.trim().toLowerCase();
  const filtered = tasks.filter(task => (!owner || task.assignedStaffId === owner)
    && (!day || String(task.dueDate || '').slice(0, 10) === day)
    && `${task.title} ${task.assignedTo || ''} ${task.villaName || ''} ${task.bookingCode || ''}`.toLowerCase().includes(query));
  const selected = views.find(item => item.label === view);
  const baseRows = orderTasks(filtered.filter(task => selected.statuses.includes(task.status)));
  const sortValues = {
    task: task => task.villaName || task.title,
    staff: task => task.assignedTo || '',
    due: task => `${task.dueDate || '9999'} ${task.dueTime || '23:59'}`,
    status: task => isLate(task) ? 'Overdue' : task.status,
    progress: task => Number(task.progress || 0),
  };
  const visible = sort.key
    ? deskTableRows(baseRows, { sortValue: sortValues[sort.key], direction: sort.direction })
    : baseRows;
  const signature = JSON.stringify([view,owner,search,day,pageSize,sort]);
  const page = paginateRecords(visible,position.signature === signature ? position.page : 0,pageSize);
  const changePage = value => setPosition({ signature, page: value });
  const sortBy = key => setSort(current => ({
    key,
    direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
  }));
  const sortHeading = (key, label) => <th aria-sort={sort.key === key ? sort.direction === 'asc' ? 'ascending' : 'descending' : 'none'}>
    <button type="button" className="assignment-sort-heading" onClick={() => sortBy(key)}>{label}{sort.key === key ? sort.direction === 'asc' ? ' ↑' : ' ↓' : ' ↕'}</button>
  </th>;
  const missing = bookingsNeedingStaff(bookings, tasks).filter(booking => !day || booking.checkIn === day);

  return <div className="team-work-hub">
    {missing.length > 0 && <details className="assignment-staffing-alert">
      <summary>{missing.length} booking{missing.length === 1 ? '' : 's'} need preparation staff</summary>
      <div className="assignment-staffing-content">
        <div className="assignment-staffing-heading"><span>Check Housekeeping shifts and scheduled work.</span>{!readOnly && <button className="admin-btn-ghost" onClick={manageStaff}>Staff directory</button>}</div>
        {missing.map(booking => <div className="assignment-staffing-row" key={booking.id}><span><strong>{booking.villaName}</strong><small>{booking.bookingCode} · Arrival {dateLabel(booking.checkIn)}</small></span>{!readOnly && <button className="admin-btn-ghost" onClick={() => openBooking?.(booking)}>View booking</button>}</div>)}
      </div>
    </details>}
    <div className="team-work-filters">
      <label className="work-search"><Search size={16}/><input aria-label="Search assignments" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search villa, booking or staff…"/></label>
      <select aria-label="Filter by staff member" value={owner} onChange={event => setOwner(event.target.value)}><option value="">All staff</option>{staff.map(member => <option key={member.id} value={member.id}>{member.name}</option>)}</select>
      <label>Preparation day <input type="date" aria-label="Filter by preparation day" value={day} onChange={event => setDay(event.target.value)}/></label>
      {day && <button type="button" className="admin-btn-ghost" onClick={() => setDay('')}>All days</button>}
      {sort.key && <button type="button" className="admin-btn-ghost" onClick={() => setSort({ key: '', direction: 'asc' })}>Clear sort</button>}
    </div>
    <div className="assignment-status-tabs assignment-essential-tabs" role="group" aria-label="Assignment status">
      {views.map(item => <button type="button" key={item.label} className={`assignment-status-tab${view === item.label ? ' is-active' : ''}`} aria-pressed={view === item.label} onClick={() => setView(item.label)}><span>{item.label}</span><small>{filtered.filter(task => item.statuses.includes(task.status)).length}</small></button>)}
    </div>
    {!readOnly && <div className="record-results-bar"><span>{visible.length} matching assignment{visible.length === 1 ? '' : 's'}</span><RecordViewToggle value={layout} onChange={setLayout}/></div>}
    <section className="assignment-status-screen" aria-label={`${view} assignments`}>
      {visible.length ? layout === 'cards' && !readOnly ? <div className="work-task-card-grid">{page.rows.map(task => <TaskCard key={task.id} task={task} openTask={openTask} showOwner/>)}</div> : <div className="assignment-table-wrap" role="region" aria-label="Assignments table" tabIndex={0}><table className="assignment-table">
        <thead><tr>{sortHeading('task','Villa / booking')}{sortHeading('staff','Staff')}{sortHeading('due','Prepare by')}{sortHeading('status','Status')}{sortHeading('progress','Checklist')}{!readOnly && <th scope="col">Action</th>}</tr></thead>
        <tbody>{page.rows.map(task => <tr key={task.id}>
          <td><span className="assignment-table-task"><span>{task.villaName || task.title}</span><small>{task.bookingCode || task.title}</small></span><small className="assignment-table-secondary">{assignmentKind(task)}</small>{isPreparation(task) && task.bookingCheckIn && <small className="assignment-table-secondary">Arrival {dateLabel(task.bookingCheckIn)}</small>}</td>
          <td>{task.assignedTo || 'Unassigned'}</td>
          <td className={isLate(task) ? 'is-overdue' : ''}>{dateLabel(task.dueDate)}<small className="assignment-table-secondary">{timeLabel(task.dueTime)}</small></td>
          <td>{isLate(task) ? 'Overdue' : task.status === 'Pending' ? 'Assigned' : task.status === 'Pending Review' ? 'For review' : task.status === 'Completed' ? 'Approved' : task.status}</td>
          <td><div className="assignment-table-progress"><span>{(task.checklist || []).filter(item => item.done).length} / {(task.checklist || []).length} steps</span><progress value={task.progress || 0} max="100"/></div></td>
          {!readOnly && <td><button type="button" className="assignment-view-button" aria-label={`View details for ${task.title}`} onClick={() => openTask(task.id)}>View details</button></td>}
        </tr>)}</tbody>
      </table></div> : <div className="assignment-table-empty">{search || owner || day ? 'No matching assignments.' : `No ${view.toLowerCase()} assignments.`}</div>}
      <RecordPagination page={page} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={setPageSize} label="assignments"/>
    </section>
  </div>;
}
