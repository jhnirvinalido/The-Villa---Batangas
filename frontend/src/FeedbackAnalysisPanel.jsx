import {useCallback,useEffect,useState} from 'react';
import {CheckCircle2,Sparkles} from 'lucide-react';

export default function FeedbackAnalysisPanel({apiRequest,refreshKey}) {
  const [report,setReport]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const load=useCallback(async(signal)=>{
    try {
      const next=await apiRequest('/admin/guest-feedback/analysis',{signal});
      if(!signal?.aborted){setReport(next);setError('');}
    } catch(failure) {
      if(!signal?.aborted)setError(failure.message || 'Recommendations could not be loaded.');
    }
  },[apiRequest]);
  useEffect(()=>{
    const controller=new AbortController();const timer=setTimeout(()=>load(controller.signal),0);
    return()=>{clearTimeout(timer);controller.abort();};
  },[load,refreshKey]);
  async function approve(id) {
    setBusy(true);setError('');
    try {await apiRequest(`/admin/guest-feedback/recommendations/${id}/approve`,{method:'POST'});await load();}
    catch(failure){setError(failure.message || 'The recommendations could not be approved.');}
    finally{setBusy(false);}
  }
  const draft=report?.recommendation_reports?.[0];
  const complaints=report?.summary?.top_complaints || [];
  let status='Analyzing feedback automatically…';
  if(report) {
    if(!report.gemini_configured)status='Recommendations are waiting for Gemini configuration.';
    else if(!report.recommendation_storage_ready || report.automation?.status==='unavailable')status='Automatic recommendations need the latest database migration.';
    else if(!complaints.length)status='No recurring issues detected in the current analysis.';
    else if(report.automation?.status==='failed')status='Recommendations could not be generated. Please check the service configuration.';
    else if(report.automation?.status==='retry')status='The recommendation service is temporarily unavailable. Retrying automatically.';
    else status='Preparing recommendations automatically. This can take a minute.';
  }
  return <section className="feedback-recommendations-section" aria-label="Recommended improvements">
    <div className="guest-feedback-toolbar"><div><h3><Sparkles size={18}/>Recommended improvements</h3><p>Updated automatically as feedback changes. Review suggestions before approving.</p></div>{draft && <span className={`feedback-report-status ${draft.status}`}>{draft.status==='approved'?'Approved':'For review'}</span>}</div>
    <div className="feedback-recommendations-scroll" role="region" aria-label="Scrollable recommendations" tabIndex={0}>
    {error && <p className="guest-feedback-error" role="alert">{error}</p>}
    {!draft && <p className="feedback-auto-status" role="status">{status}</p>}
    {draft && <>
      <div className="feedback-action-list">{draft.recommendation.actions.map((action,index)=><article className="feedback-action" key={action.category}><span className="feedback-action-number">{index+1}</span><div><h4>{action.category}</h4><p>{action.action}</p><details><summary>{action.negative_review_count} review{action.negative_review_count===1?'':'s'} · View supporting feedback</summary><p>{action.rationale}</p>{(action.evidence || []).map((text,i)=><blockquote key={i}>{text}</blockquote>)}</details></div></article>)}</div>

    </> }
    </div>
    {draft && <div className="feedback-approval-row"><small>AI suggestions · administrator review required</small>{draft.status==='draft'?<button className="admin-btn-primary" disabled={busy} onClick={()=>approve(draft.id)}>{busy?'Approving…':'Approve recommendations'}</button>:<span><CheckCircle2 size={15}/>Approved {draft.approved_at?new Date(draft.approved_at).toLocaleDateString('en-PH'):''}</span>}</div>
    }
  </section>;
}
