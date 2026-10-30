import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle, Wrench } from 'lucide-react';
import { arrivalInput, arrivalTimestamp } from './maintenanceModel.mjs';
import { formatUserFacingMessage, getApiErrorMessage, getUserFacingError } from './errorMessages.mjs';
import './MaintenanceResponse.css';

const API_URL = ((typeof window !== 'undefined' && window.__THE_VILLA_API_BASE__) || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const displayTime = value => value ? new Date(value).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' }) : '';

export default function MaintenanceResponse() {
  const [credentials] = useState(() => ({
    id: new URLSearchParams(window.location.search).get('request') || '',
    token: new URLSearchParams(window.location.hash.slice(1)).get('token') || '',
  }));
  const [request, setRequest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [decision, setDecision] = useState('Accepted');
  const [arrival, setArrival] = useState('');
  const [notes, setNotes] = useState('');
  const [success, setSuccess] = useState(false);

  const apiRequest = useCallback(async (options = {}) => {
    if (!credentials.id || !/^[a-f0-9]{64}$/i.test(credentials.token)) throw new Error('Open the complete response link sent by the administrator.');
    const response = await fetch(`${API_URL}/maintenance-response/${encodeURIComponent(credentials.id)}`, {
      ...options, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer',
      headers: { Accept: 'application/json', 'X-Maintenance-Token': credentials.token, ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
    return payload;
  }, [credentials]);

  useEffect(() => {
    let active = true;
    const referrer = document.createElement('meta'); referrer.name = 'referrer'; referrer.content = 'no-referrer';
    const robots = document.createElement('meta'); robots.name = 'robots'; robots.content = 'noindex, nofollow';
    document.head.append(referrer, robots);
    apiRequest().then(result => { if (active) setRequest(result.data); })
      .catch(failure => { if (active) setError(getUserFacingError(failure, 'The request could not be loaded. Contact the administrator.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; referrer.remove(); robots.remove(); };
  }, [apiRequest]);

  async function submit(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await apiRequest({ method: 'POST', body: JSON.stringify({ decision, expectedArrival: decision === 'Unavailable' ? null : arrivalTimestamp(arrival), notes }) });
      setRequest(previous => ({ ...previous, ...result.data, canRespond: false })); setSuccess(true);
    } catch (failure) { setError(getUserFacingError(failure, 'Your reply could not be saved. Contact the administrator.')); }
    finally { setBusy(false); }
  }

  return <main className="maintenance-response-page"><div className="maintenance-response-card">
    <header><span className="maintenance-response-brand">THE VILLA</span><div className="maintenance-response-icon"><Wrench size={25}/></div><p>On-call maintenance</p><h1>{success ? 'Response recorded' : 'Can you attend this repair?'}</h1><span>Confirm your availability and arrival time for the administrator.</span></header>
    {loading && <p className="maintenance-response-loading" role="status"><LoaderCircle size={20}/>Loading request…</p>}
    {error && <p className="maintenance-response-error" role="alert"><AlertCircle size={20}/>{formatUserFacingMessage(error)}</p>}
    {request && <><section className="maintenance-response-issue" aria-label="Repair request"><small>{request.reference} · {request.priority} priority</small><h2>{request.title}</h2><p>{request.location}{request.equipment ? ` · ${request.equipment}` : ''}</p><p className="maintenance-response-description">{request.description}</p></section>
      {request.canRespond ? <form onSubmit={submit}><fieldset disabled={busy}><legend>Your availability</legend>
        {[['Accepted', 'I can attend', 'Confirm your estimated arrival.'], ['Unavailable', 'I am unavailable', 'The administrator will arrange another contact.'], ['Proposed time', 'Suggest another time', 'The administrator will review your proposed arrival.']].map(([value, label, help]) => <label className={`maintenance-response-choice ${decision === value ? 'selected' : ''}`} key={value}><input type="radio" name="decision" value={value} checked={decision === value} onChange={() => setDecision(value)}/><span><strong>{label}</strong><small>{help}</small></span></label>)}
        {decision !== 'Unavailable' && <label className="maintenance-response-field"><span><Clock3 size={16}/>Expected arrival (Philippine time)</span><input required type="datetime-local" min={arrivalInput(new Date().toISOString())} value={arrival} onChange={event => setArrival(event.target.value)}/><small>Choose a future arrival time that works for you.</small></label>}
        <label className="maintenance-response-field">{decision === 'Accepted' ? 'Notes (optional)' : 'Brief explanation'}<textarea required={decision !== 'Accepted'} minLength={decision !== 'Accepted' ? 3 : undefined} maxLength={2000} rows={3} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Tell the administrator anything they need to know."/></label>
        <button className="maintenance-response-submit" type="submit">{busy ? <><LoaderCircle size={18}/>Saving response…</> : 'Send my response'}</button>
      </fieldset></form> : <div className="maintenance-response-confirmation" role="status"><CheckCircle2 size={24}/><div><strong>{request.state === 'Accepted' ? 'Availability confirmed' : request.state === 'Proposed time' ? 'Proposed time sent for admin review' : request.state === 'Unavailable' ? 'Unavailable response recorded' : 'This request already has a response'}</strong><p>{request.expectedArrival ? `Arrival: ${displayTime(request.expectedArrival)} (Philippine time).` : 'Contact the administrator if your availability changes.'}</p></div></div>}
    </>}
    <footer>This private link is for the assigned technician. For urgent changes, call or message the administrator.</footer>
  </div></main>;
}
