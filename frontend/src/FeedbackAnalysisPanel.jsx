import {useCallback,useEffect,useState} from 'react';
import {CheckCircle2,Sparkles} from 'lucide-react';
import { formatUserFacingMessage, getUserFacingError } from './errorMessages.mjs';

export default function FeedbackAnalysisPanel({apiRequest,refreshKey}) {
  const [report,setReport]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const load=useCallback(async(signal)=>{
    try {
      const next=await apiRequest('/admin/guest-feedback/analysis',{signal});
      if(!signal?.aborted){setReport(next);setError('');}
    } catch(failure) {
      if(!signal?.aborted)setError(getUserFacingError(failure, 'Recommendations could not be loaded.'));
    } finally {
      if(!signal?.aborted)setLoading(false);
    }
  },[apiRequest]);
  useEffect(()=>{
    const controller=new AbortController();const timer=setTimeout(()=>load(controller.signal),0);
    return()=>{clearTimeout(timer);controller.abort();};
  },[load,refreshKey]);
  useEffect(()=>{
    const status=report?.recommendation_job?.status;
    if(!['queued','processing','retry'].includes(status))return undefined;
    const controller=new AbortController();
    const timer=setInterval(()=>load(controller.signal),4000);
    return()=>{clearInterval(timer);controller.abort();};
  },[load,report?.recommendation_job?.status]);
  async function approve(id) {
    setBusy(true);setError('');
    try {await apiRequest(`/admin/guest-feedback/recommendations/${id}/approve`,{method:'POST'});await load();}
    catch(failure){setError(getUserFacingError(failure, 'The recommendations could not be approved.'));}
    finally{setBusy(false);}
  }
  async function generateRecommendations() {
    setBusy(true);setError('');
    try {
      await apiRequest('/admin/guest-feedback/recommendations',{
        method:'POST',
        body:JSON.stringify({source:'all',villa:'',rating:null,start:null,end:null}),
      });
      await load();
    } catch(failure) {
      setError(getUserFacingError(failure, 'Recommendations could not be generated.'));
    } finally {
      setBusy(false);
    }
  }
  const draft=report?.recommendation_reports?.[0];
  const job=report?.recommendation_job;
  const jobActive=['queued','processing','retry'].includes(job?.status);
  const complaints=report?.summary?.top_complaints || [];
  return <section className="feedback-recommendations-section" aria-label="Recommended improvements">
    <div className="guest-feedback-toolbar"><div><h3><Sparkles size={18}/>Recommended improvements</h3><p>Generate suggestions when you choose. Review them before approving.</p></div>{draft && <span className={`feedback-report-status ${draft.status}`}>{draft.status==='approved'?'Approved':'For review'}</span>}</div>
    <div className="feedback-recommendations-scroll" role="region" aria-label="Scrollable recommendations" tabIndex={0}>
    {error && <p className="guest-feedback-error" role="alert">{formatUserFacingMessage(error)}</p>}
    {!draft && job?.status==='queued' && <p className="feedback-auto-status" role="status">Recommendation request queued. Waiting for the worker…</p>}
    {!draft && job?.status==='processing' && <p className="feedback-auto-status" role="status">Generating a draft. You can stay on this page while it finishes…</p>}
    {!draft && job?.status==='retry' && <p className="feedback-auto-status" role="status">The provider had a temporary problem. Retrying (attempt {job.attempts} of {job.max_attempts})…</p>}
    {!draft && job?.status==='failed' && <p className="guest-feedback-error" role="alert">
      Recommendation generation stopped after {job.attempts} attempt{job.attempts===1?'':'s'}.
      {job.last_error?` ${job.last_error}`:''} You can request a new attempt.
    </p>}
    {!draft && !jobActive && <p className="feedback-auto-status" role="status">
      {loading?'Loading feedback analysis…':
        !report?'Feedback analysis is unavailable right now.':
        !report?.gemini_configured?'Configure Gemini before generating recommendations.':
        !report?.recommendation_storage_ready?'Recommendation storage is unavailable. Contact the system administrator to check the database setup.':
        !complaints.length?'No negative categorized feedback is available yet.':
        'Recommendations have not been generated for the current feedback. Select Generate recommendations when ready.'}
    </p>}
    {draft && <>
      <div className="feedback-action-list">{draft.recommendation.actions.map((action,index)=><article className="feedback-action" key={action.category}><span className="feedback-action-number">{index+1}</span><div><h4>{action.category}</h4><p>{action.action}</p><details><summary>{action.negative_review_count} review{action.negative_review_count===1?'':'s'} · View supporting feedback</summary><p>{action.rationale}</p>{(action.evidence || []).map((text,i)=><blockquote key={i}>{text}</blockquote>)}</details></div></article>)}</div>

    </> }
    </div>
    {draft && <div className="feedback-approval-row"><small>Draft suggestions · administrator review required</small>{draft.status==='draft'?<button className="admin-btn-primary" disabled={busy} onClick={()=>approve(draft.id)}>{busy?'Approving…':'Approve recommendations'}</button>:<span><CheckCircle2 size={15}/>Approved {draft.approved_at?new Date(draft.approved_at).toLocaleDateString('en-PH'):''}</span>}</div>}
    {!draft && !jobActive && !loading && report?.gemini_configured && report?.recommendation_storage_ready && complaints.length>0 &&
      <div className="feedback-approval-row"><small>Generation runs only when you request it.</small><button className="admin-btn-primary" disabled={busy} onClick={generateRecommendations}>{busy?'Queueing…':job?.status==='failed'?'Retry recommendations':'Generate recommendations'}</button></div>}
  </section>;
}
