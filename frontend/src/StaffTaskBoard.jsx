import BookingPreparationContext from "./BookingPreparationContext";
import { useState } from 'react';
import { ArrowUpRight, CalendarDays, CheckCircle2, ChevronRight, Circle, Clock3, Search } from 'lucide-react';
import { checklistCount, filterTaskQueue, dateKey, dateLabel, isLate, isWorking, orderTasks, readyForReview, returnedFeedback, timeLabel } from './taskFlow.mjs';

export function TaskCard({ task, openTask, showOwner = false, actionLabel }) {
  const count = checklistCount(task);
  return <button className={`work-card ${isLate(task) ? 'late' : ''}`} onClick={() => openTask(task.id)}>
    <div className="work-card-top"><span className={`work-status ${task.status === 'Completed' ? 'done' : task.status === 'In Progress' ? 'working' : ''}`}>{isLate(task) ? 'Overdue' : task.status === 'Pending' ? 'Assigned' : task.status === 'Pending Review' ? 'Awaiting approval' : task.status}</span><span className={`work-priority ${task.priority?.toLowerCase()}`}>{task.priority} priority</span></div>{returnedFeedback(task) && <span className="work-correction-label">Changes requested</span>}
    <BookingPreparationContext task={task}/><h3>{task.title}</h3><p>{task.villaName || task.department || 'Villa operations'}</p>{showOwner && <p className="work-card-owner">{task.assignedTo || 'Unassigned staff'}</p>}
    <div className="work-card-progress"><span>{count.done} / {count.total} steps</span><span>{task.progress || 0}%</span></div><progress value={task.progress || 0} max="100" />
    <div className="work-card-bottom"><span><CalendarDays size={14}/>{dateLabel(task.dueDate)} · {timeLabel(task.dueTime)}</span><strong>{actionLabel || (readyForReview(task) ? 'Ready to submit' : task.status === 'Pending' ? 'View & start' : task.status === 'In Progress' ? 'Continue' : 'View details')}<ChevronRight size={15}/></strong></div>
  </button>;
}
export default function StaffTaskBoard({ tasks, openTask, initialView = "My work", initialFocus = "All work", initialDueDate = "" }) {
  const [search,setSearch] = useState('');
  const [priority,setPriority] = useState('');
  const [dueDate,setDueDate] = useState(initialDueDate);
  const visible = filterTaskQueue(tasks,{view:initialView,focus:initialFocus,search,priority}).filter(task=>!dueDate || task.dueDate===dueDate);
  return <div className="work-board">
    <div className="work-toolbar"><div className="work-search"><Search size={16}/><input aria-label="Search your tasks" placeholder="Find a task or villa…" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="Filter task priority" value={priority} onChange={e=>setPriority(e.target.value)}><option value="">All priorities</option>{['High','Medium','Low'].map(p=><option key={p}>{p}</option>)}</select></div>
    {dueDate && <div className="work-date-filter"><p className="work-context">Assignments scheduled for {dateLabel(dueDate)}</p><button type="button" className="staff-btn-ghost" onClick={()=>setDueDate('')}>Show all assignments</button></div>}
    <div className="work-card-grid">{visible.map(task=><TaskCard key={task.id} task={task} openTask={openTask}/>)}</div>
    {!visible.length && <div className="work-empty"><CheckCircle2 size={32}/><strong>{search || priority ? 'No matching tasks' : dueDate ? 'No assignments for this date' : initialView === 'My work' ? 'You’re all caught up' : 'Nothing here yet'}</strong><p>{dueDate ? 'Show all assignments to see work scheduled on other dates.' : search || priority ? 'Try a different search or priority.' : 'New assignments and updates will appear automatically.'}</p></div>}
  </div>;
}
export function StaffOverview({ tasks, name, shift, openTask, viewTasks, viewCalendar, viewHistory }) {
  const active = orderTasks(tasks.filter(isWorking));
  const today = tasks.filter(t=>t.dueDate === dateKey() && t.status !== 'Cancelled');
  const focus = active[0];
  return <div className="work-overview">
    <section className="preparation-flow-banner"><div><small>BOOKING PREPARATION</small><h2>My booking assignments</h2></div><ol><li>Receive assignment</li><li>Clean &amp; prepare</li><li>Submit checklist</li><li>Admin approves</li></ol></section>
    <section className="work-metrics">{[[Circle,'To do',tasks.filter(t=>t.status==='Pending' && !isLate(t)).length],[Clock3,'In progress',tasks.filter(t=>t.status==='In Progress' && !isLate(t)).length],[CheckCircle2,'In review',tasks.filter(t=>t.status==='Pending Review').length],[CalendarDays,'Due today',today.filter(task=>isWorking(task) && !isLate(task)).length]].map(([Icon,label,count])=><button key={label} onClick={()=>viewTasks(label==='In review'?'In review':'My work',label==='To do'?'To do':label==='In progress'?'In progress':label==='Due today'?'Due today':'All work')}><span><Icon size={18}/>{label}</span><strong>{count}</strong><ArrowUpRight size={16}/></button>)}</section>
    {tasks.some(task=>isLate(task)) && <section className="preparation-overdue-notice"><div><strong>{tasks.filter(task=>isLate(task)).length} assignment(s) past the preparation deadline</strong><p>Ask your administrator to review the schedule or reassign the work before guest arrival.</p></div><button className="staff-btn-ghost" onClick={viewHistory}>Review overdue work</button></section>}
    <div className="work-overview-columns"><section className="work-focus"><div className="work-section-title"><div><small>YOUR NEXT STEP</small><h3>{name?.split(' ')[0] || 'Staff'}, here’s your work plan.</h3></div><span className="work-shift">{shift || 'Shift not assigned'}</span></div>{focus ? <><TaskCard task={focus} openTask={openTask}/></> : <div className="work-empty"><CheckCircle2 size={32}/><strong>No open work</strong><p>New booking assignments appear automatically.</p></div>}<button className="work-text-button" onClick={()=>viewTasks('My work','All work')}>See all my work <ChevronRight size={15}/></button></section>
    <section className="work-today"><div className="work-section-title"><div><small>{dateLabel(dateKey(), {weekday:'long'})}</small><h3>Today’s schedule</h3></div><button className="work-icon-button" aria-label="Open calendar" onClick={viewCalendar}><ArrowUpRight size={18}/></button></div>{orderTasks(today).slice(0,5).map(task=><button className="work-agenda-row" key={task.id} onClick={()=>openTask(task.id)}><time>{timeLabel(task.dueTime)}</time><span><strong>{task.title}</strong><small>{task.villaName} · {task.status === 'Pending' ? 'To do' : task.status}</small></span><ChevronRight size={16}/></button>)}{!today.length && <p className="work-context">No preparation scheduled today.</p>}<button className="work-text-button" onClick={viewCalendar}>View calendar <ChevronRight size={15}/></button></section></div>
  </div>;
}
