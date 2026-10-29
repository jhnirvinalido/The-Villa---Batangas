import { AlertMessage, LoadingScreen } from "./SystemFeedback";
import useLiveUpdates from './useLiveUpdates';
import {snapshotRows} from './dashboardSnapshot.mjs';
import {useCallback,useEffect,useState} from 'react';
import {MessageSquare,Star} from 'lucide-react';
import './AdminGuestFeedback.css';
import FeedbackAnalysisPanel from './FeedbackAnalysisPanel';

export default function AdminGuestFeedback({apiRequest}) {
  const [reviews,setReviews]=useState([]);
  const [companions,setCompanions]=useState([]);
  const [companionError,setCompanionError]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [refreshKey,setRefreshKey]=useState(0);
  const load=useCallback(async()=>{
    const results=await Promise.allSettled([
      apiRequest('/admin/guest-feedback'),apiRequest('/admin/guest-feedback/historical'),apiRequest('/admin/guest-feedback/companions'),
    ]);
    const errors=[];
    const companionResult=results.pop();
    setCompanions(current=>snapshotRows(current, companionResult.status==='fulfilled' ? companionResult.value.data : null));
    setCompanionError(companionResult.status==='rejected' ? companionResult.reason?.message || 'Companion feedback could not be loaded.' : '');
    setReviews(current=>{
      const next=[];
      results.forEach((result,index)=>{
        if(result.status==='fulfilled' && Array.isArray(result.value.data)) next.push(...result.value.data);
        else next.push(...current.filter(row=>(row.source==='historical_dataset')===(index===1)));
      });
      return snapshotRows(current,[...new Map(next.map(row=>[row.id,row])).values()]);
    });
    for(const result of results) {
      if(result.status==='rejected') errors.push(result.reason?.message || 'Some feedback could not be loaded.');
    }
    setError(errors.join(' '));setLoading(false);setRefreshKey(value=>value+1);
  },[apiRequest]);
  useEffect(()=>{
    const timer=setTimeout(load,0);
    return()=>clearTimeout(timer);
  },[load]);
  useLiveUpdates({domains:['feedback'],onChange:load});
  const average=reviews.length?(reviews.reduce((sum,row)=>sum+Number(row.overall_rating),0)/reviews.length).toFixed(1):'—';
  return <div className="guest-feedback-admin">{loading && <LoadingScreen message="Loading guest feedback…"/>}
    <div className="guest-feedback-toolbar"><div><h2>Guest feedback</h2><p>Guest experiences and recommended improvements.</p></div></div>
    {error && <AlertMessage message={error}/>}

    <div className="feedback-workspace">
    <FeedbackAnalysisPanel apiRequest={apiRequest} refreshKey={refreshKey}/>
    <section className="feedback-reviews-panel" aria-label="Guest reviews">
    <div className="guest-feedback-toolbar"><h3>Reviews</h3><div className="feedback-review-totals"><span className="feedback-muted">{reviews.length} review{reviews.length===1?'':'s'}</span><span className="feedback-inline-rating" aria-label={`Average rating ${average} out of 5`}><Star size={16}/><strong>{average}</strong><span>/ 5</span></span></div></div>
    <div className="feedback-reviews-scroll" role="region" aria-label="Scrollable guest reviews" tabIndex={0}><div className="guest-feedback-review-grid">{reviews.map(row=><article key={row.id} className="guest-feedback-review">
      <header><div><h3>{row.hide_identity?'Anonymous guest':row.guest_name || 'Guest'}</h3>{row.villa_name && <span>{row.villa_name}</span>}</div><strong><Star size={15}/>{row.overall_rating}/5</strong></header>
      <p className="guest-feedback-comment">{row.comments}</p>
      <footer><time>{row.review_date || row.review_date_label || (row.created_at?new Date(row.created_at).toLocaleDateString('en-PH',{month:'short',day:'numeric',year:'numeric'}):'')}</time><span className={`feedback-sentiment ${row.sentiment_label || ''}`}>{row.sentiment_label || (row.analysis_status==='insufficient_vocabulary'?'Unclassified':'Analyzing…')}</span></footer>
    </article>)}</div>
    {!loading && !error && !reviews.length && <div className="guest-feedback-empty"><MessageSquare size={32}/><h3>No feedback yet</h3><p>Guest reviews will appear here when submitted.</p></div>}
    </div></section></div>
    <section className="feedback-reviews-panel" aria-label="Internal companion feedback" style={{marginTop:24}}>
      <div className="guest-feedback-toolbar"><div><h3>Companion feedback</h3><p>Internal responses from invited guests. Excluded from public ratings and AI analysis.</p></div><span>{companions.length} response{companions.length===1?'':'s'}{companions.length===500?' (latest 500)':''}</span></div>
      {companionError && <AlertMessage message={companionError}/>}
      <div className="guest-feedback-review-grid">{companions.map(row=><article key={row.id} className="guest-feedback-review">
        <header><h3>Anonymous companion</h3><strong><Star size={15}/>{row.overall_rating}/5</strong></header>
        <p className="guest-feedback-comment">{row.comments}</p>
        <footer><time>{new Date(row.created_at).toLocaleDateString('en-PH')}</time><span>Internal feedback</span></footer>
      </article>)}</div>
      {!loading && !companionError && !companions.length && <p className="feedback-muted">No companion feedback yet.</p>}
    </section>
  </div>;
}
