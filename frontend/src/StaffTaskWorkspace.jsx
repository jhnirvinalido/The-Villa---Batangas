import { ConfirmAction } from "./SystemFeedback";
import BookingPreparationContext from "./BookingPreparationContext";
import { useEffect, useRef, useState } from 'react';
import { Check, CheckCircle2, Clock3, X } from 'lucide-react';
import { canEditTaskChecklist, canStartTask, checklistCount, dateLabel, isLate, readyForCompletion, readyForReview, returnedFeedback, setChecklistDone, setChecklistItemDone, timeLabel } from './taskFlow.mjs';
import { formatUserFacingMessage, getUserFacingError } from './errorMessages.mjs';

export default function StaffTaskWorkspace({ task, busy, update, close }) {
  const [notes,setNotes] = useState(task.notes || '');
  const [error,setError] = useState('');
  const [saved,setSaved] = useState(false);
  const [discardOpen,setDiscardOpen] = useState(false);
  const [now,setNow] = useState(Date.now);
  const [checklistDraft,setChecklistDraft] = useState(null);
  const [checklistSavingIds,setChecklistSavingIds] = useState(new Set());
  const dialog = useRef(null);
  const lock = useRef(false);
  const checklistDraftRef = useRef(null);
  const checklistSavingIdsRef = useRef(new Set());
  const checklistQueue = useRef(Promise.resolve());
  const checklist = checklistDraft ?? task.checklist ?? [];
  const taskWithChecklist = { ...task, checklist };
  const count = checklistCount(taskWithChecklist);
  const canStart = canStartTask(task,now);
  const requiresAdminReview = task.source === 'manual-maintenance-request' || !!task.maintenanceOnCall;
  const startMessage = task.maintenanceOnCall?.state === 'Awaiting response' ? 'Choose your availability from New request before this job can be scheduled.' : task.maintenanceOnCall?.state === 'Accepted' && !task.maintenanceOnCall.scheduleApproved ? 'Your availability was sent. Wait for the administrator to confirm the schedule before starting.' : task.maintenanceOnCall ? 'The administrator approved this schedule. You can start at the confirmed time.' : !task.dueDate || !task.dueTime
    ? 'A scheduled date and time are required before this task can be started.'
    : `Start this task on ${dateLabel(task.dueDate)}, before ${timeLabel(task.dueTime)}.`;
  const readonly = ['Completed','Cancelled'].includes(task.status) || (requiresAdminReview && task.status === 'Pending Review');
  const changed = notes !== (task.notes || '');
  const allChecklistDone = count.total > 0 && count.done === count.total;
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
    if (busy || lock.current || checklistSavingIdsRef.current.size) return;
    if (changed) { setDiscardOpen(true); return; }
    close();
  }
  function saveChecklist(nextChecklist, itemIds) {
    if (busy || !canEditTaskChecklist(task)) return;
    checklistDraftRef.current = nextChecklist;
    setChecklistDraft(nextChecklist);
    setError('');
    setSaved(false);

    const pending = new Set(checklistSavingIdsRef.current);
    itemIds.forEach(id => pending.add(id));
    checklistSavingIdsRef.current = pending;
    setChecklistSavingIds(pending);

    const status = task.status;
    const request = checklistQueue.current
      .catch(() => {})
      .then(() => update(task.id,{checklist:nextChecklist,status},undefined,undefined,{checklistOnly:true}));
    checklistQueue.current = request;
    request.then(() => setSaved(true))
      .catch(failure => setError(getUserFacingError(failure,'Could not save your checklist. Please retry.')))
      .finally(() => {
        const remaining = new Set(checklistSavingIdsRef.current);
        itemIds.forEach(id => remaining.delete(id));
        checklistSavingIdsRef.current = remaining;
        setChecklistSavingIds(remaining);
        if (!remaining.size) {
          checklistDraftRef.current = null;
          setChecklistDraft(null);
        }
      });
  }
  function toggleChecklistItem(itemId) {
    const current = checklistDraftRef.current ?? task.checklist ?? [];
    const item = current.find(step => step.id === itemId);
    if (!item || checklistSavingIdsRef.current.has(itemId)) return;
    saveChecklist(setChecklistItemDone(current,itemId,!item.done),[itemId]);
  }
  function toggleAllChecklist() {
    const current = checklistDraftRef.current ?? task.checklist ?? [];
    if (!current.length || checklistSavingIdsRef.current.size) return;
    const nextDone = !current.every(item => item.done);
    saveChecklist(setChecklistDone(current,nextDone),current.map(item=>item.id));
  }
  async function commit(patch) {
    if (busy || lock.current) return;
    lock.current=true;setError('');setSaved(false);
    try { await update(task.id,patch);setSaved(true); }
    catch (failure) { setError(getUserFacingError(failure, 'Could not save your update. Please retry.')); }
    finally {lock.current=false;}
  }
  return <><ConfirmAction open={discardOpen} cancel={()=>setDiscardOpen(false)} confirm={close} titleText="Discard unsaved notes?" message="Your handover notes have not been saved." confirmLabel="Discard notes" cancelLabel="Keep editing"/><div className="work-drawer-backdrop" onClick={dismiss}><section ref={dialog} tabIndex={-1} className="work-drawer" role="dialog" aria-modal="true" aria-labelledby="work-task-title" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();dismiss();}}}>
    <div className="work-drawer-top"><span>{task.department} / Assignment</span><button className="work-icon-button" aria-label="Close task" onClick={dismiss} disabled={busy}><X size={19}/></button></div>
    <div className="work-drawer-scroll"><div className="work-card-top"><span className={`work-status${task.status === 'Completed' ? ' done' : ''}`}>{task.status === 'Pending' ? 'Assigned' : task.status === 'Pending Review' ? requiresAdminReview ? 'Awaiting repair verification' : 'Ready to complete' : task.status === 'Completed' ? 'Completed' : task.status}</span><span className={`work-priority ${task.priority?.toLowerCase()}`}>{task.priority} priority</span></div><h2 id="work-task-title">{task.title}</h2><p className="work-context">{task.villaName || 'Villa operations'} · {task.bookingCode || 'General assignment'}</p>
      <BookingPreparationContext task={task}/><div className={`work-deadline ${isLate(task)?'late':''}`}><Clock3 size={17}/><span>{task.maintenanceOnCall ? task.maintenanceOnCall.expectedArrival ? `Expected arrival ${dateLabel(task.dueDate)} at ${timeLabel(task.dueTime)}` : `On-call: ${task.maintenanceOnCall.state}` : `Due ${dateLabel(task.dueDate)} at ${timeLabel(task.dueTime)}`}</span></div>
      {task.status!=='Cancelled' && <ol className="work-lifecycle">{(requiresAdminReview
        ? [task.maintenanceOnCall ? 'Start repair' : 'Start preparation','Complete checklist','Submit for verification','Admin verifies repair']
        : ['Start task','Complete checklist','Mark task complete']).map((label,index)=><li key={label} className={(index===0 && task.status!=='Pending') || (index===1 && count.total>0 && count.done===count.total) || (requiresAdminReview && index===2 && ['Pending Review','Completed'].includes(task.status)) || (requiresAdminReview && index===3 && task.status==='Completed') || (!requiresAdminReview && index===2 && task.status==='Completed') ? 'complete' : ''}><span>{index+1}</span>{label}</li>)}</ol>}
      {returnedFeedback(task) && <div className="work-feedback"><strong>Changes requested by your administrator</strong><p>{returnedFeedback(task)}</p></div>}
      {task.status === 'Pending Review' && <div className="work-outcome" role="status"><strong>{requiresAdminReview ? 'Repair submitted — waiting for administrator verification' : 'Checklist complete — mark the task complete when ready'}</strong><span>{requiresAdminReview ? 'You’re done for now. The administrator will verify the repair and update the villa’s operational status.' : 'This older assignment was submitted for review. You can now finish it directly.'}</span></div>}
      {task.status === 'Completed' && <div className="work-outcome complete" role="status"><strong>Task complete</strong><span>No further action is needed.</span></div>}
      <section className="work-instructions"><h3>What needs to be done</h3><p>{task.description}</p></section>
      <section className="work-checklist" aria-labelledby="work-checklist-title">
        <div className="work-checklist-heading">
          <div className="work-section-title"><h3 id="work-checklist-title">Steps to complete</h3><span aria-live="polite">{count.done} of {count.total}</span></div>
          {count.total > 0 && <label className="work-checklist-select-all">
            <input type="checkbox" checked={allChecklistDone}
              ref={element => { if (element) element.indeterminate = count.done > 0 && !allChecklistDone; }}
              disabled={!canEditTaskChecklist(task) || busy || checklistSavingIds.size > 0} onChange={toggleAllChecklist}/>
            <span>Mark all complete</span>
          </label>}
        </div>
        <progress aria-label="Checklist completion" value={count.done} max={count.total || 1}/>
        <div className="work-checklist-items">{checklist.map(item => <label key={item.id} className={item.done ? 'checked' : ''}>
          <input type="checkbox" checked={item.done} disabled={!canEditTaskChecklist(task) || busy || checklistSavingIds.has(item.id)} onChange={() => toggleChecklistItem(item.id)}/>
          <span>{item.label}</span>{checklistSavingIds.has(item.id) ? <span className="work-checklist-saving">Saving…</span> : item.done && <Check size={16}/>}
        </label>)}</div>
        {!count.total && <p className="work-context">This task has no completion steps. Ask your administrator to add them before submitting.</p>}
        {task.status === 'Pending' && <p className="work-context">{canStart ? 'Select Start task below before completing the checklist.' : startMessage}</p>}
      </section>
      <section className="work-handover"><label htmlFor="work-notes">Notes & handover</label><textarea id="work-notes" rows={4} maxLength={5000} value={notes} onChange={e=>{setNotes(e.target.value);setSaved(false);}} disabled={readonly || busy}/>{!readonly && <button className="staff-btn-ghost" disabled={!changed || busy} onClick={()=>commit({notes})}>Save notes</button>}</section>
      {task.statusHistory?.length>0 && <details className="work-activity"><summary>Activity history</summary>{[...task.statusHistory].reverse().map((entry,index)=><div key={entry.id || index}><strong>{entry.status}</strong><p>{entry.note}</p><small>{entry.timestamp ? new Date(entry.timestamp).toLocaleString('en-PH') : ''}</small></div>)}</details>}
    </div>
    <footer className="work-drawer-footer">{error && <p role="alert" className="work-error">{formatUserFacingMessage(error)}</p>}<div role="status" className="work-save-status">{busy?'Saving your update…':checklistSavingIds.size?'Saving checklist…':changed?'Unsaved handover notes':saved?'Your update is saved':readonly?task.status==='Cancelled'?'This assignment was cancelled. No further action is needed.':task.status==='Completed'?'Task complete. No further action is needed.':'Repair submitted for verification.':(requiresAdminReview ? readyForReview(taskWithChecklist) : readyForCompletion(taskWithChecklist))?(requiresAdminReview?'Repair checklist complete. Ready to submit for verification.':'Checklist complete. Mark the task complete when ready.'):`${count.total-count.done} steps remaining`}</div>{task.status==='Pending' && <button className="staff-btn-primary" disabled={busy || !canStart} onClick={()=>commit({status:'In Progress',...(changed?{notes}:{})})}><Clock3 size={16}/>{canStart?'Start task':task.maintenanceOnCall?.state === 'Accepted' && !task.maintenanceOnCall.scheduleApproved?'Awaiting admin approval':task.maintenanceOnCall?'Availability required':!task.dueDate || !task.dueTime?'Schedule required':'Not available yet'}</button>}{['In Progress','Pending Review'].includes(task.status) && !requiresAdminReview && <button className="staff-btn-primary" disabled={busy || checklistSavingIds.size>0 || !readyForCompletion(taskWithChecklist)} onClick={()=>commit({status:'Completed',checklist:checklist,...(changed?{notes}:{})})}><CheckCircle2 size={16}/>{changed?'Save notes & complete task':'Mark task complete'}</button>}{task.status==='In Progress' && requiresAdminReview && <button className="staff-btn-primary" disabled={busy || checklistSavingIds.size>0 || !readyForReview(taskWithChecklist)} onClick={()=>commit({status:'Pending Review',checklist:checklist,...(changed?{notes}:{})})}><CheckCircle2 size={16}/>{changed?'Save notes & submit for verification':'Submit repair for verification'}</button>}{readonly && <button className="staff-btn-ghost" onClick={dismiss}>Done</button>}</footer>
  </section></div></>;
}
