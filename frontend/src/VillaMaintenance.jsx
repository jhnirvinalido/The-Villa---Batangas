import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, CheckCircle2, Clock3, Mail, Wrench } from 'lucide-react';
import useLiveUpdates from './useLiveUpdates';
import { formatUserFacingMessage, getUserFacingError } from './errorMessages.mjs';
import { arrivalInput, arrivalTimestamp, conflictsWithBooking as arrivalConflictsWithBooking, isClosed, maintenanceForm, maintenancePayload } from './maintenanceModel.mjs';
import './VillaMaintenance.css';

const dateTime = value => value ? new Date(value).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' }) : 'Not confirmed';
const statusLabel = row => row.status === 'Pending Review' ? 'Work done · awaiting verification' : row.status === 'Pending' ? 'Waiting for technician' : row.status;

function RequestForm({ busy, submit }) {
  const [form, setForm] = useState({ title: '', description: '', kind: 'Repair', priority: 'Medium' });
  const set = (key, value) => setForm(previous => ({ ...previous, [key]: value }));
  return <form className="villa-maintenance-form" onSubmit={event => { event.preventDefault(); submit(form); }}>
    <h2>Request maintenance</h2><p>The selected technician receives an email to confirm availability and arrival time. New bookings pause only after the administrator confirms the technician’s availability.</p>
    <fieldset disabled={busy}><label>What needs attention?<input required autoFocus minLength={3} maxLength={180} value={form.title} onChange={event => set('title', event.target.value)} placeholder="e.g. Air conditioner not cooling"/></label>
    <label>Describe the issue<textarea required minLength={5} maxLength={5000} rows={4} value={form.description} onChange={event => set('description', event.target.value)}/></label>
    <div className="villa-maintenance-fields"><label>Work needed<select value={form.kind} onChange={event => set('kind', event.target.value)}><option>Repair</option><option>Inspection</option></select></label><label>Priority<select value={form.priority} onChange={event => set('priority', event.target.value)}><option>High</option><option>Medium</option><option>Low</option></select></label></div>
    <button className="villa-maintenance-primary" type="submit"><Wrench size={17}/>{busy ? 'Sending request…' : 'Send maintenance request'}</button></fieldset>
  </form>;
}

function AvailabilityForm({ row, busy, submit, admin, technicians, bookedPeriods = [] }) {
  const [decision, setDecision] = useState('Accepted');
  const [arrival, setArrival] = useState(arrivalInput(row.maintenance?.onCall?.expectedArrival) || arrivalInput(row.maintenance?.suggestedArrival));
  const [notes, setNotes] = useState('');
  const [technician, setTechnician] = useState(row.assignedStaffId || '');
  const conflictsWithBooking = ['Accepted', 'Proposed time'].includes(decision) && bookedPeriods.some(period =>
    period.villaId === row.maintenance?.villaId
    && arrivalConflictsWithBooking(arrival, period)
  );
  const villaBookings = bookedPeriods.filter(period => period.villaId === row.maintenance?.villaId);
  const suggestedArrival = row.maintenance?.suggestedArrival;
  const targetBooking = row.maintenance?.targetBooking;
  return <form className="villa-maintenance-form" onSubmit={event => { event.preventDefault(); submit({ decision, arrival, notes, technician }); }}>
    <fieldset disabled={busy}>
      {admin && <label>Technician<select value={technician} onChange={event => setTechnician(event.target.value)}>{!technicians.some(person => person.id === technician) && <option value={technician}>{row.assignedTo || 'Current technician'}</option>}{technicians.map(person => <option key={person.id} value={person.id}>{person.name || person.fullName}</option>)}</select></label>}
      {(!admin || technician === row.assignedStaffId) && <><label>{admin ? 'Response received' : 'Your availability'}<select value={decision} onChange={event => setDecision(event.target.value)}><option value="Accepted">{admin ? 'Available / approve proposed arrival' : 'I can attend'}</option><option value="Unavailable">Unavailable</option><option value="Proposed time">Suggest another arrival time</option>{admin && <option value="Request availability">Ask for availability again</option>}</select></label>
      {!admin && villaBookings.length > 0 && <div className="villa-maintenance-booking-guide"><strong>Guest booking times</strong><p>Choose an arrival outside each guest stay window.</p><ul>{villaBookings.map(period => <li key={`${period.checkInDate}-${period.checkOutDate}`}>{period.checkInDate}{period.checkOutDate !== period.checkInDate ? ` to ${period.checkOutDate}` : ''}{period.checkInTime ? ` · check-in ${period.checkInTime}` : ''}{period.checkOutTime ? ` · check-out ${period.checkOutTime}` : ' · checkout time not set'}</li>)}</ul></div>}
      {['Accepted', 'Proposed time'].includes(decision) && <>
        {!admin && suggestedArrival && decision === 'Accepted' && <p className="villa-maintenance-schedule-suggestion">System suggestion: <strong>{dateTime(suggestedArrival)}</strong>{targetBooking?.checkInDate && <> · before guest check-in on <strong>{targetBooking.checkInDate}{targetBooking.checkInTime ? ` at ${targetBooking.checkInTime}` : ''}</strong></>}</p>}
        <label>{!admin && decision === 'Accepted' && suggestedArrival ? 'Confirm suggested arrival' : 'Expected arrival (Philippine time)'}<input required type="datetime-local" readOnly={!admin && decision === 'Accepted' && !!suggestedArrival} value={arrival} onChange={event => setArrival(event.target.value)}/></label>
      </>}
      {conflictsWithBooking && <p className="villa-maintenance-booking-conflict" role="alert">The selected arrival falls within a guest booking. Choose a time outside the stay window.</p>}
      {decision !== 'Request availability' && <label>{decision === 'Accepted' ? 'Notes (optional)' : 'Explanation'}<textarea rows={2} required={decision !== 'Accepted'} minLength={decision !== 'Accepted' ? 3 : undefined} maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)}/></label>}</>}
      <button type="submit" className="villa-maintenance-primary" disabled={conflictsWithBooking}>{busy ? 'Saving…' : admin ? technician !== row.assignedStaffId ? 'Email this technician' : 'Record response' : decision === 'Accepted' ? 'Confirm availability' : 'Send response'}</button>
    </fieldset>
  </form>;
}

function WorkForm({ row, busy, submit }) {
  const [checklist, setChecklist] = useState(row.checklist || []);
  const [notes, setNotes] = useState(row.notes || '');
  const [waiting, setWaiting] = useState(!!row.maintenance?.waitingForParts);
  const [parts, setParts] = useState(row.maintenance?.partsNotes || '');
  const ready = checklist.length > 0 && checklist.every(item => item.done) && !waiting;
  return <form className="villa-maintenance-form" onSubmit={event => { event.preventDefault(); submit({ status: ready ? 'Pending Review' : 'In Progress', checklist, notes, waitingForParts: waiting, partsNotes: parts, expectedUpdatedAt: row.updatedAt }); }}>
    <h3>Your maintenance work</h3><fieldset disabled={busy}><div className="villa-maintenance-checklist">{checklist.map(item => <label key={item.id}><input type="checkbox" checked={!!item.done} onChange={() => setChecklist(previous => previous.map(step => step.id === item.id ? { ...step, done: !step.done } : step))}/>{item.label}</label>)}</div>
    <label>Work performed / findings<textarea required={ready} minLength={ready ? 5 : undefined} rows={4} maxLength={5000} value={notes} onChange={event => setNotes(event.target.value)}/></label>
    <label className="villa-maintenance-checkbox"><input type="checkbox" checked={waiting} onChange={event => setWaiting(event.target.checked)}/>Waiting for parts or supplies</label>
    {waiting && <label>Parts needed<textarea required rows={2} maxLength={2000} value={parts} onChange={event => setParts(event.target.value)}/></label>}
    <button className="villa-maintenance-primary" type="submit">{busy ? 'Saving…' : ready ? 'Submit completed work for verification' : 'Save progress'}</button></fieldset>
  </form>;
}

function VerificationForm({ busy, submit, cancel = false }) {
  const [note, setNote] = useState('');
  return <form className="villa-maintenance-form" onSubmit={event => { event.preventDefault(); submit({ status: cancel ? 'Cancelled' : 'Completed', verificationNote: note }); }}><fieldset disabled={busy}>
    <label>{cancel ? 'Reason for cancellation and confirmation the villa is safe' : 'Confirm the work is finished and the villa is ready for guests'}<textarea required minLength={5} maxLength={2000} rows={3} value={note} onChange={event => setNote(event.target.value)}/></label>
    <button className={cancel ? 'villa-maintenance-secondary' : 'villa-maintenance-primary'} type="submit">{busy ? 'Saving…' : cancel ? 'Cancel maintenance request' : 'Verify work & make villa available'}</button>
  </fieldset>{!cancel && <small>Bookings resume after all open maintenance work for this villa has been verified.</small>}</form>;
}

export default function VillaMaintenance({ villa, apiRequest, role = 'admin', staffDirectory = [], onBack, onChanged, modal = false, initialRequestId = '' }) {
  const admin = role === 'admin';
  const [records, setRecords] = useState([]);
  const [currentVilla, setCurrentVilla] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [notice, setNotice] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [selected, setSelected] = useState(initialRequestId);
  const [bookedPeriods, setBookedPeriods] = useState([]);
  const loadVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    try {
      const result = await apiRequest(admin ? '/admin/maintenance' : '/staff/villa-operations');
      if (version !== loadVersion.current) return;
      const work = admin ? result.data : result.data?.reports;
      setRecords((work || []).filter(row => row.maintenance?.villaId === villa.id));
      if (!admin) {
        setCurrentVilla(result.data?.villas?.find(item => item.id === villa.id) || null);
        setBookedPeriods(result.data?.bookedPeriods || []);
      }
      setLoadError('');
    } catch (failure) { if (version === loadVersion.current) setLoadError(getUserFacingError(failure, 'Maintenance could not be loaded.')); }
    finally { if (version === loadVersion.current) setLoading(false); }
  }, [apiRequest, admin, villa.id]);
  useEffect(() => { const timer = setTimeout(load, 0); return () => clearTimeout(timer); }, [load]);
  useLiveUpdates({ domains: ['tasks', 'catalog', 'staff'], onChange: load });
  const active = records.filter(row => !isClosed(row));
  const row = records.find(item => item.id === selected) || active[0] || records[0];
  const showRequest = !loading && !loadError && active.length === 0 && (requesting || !records.length);
  const displayVilla = currentVilla || villa;
  const underMaintenance = displayVilla.status === 'Under Maintenance'
    || active.some(item => item.maintenance?.blocksBooking);
  const technicians = staffDirectory.filter(person => person.department?.toLowerCase() === 'maintenance' && person.isActive && person.accountStatus === 'Active' && person.portalRole === 'staff');
  const onCall = row?.maintenance?.onCall || {};
  const technicianEmail = admin ? String(row?.technicianEmail || '').trim() : '';

  useEffect(() => {
    if (!modal) return undefined;
    const closeOnEscape = event => {
      if (event.key === 'Escape' && !busy) onBack?.();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [modal, busy, onBack]);

  async function mutate(path, method, body, message) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await apiRequest(path, { method, body: JSON.stringify(body) });
      setRequesting(false); setSelected(result.data?.id || row?.id || '');
      await load(); await onChanged?.(); setNotice(message);
    } catch (failure) { setError(getUserFacingError(failure, 'This update could not be saved.')); }
    finally { setBusy(false); }
  }
  function create(form) {
    const body = admin ? maintenancePayload({ ...maintenanceForm(null, '', { villaId: villa.id, blocksBooking: true }), ...form }) : { ...form, villaId: villa.id };
    return mutate(
      admin ? '/admin/maintenance' : '/staff/villa-operations',
      'POST',
      body,
      'Maintenance request sent. Bookings remain available until the administrator confirms the technician’s schedule.',
    );
  }
  function updateAdmin(changes, message) {
    return mutate(`/admin/maintenance/${row.id}`, 'PATCH', { ...maintenancePayload(maintenanceForm(row), row), ...changes }, message);
  }
  function respond({ decision, arrival, notes, technician }) {
    if (admin) return updateAdmin({ assignedStaffId: technician, responseAction: technician !== row.assignedStaffId ? 'Request availability' : decision, expectedArrival: arrivalTimestamp(arrival), responseNotes: notes, contactMethod: 'Email' }, 'Technician response recorded.');
    return mutate(`/staff/villa-operations/${row.id}/response`, 'POST', { expectedUpdatedAt: row.updatedAt, decision, expectedArrival: arrivalTimestamp(arrival), notes }, 'Availability sent. This request is now in My tasks while the administrator reviews the schedule.');
  }
  const content = <div className="villa-maintenance-page">
    <button className="villa-maintenance-back" disabled={busy} onClick={onBack}>{modal ? <><ArrowLeft size={17}/>Close villa view</> : <><ArrowLeft size={17}/>Back to villas</>}</button>
    <header className="villa-maintenance-heading"><div><span>Villa maintenance</span><h2>{villa.title}</h2></div><span className={`villa-maintenance-badge ${underMaintenance ? 'paused' : 'available'}`}>{underMaintenance ? 'Under Maintenance' : active.length ? 'Schedule pending · bookings open' : 'Available · bookings open'}</span></header>
    {error && <p className="villa-maintenance-alert" role="alert"><AlertCircle size={18}/>{formatUserFacingMessage(error)}</p>}{notice && <p className="villa-maintenance-success" role="status"><CheckCircle2 size={18}/>{notice}</p>}
    {loading ? <p role="status">Loading villa maintenance…</p> : loadError ? <p className="villa-maintenance-alert" role="alert">{formatUserFacingMessage(loadError)}<button onClick={load}>Retry</button></p> : showRequest ? <section className="villa-maintenance-panel"><RequestForm busy={busy} submit={create}/></section> : row && <>
      {records.length > 1 && <label className="villa-maintenance-history">Maintenance history<select value={row.id} onChange={event => { setSelected(event.target.value); setError(''); setNotice(''); }}>{records.map(item => <option key={item.id} value={item.id}>{item.title} · {statusLabel(item)}</option>)}</select></label>}
      <section className="villa-maintenance-panel"><div className="villa-maintenance-job-heading"><div><span>{row.taskCode || 'Maintenance request'} · {row.maintenance?.kind || 'Repair'}</span><h3>{row.title}</h3></div><span className="villa-maintenance-badge">{statusLabel(row)}</span></div><p className="villa-maintenance-description">{row.description}</p>
        <dl className="villa-maintenance-facts"><div><dt>Technician</dt><dd>{row.assignedToMe ? 'Assigned to you' : row.assignedTo || 'Maintenance staff'}</dd></div><div><dt>Email</dt><dd>{row.technicianEmail || (row.assignedToMe ? 'Your account email' : 'No email on file')}</dd></div><div><dt>Availability</dt><dd>{onCall.state || 'Contacting technician'}</dd></div><div><dt>Expected arrival</dt><dd>{dateTime(onCall.expectedArrival)}</dd></div><div><dt>Progress</dt><dd>{row.progress || 0}%</dd></div></dl>
        {technicianEmail && !isClosed(row) && <a className="villa-maintenance-secondary" href={`mailto:${encodeURIComponent(technicianEmail)}`}><Mail size={16}/>Email technician</a>}
        {onCall.attentionNeeded && !isClosed(row) && <p className="villa-maintenance-help">{onCall.attentionReason}</p>}
        {row.maintenance?.waitingForParts && <p className="villa-maintenance-help"><Clock3 size={16}/>Waiting for parts{row.maintenance.partsNotes ? `: ${row.maintenance.partsNotes}` : ''}</p>}
        {row.notes && (admin || row.status !== 'In Progress') && <div className="villa-maintenance-findings"><h4>Work performed / findings</h4><p>{row.notes}</p></div>}
        {admin && row.status === 'Pending' && <details className="villa-maintenance-details"><summary>Record an email response or change technician</summary><AvailabilityForm key={row.updatedAt} row={row} admin technicians={technicians} busy={busy} submit={respond}/></details>}
        {!admin && row.assignedToMe && row.status === 'Pending' && onCall.state === 'Awaiting response' && <AvailabilityForm key={row.updatedAt} row={row} busy={busy} submit={respond} bookedPeriods={bookedPeriods}/>}
        {!admin && row.assignedToMe && row.status === 'Pending' && onCall.state === 'Accepted' && <p className="villa-maintenance-awaiting-admin">Your availability is confirmed. The administrator will approve the schedule before booking availability is paused.</p>}
        {admin && row.status === 'Pending' && onCall.state === 'Accepted' && <div className="villa-maintenance-schedule-approval"><p>The technician confirmed availability for <strong>{dateTime(onCall.expectedArrival)}</strong>. Confirm the schedule to start maintenance and pause new bookings.</p><button className="villa-maintenance-primary" disabled={busy} onClick={() => updateAdmin({ status: 'In Progress', blocksBooking: !!row.maintenance?.villaId }, 'Schedule confirmed. The Villa is now under maintenance and new bookings are paused.')}>{busy ? 'Confirming…' : 'Confirm schedule & pause bookings'}</button></div>}
        {!admin && row.assignedToMe && row.status === 'In Progress' && <WorkForm key={row.updatedAt} row={row} busy={busy} submit={body => mutate(`/staff/tasks/${row.id}`, 'PATCH', body, 'Maintenance progress saved for admin review.')}/>}
        {row.status === 'Pending Review' && (admin ? <VerificationForm key={row.updatedAt} row={row} busy={busy} submit={changes => updateAdmin(changes, 'Work verified. Villa availability has been restored.')}/> : <p className="villa-maintenance-help">Your work is submitted. The villa remains under maintenance until admin verification.</p>)}
        {row.status === 'Completed' && <p className="villa-maintenance-complete"><CheckCircle2 size={20}/>Maintenance completed and verified{active.length ? '. Other maintenance work is still open.' : '. Booking availability has been restored.'}</p>}
        {admin && !isClosed(row) && <details className="villa-maintenance-details"><summary>Cancel this maintenance request</summary><VerificationForm row={row} busy={busy} cancel submit={changes => updateAdmin(changes, 'Maintenance request cancelled. Villa availability refreshed.')}/></details>}
        {active.length === 0 && <button className="villa-maintenance-primary" disabled={busy} onClick={() => setRequesting(true)}><Wrench size={17}/>Request maintenance</button>}
      </section>
    </>}
  </div>;
  if (!modal) return content;
  return <div className="villa-maintenance-modal-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !busy) onBack?.();
  }}>
    <section className="villa-maintenance-modal" role="dialog" aria-modal="true" aria-label={`${villa.title} maintenance`}>
      {content}
    </section>
  </div>;
}
