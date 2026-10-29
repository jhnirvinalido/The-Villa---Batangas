import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, X } from 'lucide-react';
import { dateKey, dateLabel, isLate, orderTasks, timeLabel } from './taskFlow.mjs';

export default function StaffSchedule({tasks,shift,openTask,showOwner=false,onViewTodos}) {
  const [selected,setSelected]=useState(dateKey());
  const [mode,setMode]=useState('Month');
  const [showCompleted,setShowCompleted]=useState(false);
  const [dayModalOpen,setDayModalOpen]=useState(false);
  const dialog=useRef(null);
  const date = new Date(`${selected}T12:00:00`);
  const key = d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const first = mode==='Month'?new Date(date.getFullYear(),date.getMonth(),1,12):new Date(date);
  first.setDate(first.getDate()-(first.getDay()+6)%7);
  const days=Array.from({length:mode==='Month'?42:7},(_,i)=>{const d=new Date(first);d.setDate(d.getDate()+i);return d;});
  const visible=tasks.filter(t=>t.status!=='Cancelled' && (showCompleted || t.status!=='Completed'));
  const dayTasks=orderTasks(visible.filter(t=>t.dueDate===selected));
  const selectedDateTasks=tasks.filter(task=>task.dueDate===selected && task.status!=='Cancelled');
  const selectedDateUnavailable=selectedDateTasks.some(task=>isLate(task));
  const unavailableReason=[
    selectedDateTasks.some(task=>isLate(task)) && 'overdue assignments',
  ].filter(Boolean).join(' and ');
  const dayOverview={
    todo:selectedDateTasks.filter(task=>task.status==='Pending').length,
    inProgress:selectedDateTasks.filter(task=>task.status==='In Progress').length,
    overdue:selectedDateTasks.filter(task=>isLate(task)).length,
    review:selectedDateTasks.filter(task=>task.status==='Pending Review').length,
    completed:selectedDateTasks.filter(task=>task.status==='Completed').length,
  };
  const daySummary=[
    `${selectedDateTasks.length} assignment${selectedDateTasks.length===1?'':'s'} scheduled`,
    dayOverview.todo && `${dayOverview.todo} to do`,
    dayOverview.inProgress && `${dayOverview.inProgress} in progress`,
    dayOverview.overdue && `${dayOverview.overdue} overdue`,
    dayOverview.review && `${dayOverview.review} for review`,
    dayOverview.completed && `${dayOverview.completed} completed`,
  ].filter(Boolean).join(' · ');

  useEffect(()=>{
    if(!dayModalOpen) return undefined;
    const previous=document.activeElement;
    const overflow=document.body.style.overflow;
    document.body.style.overflow='hidden';
    dialog.current?.focus();
    const dismissOnEscape=event=>{
      if(event.key==='Escape') setDayModalOpen(false);
    };
    window.addEventListener('keydown',dismissOnEscape);
    return ()=>{
      document.body.style.overflow=overflow;
      window.removeEventListener('keydown',dismissOnEscape);
      previous?.focus();
    };
  },[dayModalOpen]);

  function move(direction) {
    const next=new Date(date);
    if(mode==='Month') {next.setDate(1);next.setMonth(next.getMonth()+direction);} else next.setDate(next.getDate()+direction*7);
    setSelected(key(next));
  }

  function viewTodos() {
    setDayModalOpen(false);
    onViewTodos?.(selected);
  }

  return <div className="work-calendar-layout"><section className="work-calendar">
    <div className="work-calendar-toolbar"><div><small>YOUR SCHEDULE</small><h3>{date.toLocaleDateString('en-PH',{month:'long',year:'numeric'})}</h3></div><div className="work-calendar-navigation"><button className="work-icon-button" aria-label={`Previous ${mode.toLowerCase()}`} onClick={()=>move(-1)}><ChevronLeft size={17}/></button><button className="staff-btn-ghost" onClick={()=>setSelected(dateKey())}>Today</button><button className="work-icon-button" aria-label={`Next ${mode.toLowerCase()}`} onClick={()=>move(1)}><ChevronRight size={17}/></button></div><div className="work-segments">{['Month','Week'].map(value=><button key={value} aria-pressed={mode===value} onClick={()=>setMode(value)}>{value}</button>)}</div></div>
    <div className="work-calendar-weekdays">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=><span key={day}>{day}</span>)}</div>
    <div className={`work-calendar-days ${mode.toLowerCase()}`}>{days.map(day=>{const value=key(day);const events=visible.filter(task=>task.dueDate===value).sort((a,b)=>(a.dueTime || '23:59').localeCompare(b.dueTime || '23:59'));const allDayTasks=tasks.filter(task=>task.dueDate===value && task.status!=='Cancelled');const unavailable=allDayTasks.some(task=>isLate(task));return <button key={value} aria-label={`${dateLabel(value)}: ${events.length} tasks${unavailable?', Needs attention':''}`} aria-pressed={selected===value} className={`${day.getMonth()!==date.getMonth()?'muted':''} ${selected===value?'selected':''} ${value===dateKey()?'today':''} ${unavailable?'unavailable':''}`} onClick={()=>{setSelected(value);setDayModalOpen(true);}}><span className="work-day-number">{day.getDate()}</span>{unavailable && <span className="work-day-unavailable">Needs attention</span>}<span className="work-day-events">{events.slice(0,mode==='Week'?5:2).map(task=><span key={task.id} className={`work-calendar-event ${isLate(task)?'late':task.status==='Completed'?'done':task.status==='In Progress'?'working':''}`}><i/>{task.title}</span>)}{events.length>(mode==='Week'?5:2) && <small>+{events.length-(mode==='Week'?5:2)} more</small>}</span><span className="work-day-mobile-count">{events.length || ''}</span></button>;})}</div>
    <div className="work-calendar-legend"><span><i/>To do</span><span className="working"><i/>In progress</span><span className="late"><i/>Overdue</span><label><input type="checkbox" checked={showCompleted} onChange={e=>setShowCompleted(e.target.checked)}/>Show approved</label></div>
  </section>
  {dayModalOpen && <div className="work-day-modal-backdrop" onClick={()=>setDayModalOpen(false)}><section ref={dialog} tabIndex={-1} className="work-day-modal" role="dialog" aria-modal="true" aria-labelledby="work-day-modal-title" onClick={event=>event.stopPropagation()}>
    <header className="work-day-modal-header"><div><small>{shift || 'Shift not assigned'}</small><h2 id="work-day-modal-title">{dateLabel(selected,{weekday:'long',year:'numeric'})}</h2><p>{daySummary || 'No assignments scheduled'}</p></div><button type="button" className="work-icon-button" aria-label="Close date details" onClick={()=>setDayModalOpen(false)}><X size={18}/></button></header>
    {selectedDateUnavailable && <div className="work-day-unavailable-notice"><strong>Needs attention</strong><span>This date has {unavailableReason}. Ask your administrator to review any missed preparation deadlines.</span></div>}
    <div className="work-day-modal-list">{dayTasks.map(task=>{
      const status=isLate(task)?'Overdue':task.status==='Pending'?'To do':task.status;
      const details=<><Clock3 size={16}/><span className="work-day-task-content"><span className="work-day-task-heading"><time>{timeLabel(task.dueTime)}</time><strong>{task.title}</strong><span className={`work-day-task-status status-${status.toLowerCase().replaceAll(' ','-')}`}>{status}</span></span><p>{task.description}</p><small>{task.villaName}{task.bookingCode ? ` · ${task.bookingCode}` : ''}{showOwner && task.assignedTo ? ` · ${task.assignedTo}` : ''}</small></span>{showOwner && <ChevronRight size={16}/>}</>;
      return <button className="work-agenda-row" key={task.id} onClick={()=>{setDayModalOpen(false);openTask(task.id);}}>{details}</button>;
    })}{!dayTasks.length && <div className="work-empty"><CalendarDays size={28}/><strong>A clear day</strong><p>No assignments scheduled for this date.</p></div>}</div>
    <footer className="work-day-modal-footer">{onViewTodos && <button type="button" className="staff-btn-primary" onClick={viewTodos}>Open tasks for this date</button>}<button type="button" className="staff-btn-ghost" onClick={()=>setDayModalOpen(false)}>Close</button></footer>
  </section></div>}
  </div>;
}
