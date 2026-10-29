import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CalendarClock, CheckCircle2, ChevronRight, LoaderCircle, Wrench } from 'lucide-react';
import useLiveUpdates from './useLiveUpdates';
import VillaMaintenance from './VillaMaintenance';
import './StaffVillaOperations.css';

export default function StaffVillaOperations({ apiRequest, onChanged, initialVillaId = '' }) {
  const [villas, setVillas] = useState([]);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRequestId, setSelectedRequestId] = useState('');

  const load = useCallback(async () => {
    try {
      const result = await apiRequest('/staff/villa-operations');
      setVillas(result.data?.villas || []);
      setReports(result.data?.reports || []);
      setError('');
    } catch (failure) {
      setError(failure.message || 'Maintenance workspace could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [apiRequest]);

  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);
  useLiveUpdates({ domains: ['catalog', 'tasks'], onChange: load });

  const requests = reports.filter(report => report.canRespond
    && report.status === 'Pending'
    && report.maintenance?.onCall?.state === 'Awaiting response'
    && (!initialVillaId || report.maintenance?.villaId === initialVillaId));
  const selectedRequest = reports.find(report => report.id === selectedRequestId);
  const selectedVilla = selectedRequest
    ? villas.find(item => item.id === selectedRequest.maintenance?.villaId)
      || { id: selectedRequest.maintenance?.villaId, title: selectedRequest.villaName || 'Villa' }
    : null;

  return (
    <div className="staff-maintenance-workspace">
      <header className="staff-maintenance-header">
        <div>
          <span>MAINTENANCE WORKSPACE</span>
          <h2>New request</h2>
          <p>Maintenance requests from your administrator. Choose when you can attend each one.</p>
        </div>
        <div className="staff-maintenance-header-icon" aria-hidden="true"><Wrench size={24}/></div>
      </header>

      {error && <p role="alert" className="staff-maintenance-message is-error"><AlertCircle size={18}/>{error}</p>}

      <section className="staff-maintenance-inbox" aria-label="Incoming maintenance requests">
        {loading ? <p className="staff-maintenance-loading" role="status"><LoaderCircle size={18} className="staff-maintenance-spinner"/>Loading requests…</p> : requests.length ? (
          <div className="staff-maintenance-request-list">{requests.map(report => (
            <button type="button" className="staff-maintenance-request-row" key={report.id} onClick={() => setSelectedRequestId(report.id)}>
              <span className="staff-maintenance-request-icon"><Wrench size={17}/></span>
              <span className="staff-maintenance-request-copy">
                <span className="staff-maintenance-request-meta">{report.taskCode || 'Maintenance request'} · {report.priority || 'Medium'} priority</span>
                <strong>{report.title}</strong>
                <small>{report.villaName || 'Villa'} · {report.maintenance?.kind || 'Repair'}</small>
                <span className="staff-maintenance-request-action"><CalendarClock size={15}/>Choose availability</span>
              </span>
              <ChevronRight size={18}/>
            </button>
          ))}</div>
        ) : (
          <div className="staff-maintenance-empty"><CheckCircle2 size={25}/><strong>No new requests</strong><p>Requests assigned by your administrator will appear here.</p></div>
        )}
      </section>

      {selectedVilla && <VillaMaintenance key={selectedRequestId} villa={selectedVilla} role="staff" apiRequest={apiRequest} initialRequestId={selectedRequestId} modal onBack={() => setSelectedRequestId('')} onChanged={async () => { await load(); await onChanged?.(); }}/>}

    </div>
  );
}
