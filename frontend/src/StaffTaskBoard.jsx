import RecordViewToggle from "./RecordViewToggle";
import BookingPreparationContext from "./BookingPreparationContext";
import { useState } from 'react';
import { ArrowUpRight, CalendarDays, CheckCircle2, ChevronRight, Search, X } from 'lucide-react';
import { checklistCount, filterTaskQueue, dateKey, dateLabel, isLate, isWorking, orderTasks, returnedFeedback, timeLabel } from './taskFlow.mjs';
import { RecordPagination } from './RecordListControls';
import { paginateRecords } from './recordListModel.mjs';
import { deskTableRows } from './frontDeskTableModel.mjs';

function taskStatusLabel(task) {
  if (isLate(task)) return 'Overdue';
  if (task.status === 'Pending') return 'Assigned';
  if (task.status === 'Pending Review') {
    return task.source === 'manual-maintenance-request' || task.maintenanceOnCall
      ? 'Repair verification'
      : 'Ready to complete';
  }
  return task.status;
}

export function TaskCard({ task, openTask, showOwner = false }) {
  const count = checklistCount(task);
  return <article className={`work-card ${isLate(task) ? 'late' : ''}`}>
    <div className="work-card-top"><span className={`work-status ${task.status === 'Completed' ? 'done' : task.status === 'In Progress' ? 'working' : ''}`}>{taskStatusLabel(task)}</span><span className={`work-priority ${task.priority?.toLowerCase()}`}>{task.priority} priority</span></div>{returnedFeedback(task) && <span className="work-correction-label">Changes requested</span>}
    <BookingPreparationContext task={task}/><h3>{task.title}</h3><p>{task.villaName || task.department || 'Villa operations'}</p>{showOwner && <p className="work-card-owner">{task.assignedTo || 'Unassigned staff'}</p>}
    <div className="work-card-progress"><span>{count.done} / {count.total} steps</span><span>{task.progress || 0}%</span></div><progress value={task.progress || 0} max="100" />
    <div className="work-card-bottom"><span><CalendarDays size={14}/>{dateLabel(task.dueDate)} · {timeLabel(task.dueTime)}</span><button type="button" className="work-task-view-button" aria-label={`View details for ${task.title}`} onClick={() => openTask(task.id)}>View details<ChevronRight size={15}/></button></div>
  </article>;
}
export default function StaffTaskBoard({ tasks, openTask, initialView = "My work", initialFocus = "All work", initialDueDate = "" }) {
  const [search,setSearch] = useState('');
  const [priority,setPriority] = useState('');
  const [status,setStatus] = useState('');
  const [layout,setLayout] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 650px)').matches ? 'cards' : 'table');
  const [dueDate,setDueDate] = useState(initialDueDate);
  const [sort,setSort] = useState({ key: '', direction: 'asc' });
  const [pageSize,setPageSize] = useState(10);
  const [position,setPosition] = useState({ signature: '', page: 0 });
  const filtered = filterTaskQueue(tasks,{view:initialView,focus:initialFocus,search,priority}).filter(task=>(!dueDate || task.dueDate===dueDate) && (!status || (status==='Overdue' ? isLate(task) : task.status===status)));
  const sortValues = {
    task: task => task.title,
    villa: task => task.villaName || task.department || '',
    due: task => `${task.dueDate || '9999'} ${task.dueTime || '23:59'}`,
    priority: task => ({High:0,Medium:1,Low:2}[task.priority] ?? 1),
    status: task => isLate(task) ? 'Overdue' : task.status,
    progress: task => Number(task.progress || 0),
  };
  const visible = sort.key ? deskTableRows(filtered,{sortValue:sortValues[sort.key],direction:sort.direction}) : filtered;
  const signature = JSON.stringify([initialView,initialFocus,search,priority,status,dueDate,pageSize,sort]);
  const page = paginateRecords(visible,position.signature === signature ? position.page : 0,pageSize);
  const changePage = value => setPosition({ signature, page: value });
  const sortBy = key => setSort(current=>({key,direction:current.key===key && current.direction==='asc'?'desc':'asc'}));
  const sortHeading = (key,label) => <th aria-sort={sort.key===key?sort.direction==='asc'?'ascending':'descending':'none'}><button type="button" className="work-task-sort-heading" onClick={()=>sortBy(key)}>{label}{sort.key===key?sort.direction==='asc'?' ↑':' ↓':' ↕'}</button></th>;
  return <div className="work-board">
    <div className="work-toolbar record-toolbar">
      <label className="work-search"><Search size={16}/><input type="search" aria-label="Search your tasks" placeholder="Search assignment, villa or booking…" value={search} onChange={event => setSearch(event.target.value)}/></label>
      <select aria-label="Filter task status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{['Pending','In Progress','Pending Review','Completed','Overdue'].map(value => <option key={value} value={value}>{value === 'Pending' ? 'To do' : value === 'Pending Review' ? 'Ready to complete' : value}</option>)}</select>
      <select aria-label="Filter task priority" value={priority} onChange={event => setPriority(event.target.value)}><option value="">All priorities</option>{['High','Medium','Low'].map(value => <option key={value}>{value}</option>)}</select>
      <input type="date" aria-label="Filter task due date" value={dueDate} onChange={event => setDueDate(event.target.value)}/>
      {(search || status || priority || dueDate || sort.key) && <button type="button" className="staff-btn-ghost" onClick={() => {setSearch('');setStatus('');setPriority('');setDueDate('');setSort({key:'',direction:'asc'});}}>Clear filters</button>}
    </div>
    <div className="record-results-bar"><span role="status">{visible.length} assignment{visible.length === 1 ? '' : 's'}{initialFocus !== 'All work' ? ` · ${initialFocus}` : initialView === 'My work' ? ' · Includes completed work' : ''}</span><RecordViewToggle value={layout} onChange={setLayout}/></div>
    {layout === 'cards' ? <div className="work-task-card-grid">{page.rows.map(task => <TaskCard key={task.id} task={task} openTask={openTask}/>)}</div> :
    <div className="work-task-table-wrap villa-table-frame" role="region" aria-label="Staff tasks table" tabIndex={0}><table className="work-task-table">
      <thead><tr>{sortHeading('task','Assignment')}{sortHeading('villa','Villa')}{sortHeading('due','Due')}{sortHeading('priority','Priority')}{sortHeading('status','Status')}{sortHeading('progress','Progress')}<th scope="col">Action</th></tr></thead>
      <tbody>{page.rows.map(task=><tr key={task.id}><td><strong>{task.title}</strong><small>{task.bookingCode || task.bookingId || 'No booking code'}</small></td><td>{task.villaName || task.department || 'Villa operations'}</td><td>{dateLabel(task.dueDate)} · {timeLabel(task.dueTime)}</td><td>{task.priority || 'Medium'}</td><td>{taskStatusLabel(task)}</td><td><span>{checklistCount(task).done} / {checklistCount(task).total} steps</span><progress value={task.progress || 0} max="100"/></td><td><button type="button" className="work-task-view-button" aria-label={`View ${task.title}`} onClick={()=>openTask(task.id)}>View details<ChevronRight size={14}/></button></td></tr>)}</tbody>
    </table></div>}
    {!visible.length && <div className="work-empty"><CheckCircle2 size={32}/><strong>{search || priority || status ? 'No matching tasks' : dueDate ? 'No assignments for this date' : initialFocus === 'Completed' ? 'No completed assignments yet' : initialView === 'My work' ? 'You’re all caught up' : 'Nothing here yet'}</strong><p>{dueDate ? 'Show all assignments to see work scheduled on other dates.' : search || priority || status ? 'Try adjusting your search, status or priority.' : initialFocus === 'Completed' ? 'Assignments appear here after you mark them complete.' : 'New assignments and updates will appear automatically.'}</p></div>}
    <RecordPagination page={page} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={setPageSize} label="assignments"/>
  </div>;
}
export function StaffOverview({ tasks, shift, openTask, viewTasks, viewCalendar }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFilter, setDateFilter] = useState('');
  const todayKey = dateKey();
  const query = search.trim().toLowerCase();
  const matchingTasks = tasks.filter(task => {
    const matchesSearch = `${task.title || ''} ${task.villaName || ''} ${task.department || ''} ${task.bookingCode || ''} ${task.bookingId || ''}`.toLowerCase().includes(query);
    const matchesStatus = !statusFilter || task.status === statusFilter;
    const matchesDate = !dateFilter
      || (dateFilter === 'today' && task.dueDate === todayKey)
      || (dateFilter === 'upcoming' && task.dueDate > todayKey)
      || (dateFilter === 'overdue' && isLate(task));
    return task.status !== 'Cancelled' && matchesSearch && matchesStatus && matchesDate;
  });
  const hasFilters = !!(query || statusFilter || dateFilter);
  const active = orderTasks(matchingTasks.filter(isWorking));
  const today = matchingTasks.filter(task => task.dueDate === todayKey);
  const focus = active[0];
  return <div className="work-overview">
    <section className="work-overview-filters" aria-label="Filter assignments">
      <label className="work-overview-search"><Search size={17}/><input aria-label="Search assignments" placeholder="Search assignments, villas or booking codes" value={search} onChange={event => setSearch(event.target.value)}/></label>
      <label className="work-overview-select"><span>Status</span><select aria-label="Filter by assignment status" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">All statuses</option><option value="Pending">To do</option><option value="In Progress">In progress</option><option value="Pending Review">In review</option><option value="Completed">Completed</option></select></label>
      <label className="work-overview-select"><CalendarDays size={16}/><select aria-label="Filter by due date" value={dateFilter} onChange={event => setDateFilter(event.target.value)}><option value="">Any due date</option><option value="today">Due today</option><option value="upcoming">Upcoming</option><option value="overdue">Overdue</option></select></label>
      {hasFilters && <button type="button" className="work-overview-clear" onClick={() => { setSearch(''); setStatusFilter(''); setDateFilter(''); }}><X size={15}/> Clear filters</button>}
    </section>
    {tasks.some(task=>isLate(task)) && <section className="preparation-overdue-notice"><div><strong>{tasks.filter(task=>isLate(task)).length} assignment(s) past the preparation deadline</strong><p>Ask your administrator to review the schedule or reassign the work before guest arrival.</p></div><button className="staff-btn-ghost" onClick={() => viewTasks('My work','Overdue')}>Review overdue work</button></section>}
    <div className="work-overview-columns"><section className="work-focus"><div className="work-section-title"><div><small>NEXT ASSIGNMENT</small><h3>Your next task</h3></div><span className="work-shift">{shift || 'Shift not assigned'}</span></div>{focus ? <><TaskCard task={focus} openTask={openTask}/></> : <div className="work-empty"><CheckCircle2 size={32}/><strong>{hasFilters ? 'No open work matches' : 'No open work'}</strong><p>{hasFilters ? 'Try adjusting or clearing your filters.' : 'New booking assignments appear automatically.'}</p></div>}<button className="work-text-button" onClick={()=>viewTasks('My work','All work')}>See all my work <ChevronRight size={15}/></button></section>
    <section className="work-today"><div className="work-section-title"><div><small>{dateLabel(todayKey, {weekday:'long'})}</small><h3>Today’s schedule</h3></div><button className="work-icon-button" aria-label="Open calendar" onClick={viewCalendar}><ArrowUpRight size={18}/></button></div>{orderTasks(today).slice(0,5).map(task=><button className="work-agenda-row" key={task.id} onClick={()=>openTask(task.id)}><time>{timeLabel(task.dueTime)}</time><span><strong>{task.title}</strong><small>{task.villaName} · {task.status === 'Pending' ? 'To do' : task.status}</small></span><ChevronRight size={16}/></button>)}{!today.length && <p className="work-context">{hasFilters ? 'No assignments match these filters.' : 'No preparation scheduled today.'}</p>}<button className="work-text-button" onClick={viewCalendar}>View calendar <ChevronRight size={15}/></button></section></div>
  </div>;
}
