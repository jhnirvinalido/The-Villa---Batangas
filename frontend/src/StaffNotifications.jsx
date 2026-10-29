import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Bell, CheckCheck, ChevronRight, ClipboardList, LoaderCircle, X } from 'lucide-react';
import { newUnreadNotifications, notificationId, staffNotificationTime } from './staffNotificationFeed.mjs';
import { playStaffNotificationSound, showStaffBrowserNotification } from './staffBrowserNotifications.mjs';
import './StaffNotifications.css';

export default function StaffNotifications({ staffId, notifications, apiRequest, openTask, refresh, popupsEnabled = true, setNotifications }) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  const [locallyRead, setLocallyRead] = useState(new Set());
  const [missedCount, setMissedCount] = useState(0);
  const [browserError, setBrowserError] = useState('');
  const [browserEnabled, setBrowserEnabled] = useState(() => {
    try { return 'Notification' in window && Notification.permission === 'granted' && localStorage.getItem(`theVillaBrowserAlerts:${staffId}`) === 'true'; }
    catch { return false; }
  });
  const [browserBusy, setBrowserBusy] = useState(false);
  const seen = useRef({ owner: '', ids: new Set() });
  const pendingRead = useRef(false);
  const root = useRef(null);
  const bell = useRef(null);
  const panelId = useId();
  const storageKey = `theVillaStaffAlerts:${staffId}`;

  useEffect(() => {
    if (!staffId || !popupsEnabled) { setAlerts([]); return; }
    if (seen.current.owner !== staffId) {
      let stored = [];
      try { const value = JSON.parse(sessionStorage.getItem(storageKey) || '[]'); if (Array.isArray(value)) stored = value.filter(id => typeof id === 'string'); } catch { /* Session storage is optional. */ }
      seen.current = { owner: staffId, ids: new Set(stored) };
    }
    const incoming = newUnreadNotifications(notifications, seen.current.ids);
    if (!incoming.length) return;
    incoming.forEach(item => seen.current.ids.add(item.id));
    try { sessionStorage.setItem(storageKey, JSON.stringify([...seen.current.ids].slice(-2000))); } catch { /* Memory still prevents repeats. */ }
    setAlerts(current => [...incoming, ...current.filter(item => !incoming.some(next => next.id === item.id))].slice(0, 3));
    setMissedCount(Math.max(0, incoming.length - 3));
    if (document.visibilityState === 'visible') playStaffNotificationSound();
    if (browserEnabled && document.visibilityState === 'hidden') {
      showStaffBrowserNotification(incoming[0], staffId, incoming.length).then(shown => {
        if (!shown) setBrowserError('Browser alerts could not be displayed. Your updates are still in this inbox.');
      });
    }
  }, [staffId, storageKey, notifications, popupsEnabled, browserEnabled]);

  async function toggleBrowserAlerts() {
    setBrowserError('');
    if (browserEnabled) {
      setBrowserEnabled(false);
      try { localStorage.removeItem(`theVillaBrowserAlerts:${staffId}`); } catch { /* Optional preference storage. */ }
      return;
    }
    if (!('Notification' in window)) { setBrowserError('Browser notifications are not supported here. Use the in-app inbox.'); return; }
    if (!window.isSecureContext) { setBrowserError('Browser notifications require HTTPS or localhost.'); return; }
    setBrowserBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') { setBrowserError('Browser alerts are not enabled. Allow notifications in your browser settings to use them.'); return; }
      setBrowserEnabled(true);
      try { localStorage.setItem(`theVillaBrowserAlerts:${staffId}`, 'true'); } catch { /* Enabled for this page session. */ }
    } catch { setBrowserError('Could not enable browser alerts. Your in-app notifications still work.'); }
    finally { setBrowserBusy(false); }
  }

  useEffect(() => {
    if (!alerts.length) return;
    const timer = setTimeout(() => { setAlerts([]); setMissedCount(0); }, 9000);
    return () => clearTimeout(timer);
  }, [alerts]);

  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const key = event => { if (event.key === 'Escape') { setOpen(false); bell.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key); };
  }, [open]);

  const feed = useMemo(() => {
    const unique = new Map();
    for (const item of notifications || []) if (notificationId(item)) unique.set(item.id, { ...item, unread: item.unread && !locallyRead.has(item.id) });
    return [...unique.values()].sort((a, b) => (Date.parse(b.timestamp) || 0) - (Date.parse(a.timestamp) || 0));
  }, [notifications, locallyRead]);
  const unread = feed.filter(item => item.unread).length;

  async function read(items, all = false) {
    if (pendingRead.current) return false;
    const ids = items.filter(item => item.unread).map(item => item.id);
    if (!ids.length) return true;
    pendingRead.current = true;
    setReading(true); setError('');
    setLocallyRead(current => new Set([...current, ...ids]));
    try {
      await apiRequest(all ? '/staff/notifications/read-all' : `/staff/notifications/${encodeURIComponent(ids[0])}/read`, { method: 'PATCH' });
      setAlerts(current => current.filter(item => !ids.includes(item.id)));
      refresh();
      return true;
    } catch {
      setLocallyRead(current => new Set([...current].filter(id => !ids.includes(id))));
      setError('Could not mark notifications as read. Please try again.');
      return false;
    } finally { pendingRead.current = false; setReading(false); }
  }

  async function activate(item) {
    const current = feed.find(entry => entry.id === item.id) || item;
    const success = await read([current]);
    if (!success) { setOpen(true); return; }
    setAlerts(entries => entries.filter(entry => entry.id !== item.id));
    setOpen(false);
    if (item.taskId) openTask(item.taskId);
  }

  return <div className="staff-alert-center" ref={root}>
    <button type="button" ref={bell} className={`staff-alert-bell${unread ? ' has-unread' : ''}`} aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open} aria-controls={panelId} onClick={() => { setOpen(value => !value); setAlerts([]); }}>
      <Bell size={21} />{unread > 0 && <span className="staff-alert-count" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
    </button>
    {open && <section id={panelId} className="staff-alert-panel" aria-label="Staff notifications">
      <header><div><h2>Notifications</h2><p>{unread ? `${unread} unread update${unread === 1 ? '' : 's'}` : 'You’re all caught up'}</p></div><button type="button" className="staff-alert-close" aria-label="Close notifications" onClick={() => setOpen(false)}><X size={18} /></button></header>
      <div className="staff-alert-toolbar"><span>Assignments and updates</span><button type="button" disabled={!unread || reading} onClick={() => read(feed, true)}>{reading ? <LoaderCircle className="staff-alert-spin" size={14} /> : <CheckCheck size={14} />} Mark all read</button></div>
      {error && <p className="staff-alert-error" role="alert">{error}</p>}
      <div className="staff-alert-feed">{feed.length ? feed.slice(0, 100).map(item => <button type="button" disabled={reading} key={item.id} className={`staff-alert-item${item.unread ? ' unread' : ''}`} onClick={() => activate(item)}>
        <span className="staff-alert-icon"><ClipboardList size={18} /></span><span className="staff-alert-copy"><strong>{item.title || 'Staff update'}</strong><span>{item.message}</span><time dateTime={item.timestamp || undefined}>{staffNotificationTime(item.timestamp)}</time></span>{item.unread && <i aria-label="Unread" />}
      </button>) : <div className="staff-alert-empty"><Bell size={30} /><strong>No notifications yet</strong><p>Your assignments and updates will appear here.</p></div>}</div>
      <footer className="staff-alert-browser"><div><strong>Browser alerts</strong><small>Updates in other tabs while this portal stays open</small></div><button type="button" disabled={browserBusy || !popupsEnabled} onClick={toggleBrowserAlerts}>{browserBusy ? 'Enabling…' : browserEnabled ? 'Turn off' : 'Enable'}</button>{browserError && <p role="status">{browserError}</p>}</footer>
    </section>}
    <div className="staff-alert-popups" aria-live="polite" aria-atomic="false">
      {alerts.map(item => <article className="staff-alert-popup" key={item.id}>
        <span className="staff-alert-popup-icon"><Bell size={21} /></span><div><small>THE VILLA · STAFF UPDATE</small><strong>{item.title || 'New notification'}</strong><p>{item.message}</p><button type="button" disabled={reading} onClick={() => activate(item)}>{item.taskId ? 'View assignment' : 'View update'}<ChevronRight size={14} /></button></div>
        <button type="button" className="staff-alert-close" aria-label="Dismiss notification popup" onClick={() => setAlerts(current => current.filter(entry => entry.id !== item.id))}><X size={16} /></button>
      </article>)}
      {alerts.length > 0 && (missedCount > 0 || alerts.length > 1) && <button type="button" className="staff-alert-more" onClick={() => { setOpen(true); setAlerts([]); }}>View all {unread} unread updates</button>}
    </div>
  </div>;
}
