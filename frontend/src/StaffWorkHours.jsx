import { useCallback, useEffect, useState } from 'react';
import { Clock3, LogIn, LogOut, RefreshCw } from 'lucide-react';
import { RecordPagination } from './RecordListControls';
import { paginateRecords } from './recordListModel.mjs';
import { dateKey } from './taskFlow.mjs';
import { formatUserFacingMessage, getUserFacingError } from './errorMessages.mjs';

function stamp(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('en-PH', {
    timeZone: 'Asia/Manila',
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function workedDuration(record, now) {
  if (!record.clockInAt) return '—';
  const started = Date.parse(record.clockInAt);
  const ended = record.clockOutAt ? Date.parse(record.clockOutAt) : now;
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return '—';
  const minutes = Math.floor((ended - started) / 60000);
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export default function StaffWorkHours({ apiRequest, initialDate = '' }) {
  const [records, setRecords] = useState([]);
  const [day, setDay] = useState(initialDate);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [now, setNow] = useState(Date.now);
  const [pageSize, setPageSize] = useState(10);
  const [position, setPosition] = useState({ signature: '', page: 0 });
  const active = records.find(record => !record.clockOutAt);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiRequest('/staff/time-records');
      if (!Array.isArray(response?.data)) throw new Error('Work-hours records were not returned by the server.');
      setRecords(response.data);
    } catch (failure) {
      setError(getUserFacingError(failure, 'Could not load your work-hours records.'));
    } finally {
      setLoading(false);
    }
  }, [apiRequest]);

  useEffect(() => {
    let active = true;
    apiRequest('/staff/time-records').then(response => {
      if (!Array.isArray(response?.data)) throw new Error('Work-hours records were not returned by the server.');
      if (active) setRecords(response.data);
    }).catch(failure => { if (active) setError(getUserFacingError(failure, 'Could not load your work-hours records.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiRequest]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const filtered = records.filter(record => (!day || (record.clockInAt && dateKey(new Date(record.clockInAt)) === day)) && (!status || record.reviewStatus === status));
  const signature = JSON.stringify([day, status, records.map(record => `${record.id}:${record.updatedAt}`).join('|'), pageSize]);
  const page = paginateRecords(filtered, position.signature === signature ? position.page : 0, pageSize);
  const changePage = value => setPosition({ signature, page: value });

  async function toggleClock() {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      await apiRequest(active ? '/staff/time-records/clock-out' : '/staff/time-records/clock-in', { method: 'POST' });
      await loadRecords();
      setNotice(active ? 'Clock-out recorded and sent to your administrator for review.' : 'Clock-in recorded.');
    } catch (failure) {
      setError(getUserFacingError(failure, 'Your clock entry could not be saved.'));
    } finally {
      setSaving(false);
    }
  }

  return <section className="staff-work-hours" aria-labelledby="staff-work-hours-title">
    <header className="staff-work-hours-heading">
      <div><span>STAFF TIMEKEEPING</span><h2 id="staff-work-hours-title">Work hours</h2><p>Record your actual shift times. Completed entries are sent to an administrator for review.</p></div>
      <button type="button" className={active ? 'staff-btn-ghost' : 'staff-btn-primary'} disabled={saving || loading || !!error} onClick={toggleClock}>
        {active ? <LogOut size={16}/> : <LogIn size={16}/>}
        {saving ? 'Saving…' : active ? 'Clock out' : 'Clock in'}
      </button>
    </header>
    {active && <div className="staff-hours-active" role="status"><Clock3 size={17}/><span>Clocked in since {stamp(active.clockInAt)}</span><strong>{workedDuration(active, now)}</strong></div>}
    {notice && <p className="staff-hours-notice" role="status">{formatUserFacingMessage(notice)}</p>}
    {error && <p className="staff-hours-error" role="alert">{formatUserFacingMessage(error)}</p>}
    <div className="record-toolbar">
      <label>Clock-in date <input type="date" aria-label="Filter work hours by clock-in date" value={day} onChange={event => setDay(event.target.value)}/></label>
      <select aria-label="Filter my work-hours status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option><option value="open">Clocked in</option><option value="pending_review">Awaiting review</option><option value="approved">Approved</option><option value="needs_correction">Needs attention</option></select>
      {(day || status) && <button type="button" className="staff-btn-ghost" onClick={() => {setDay('');setStatus('');}}>Clear filters</button>}
    </div>
    <div className="staff-hours-table-wrap" role="region" aria-label="My work hours table" tabIndex={0}><table className="staff-hours-table" aria-busy={loading || undefined}>
      <thead><tr><th>Clock in</th><th>Clock out</th><th>Duration</th><th>Review status</th><th>Administrator note</th></tr></thead>
      <tbody>{page.rows.map(record => <tr key={record.id}>
        <td>{stamp(record.clockInAt)}</td><td>{stamp(record.clockOutAt)}</td><td>{workedDuration(record, now)}</td>
        <td><span className={`staff-hours-status status-${record.reviewStatus}`}>{record.reviewStatus === 'pending_review' ? 'Awaiting review' : record.reviewStatus === 'needs_correction' ? 'Needs attention' : record.reviewStatus === 'approved' ? 'Approved' : 'In progress'}</span></td>
        <td>{record.reviewNote || '—'}</td>
      </tr>)}{!page.total && <tr><td className="staff-hours-empty" colSpan={5}>{loading ? 'Loading time records…' : 'No work-hours records yet. Clock in when your shift starts.'}</td></tr>}</tbody>
    </table></div>
    <RecordPagination page={page} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={setPageSize} label="time records"/>
    <button type="button" className="staff-hours-refresh" disabled={loading || saving} onClick={loadRecords}><RefreshCw size={14}/>Refresh records</button>
  </section>;
}
