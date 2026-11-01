import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
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

function duration(record) {
  if (!record.clockInAt || !record.clockOutAt) return '—';
  const minutes = Math.floor((Date.parse(record.clockOutAt) - Date.parse(record.clockInAt)) / 60000);
  if (!Number.isFinite(minutes) || minutes < 0) return '—';
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export default function AdminWorkHours({ apiRequest, staff = [] }) {
  const [records, setRecords] = useState([]);
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [day, setDay] = useState('');
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pageSize, setPageSize] = useState(10);
  const [position, setPosition] = useState({ signature: '', page: 0 });
  const staffById = useMemo(() => new Map(staff.map(member => [member.id, member])), [staff]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiRequest('/admin/staff-time-records');
      if (!Array.isArray(response?.data)) throw new Error('Work-hours records were not returned by the server.');
      setRecords(response.data);
    } catch (failure) {
      setError(getUserFacingError(failure, 'Could not load staff work-hours records.'));
    } finally {
      setLoading(false);
    }
  }, [apiRequest]);

  useEffect(() => {
    let active = true;
    apiRequest('/admin/staff-time-records').then(response => {
      if (!Array.isArray(response?.data)) throw new Error('Work-hours records were not returned by the server.');
      if (active) setRecords(response.data);
    }).catch(failure => { if (active) setError(getUserFacingError(failure, 'Could not load staff work-hours records.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiRequest]);

  const filtered = records.filter(record => {
    const member = staffById.get(record.staffAccountId);
    const name = member?.name || member?.fullName || 'Staff member';
    const matchesText = `${name} ${member?.department || ''} ${record.reviewNote || ''}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesText && (status === 'all' || record.reviewStatus === status) && (!day || (record.clockInAt && dateKey(new Date(record.clockInAt)) === day));
  });
  const signature = JSON.stringify([query, status, day, pageSize, records.map(record => `${record.id}:${record.reviewStatus}`).join('|')]);
  const page = paginateRecords(filtered, position.signature === signature ? position.page : 0, pageSize);
  const changePage = value => setPosition({ signature, page: value });

  async function review(record, reviewStatus) {
    const reviewNote = String(notes[record.id] || '').trim();
    if (reviewStatus === 'needs_correction' && !reviewNote) {
      setError('Add a note before flagging a record for correction.');
      return;
    }
    setBusyId(record.id);
    setError('');
    try {
      await apiRequest(`/admin/staff-time-records/${encodeURIComponent(record.id)}/review`, {
        method: 'PATCH',
        body: JSON.stringify({ reviewStatus, reviewNote }),
      });
      await loadRecords();
    } catch (failure) {
      setError(getUserFacingError(failure, 'The work-hours record could not be reviewed.'));
    } finally {
      setBusyId('');
    }
  }

  return <section className="admin-work-hours" aria-labelledby="admin-work-hours-title">
    <header className="admin-work-hours-heading"><div><span>PEOPLE</span><h2 id="admin-work-hours-title">Work-hours review</h2><p>Review staff clock-in and clock-out records. Time values are recorded by the server.</p></div></header>
    <div className="admin-work-hours-controls">
      <label className="admin-work-hours-search"><Search size={16}/><input type="search" aria-label="Search work-hours records" placeholder="Search staff or note…" value={query} onChange={event => setQuery(event.target.value)}/></label>
      <select aria-label="Filter work-hours review status" value={status} onChange={event => setStatus(event.target.value)}>
        <option value="all">All statuses</option><option value="open">Clocked in</option><option value="pending_review">Awaiting review</option><option value="approved">Approved</option><option value="needs_correction">Needs attention</option>
      </select>
      <input type="date" aria-label="Filter staff work hours by clock-in date" value={day} onChange={event => setDay(event.target.value)}/>
      {(query || status !== 'all' || day) && <button type="button" className="admin-btn-ghost" onClick={() => {setQuery('');setStatus('all');setDay('');}}>Clear filters</button>}
      <button type="button" className="admin-btn-ghost" disabled={loading} onClick={loadRecords}>Refresh</button>
    </div>
    {error && <p className="admin-work-hours-error" role="alert">{formatUserFacingMessage(error)}</p>}
    <div className="admin-work-hours-table-wrap" role="region" aria-label="Staff work hours table" tabIndex={0}><table className="admin-work-hours-table" aria-busy={loading || undefined}>
      <thead><tr><th>Staff member</th><th>Clock in</th><th>Clock out</th><th>Duration</th><th>Status</th><th>Review note / action</th></tr></thead>
      <tbody>{page.rows.map(record => {
        const member = staffById.get(record.staffAccountId);
        const name = member?.name || member?.fullName || 'Staff member';
        return <tr key={record.id}>
          <td><strong>{name}</strong><small>{member?.department || member?.employeeCode || '—'}</small></td>
          <td>{stamp(record.clockInAt)}</td><td>{stamp(record.clockOutAt)}</td><td>{duration(record)}</td>
          <td><span className={`admin-work-hours-status status-${record.reviewStatus}`}>{record.reviewStatus === 'pending_review' ? 'Awaiting review' : record.reviewStatus === 'needs_correction' ? 'Needs attention' : record.reviewStatus === 'approved' ? 'Approved' : 'Clocked in'}</span></td>
          <td>{record.reviewStatus === 'pending_review' ? <div className="admin-work-hours-review"><input aria-label={`Review note for ${name}`} maxLength={1000} placeholder="Optional approval note; required to flag" value={notes[record.id] || ''} onChange={event => setNotes(current => ({ ...current, [record.id]: event.target.value }))}/><div><button type="button" disabled={!!busyId} onClick={() => review(record, 'approved')}>Approve</button><button type="button" disabled={!!busyId} onClick={() => review(record, 'needs_correction')}>Flag</button></div></div> : record.reviewNote || '—'}</td>
        </tr>;
      })}{!page.total && <tr><td colSpan={6} className="admin-work-hours-empty">{loading ? 'Loading work-hours records…' : error ? 'Work-hours records could not be loaded. Refresh to try again.' : 'No records match these filters.'}</td></tr>}</tbody>
    </table></div>
    <RecordPagination page={page} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={setPageSize} label="work-hours records"/>
  </section>;
}
