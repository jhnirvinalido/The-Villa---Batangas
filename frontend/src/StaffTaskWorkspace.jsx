import { ConfirmAction } from "./SystemFeedback";
import BookingPreparationContext from "./BookingPreparationContext";
import { useEffect, useRef, useState } from 'react';
import { Check, CheckCircle2, Clock3, X } from 'lucide-react';
import { canStartTask, checklistCount, dateLabel, isLate, readyForReview, returnedFeedback, timeLabel } from './taskFlow.mjs';

export default function StaffTaskWorkspace({ task, busy, update, close }) {
  const [notes,setNotes] = useState(task.notes || '');
  const [error,setError] = useState('');
  const [saved,setSaved] = useState(false);
  const [discardOpen,setDiscardOpen] = useState(false);
  const [now,setNow] = useState(Date.now);
  const dialog = useRef(null);
  const lock = useRef(false);
  const count = checklistCount(task);
  const canStart = canStartTask(task,now);
  const startMessage = task.maintenanceOnCall?.state === 'Awaiting response' ? 'Choose your availability from New request before this job can be scheduled.' : task.maintenanceOnCall?.state === 'Accepted' && !task.maintenanceOnCall.scheduleApproved ? 'Your availability was sent. Wait for the administrator to confirm the schedule before starting.' : task.maintenanceOnCall ? 'The administrator approved this schedule. You can start at the confirmed time.' : !task.dueDate || !task.dueTime
    ? 'A scheduled date and time are required before this task can be started.'
    : `Start this task on ${dateLabel(task.dueDate)}, before ${timeLabel(task.dueTime)}.`;
  const readonly = ['Completed','Pending Review','Cancelled'].includes(task.status);
  const changed = notes !== (task.notes || '');
  useEffect(()=>{
    const timer=window.setInterval(()=>setNow(Date.now()),30_000);
    return ()=>window.clearInterval(timer);
  },[]);
  useEffect(()=>{
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.focus();
    function trap(event) {
      if (event.key !== 'Tab') return;
      const items = [...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),[tabindex="0"]')];
      if (!items.length) { event.preventDefault(); return; }
      if(event.shiftKey && (document.activeElement===items[0] || document.activeElement===dialog.current)) {event.preventDefault();items.at(-1).focus();}
      else if(!event.shiftKey && (document.activeElement===items.at(-1) || document.activeElement===dialog.current)) {event.preventDefault();items[0].focus();}
    }
    const node = dialog.current;
    node?.addEventListener('keydown',trap);
    return ()=>{document.body.style.overflow=overflow;node?.removeEventListener('keydown',trap);previous?.focus();};
  },[]);
  function dismiss() {
    if (busy || lock.current) return;
    if (changed) { setDiscardOpen(true); return; }
    close();
  }
  async function commit(patch) {
    if (busy || lock.current) return;
    lock.current=true;setError('');setSaved(false);
    try { await update(task.id,patch);setSaved(true); }
    catch (failure) { setError(failure.message || 'Could not save your update. Please retry.'); }
    finally {lock.current=false;}
  }
  return <><ConfirmAction open={discardOpen} cancel={()=>setDiscardOpen(false)} confirm={close} titleText="Discard unsaved notes?" message="Your handover notes have not been saved." confirmLabel="Discard notes" cancelLabel="Keep editing"/><div className="work-drawer-backdrop" onClick={dismiss}><section ref={dialog} tabIndex={-1} className="work-drawer" role="dialog" aria-modal="true" aria-labelledby="work-task-title" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();dismiss();}}}>
    <div className="work-drawer-top"><span>{task.department} / Assignment</span><button className="work-icon-button" aria-label="Close task" onClick={dismiss} disabled={busy}><X size={19}/></button></div>
    <div className="work-drawer-scroll"><div className="work-card-top"><span className="work-status">{task.status === 'Pending' ? 'Assigned' : task.status === 'Pending Review' ? 'Awaiting approval' : task.status}</span><span className={`work-priority ${task.priority?.toLowerCase()}`}>{task.priority} priority</span></div><h2 id="work-task-title">{task.title}</h2><p className="work-context">{task.villaName || 'Villa operations'} · {task.bookingCode || 'General assignment'}</p>
      <BookingPreparationContext task={task}/><div className={`work-deadline ${isLate(task)?'late':''}`}><Clock3 size={17}/><span>{task.maintenanceOnCall ? task.maintenanceOnCall.expectedArrival ? `Expected arrival ${dateLabel(task.dueDate)} at ${timeLabel(task.dueTime)}` : `On-call: ${task.maintenanceOnCall.state}` : `Due ${dateLabel(task.dueDate)} at ${timeLabel(task.dueTime)}`}</span></div>
      {task.status!=='Cancelled' && <ol className="work-lifecycle">{[task.maintenanceOnCall ? 'Start repair' : 'Start preparation','Complete checklist','Submit for review','Admin approved'].map((label,index)=><li key={label} className={(index===0 && task.status!=='Pending') || (index===1 && count.total>0 && count.done===count.total) || (index===2 && ['Pending Review','Completed'].includes(task.status)) || (index===3 && task.status==='Completed') ? 'complete' : ''}><span>{index+1}</span>{label}</li>)}</ol>}
      {returnedFeedback(task) && <div className="work-feedback"><strong>Changes requested by your administrator</strong><p>{returnedFeedback(task)}</p></div>}
      <section className="work-instructions"><h3>What needs to be done</h3><p>{task.description}</p></section>
      <section className="work-checklist"><div className="work-section-title"><h3>Steps to complete</h3><span>{count.done} of {count.total}</span></div><progress value={count.done} max={count.total || 1}/>{(task.checklist || []).map(item=><label key={item.id} className={item.done?'checked':''}><input type="checkbox" checked={item.done} disabled={readonly || busy || (task.status==='Pending' && !canStart)} onChange={()=>{
        const checklist=task.checklist.map(i=>i.id===item.id?{...i,done:!i.done}:i);
        commit({checklist,status:task.status==='Pending'?'In Progress':task.status});
      }}/><span>{item.label}</span>{item.done && <Check size={16}/>}</label>)}{!count.total && <p className="work-context">This task has no completion steps. Ask your administrator to add them before submitting.</p>}{task.status==='Pending' && <p className="work-context">{canStart?'Start the task below, or check your first completed step to start automatically.':startMessage}</p>}</section>
      <section className="work-handover"><label htmlFor="work-notes">Notes & handover</label><textarea id="work-notes" rows={4} maxLength={5000} value={notes} onChange={e=>{setNotes(e.target.value);setSaved(false);}} disabled={readonly || busy}/>{!readonly && <button className="staff-btn-ghost" disabled={!changed || busy} onClick={()=>commit({notes})}>Save notes</button>}</section>
      {task.statusHistory?.length>0 && <details className="work-activity"><summary>Activity history</summary>{[...task.statusHistory].reverse().map((entry,index)=><div key={entry.id || index}><strong>{entry.status}</strong><p>{entry.note}</p><small>{entry.timestamp ? new Date(entry.timestamp).toLocaleString('en-PH') : ''}</small></div>)}</details>}
    </div>
    <footer className="work-drawer-footer">{error && <p role="alert" className="work-error">{error}</p>}<div role="status" className="work-save-status">{busy?'Saving your update…':changed?'Unsaved handover notes':saved?'Your update is saved':readonly?task.status==='Cancelled'?'This assignment was cancelled. No further action is needed.':task.status==='Completed'?'Approved by your administrator':'Submitted. Your administrator will review this task.':readyForReview(task)?'All steps complete. Ready for review.':`${count.total-count.done} steps remaining`}</div>{task.status==='Pending' && <button className="staff-btn-primary" disabled={busy || !canStart} onClick={()=>commit({status:'In Progress',...(changed?{notes}:{})})}><Clock3 size={16}/>{canStart?'Start task':task.maintenanceOnCall?.state === 'Accepted' && !task.maintenanceOnCall.scheduleApproved?'Awaiting admin approval':task.maintenanceOnCall?'Availability required':!task.dueDate || !task.dueTime?'Schedule required':'Not available yet'}</button>}{task.status==='In Progress' && <button className="staff-btn-primary" disabled={busy || !readyForReview(task)} onClick={()=>commit({status:'Pending Review',checklist:task.checklist,...(changed?{notes}:{})})}><CheckCircle2 size={16}/>{changed?'Save notes & submit for review':'Submit for review'}</button>}{readonly && <button className="staff-btn-ghost" onClick={dismiss}>Done</button>}</footer>
  </section></div></>;
}
