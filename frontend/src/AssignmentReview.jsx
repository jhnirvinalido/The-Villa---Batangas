import { useState } from 'react';
import { CheckCircle2, RotateCcw } from 'lucide-react';
import { formatUserFacingMessage, getUserFacingError } from './errorMessages.mjs';

export default function AssignmentReview({ task, update }) {
  const [feedback,setFeedback]=useState('');
  const [steps,setSteps]=useState([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function save(approve) {
    if(busy)return;
    setBusy(true);setError('');
    try {
      await update(task.id,approve?{status:'Completed',progress:100}:{status:'In Progress',reviewNote:feedback.trim(),checklist:task.checklist.map(item=>({...item,done:steps.includes(item.id)?false:item.done})),progress:Math.round(task.checklist.filter(item=>item.done && !steps.includes(item.id)).length/task.checklist.length*100)},approve?'Task approved. Staff can see the completed assignment.':'Task returned with your feedback and the steps that need attention.');
    } catch(failure){setError(getUserFacingError(failure, 'Review could not be saved.'));}
    finally {setBusy(false);}
  }
  return <section className="assignment-review"><div><h3>Review this submission</h3><p>Approve the completed work, or identify the steps that need correction.</p></div><details><summary>Request corrections</summary><label>What needs to change?<textarea rows={3} maxLength={2000} value={feedback} onChange={e=>setFeedback(e.target.value)} disabled={busy} placeholder="Give staff specific feedback so they know what to fix."/></label><p>Select the steps that need another check. Other completed steps stay checked.</p>{(task.checklist || []).map(item=><label className="assignment-review-step" key={item.id}><input type="checkbox" checked={steps.includes(item.id)} disabled={busy} onChange={()=>setSteps(current=>current.includes(item.id)?current.filter(id=>id!==item.id):[...current,item.id])}/>{item.label || item.text}</label>)}<button className="admin-btn-secondary" disabled={busy || feedback.trim().length<5 || !steps.length} onClick={()=>save(false)}><RotateCcw size={15}/>Return selected steps</button></details>{error && <p role="alert" className="assignment-warning">{formatUserFacingMessage(error)}</p>}<button className="admin-btn-primary" disabled={busy} onClick={()=>save(true)}><CheckCircle2 size={15}/>{busy?'Saving review…':'Approve completed work'}</button></section>;
}
