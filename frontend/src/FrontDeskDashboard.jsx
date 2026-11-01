import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { CalendarDays, CheckCircle2, ClipboardCheck, CreditCard, LogOut, Plus, RefreshCw, Search, Users, X } from 'lucide-react';
import { ConfirmSignOut } from './SystemFeedback';
import { frontDeskSection } from './portalRouting.mjs';
import { deskApi, deskSession, refreshDeskSession, signOutDesk } from './frontDeskApi.mjs';
import { bookingReadiness, deskBookingAction, deskDate, normalizeDeskBooking, peso } from './frontDeskModel.mjs';
import { snapshotRows } from './dashboardSnapshot.mjs';
import { singleFlightRefresh } from './liveTransport.mjs';
import { dateKey, isLate, timeLabel } from './taskFlow.mjs';
import useLiveUpdates from './useLiveUpdates';
import FrontDeskWalkIn from './FrontDeskWalkIn';
import FrontDeskSettlement from './FrontDeskSettlement';
import './FrontDeskDashboard.css';

const sections = [
  { id: 'bookings', label: 'Bookings', icon: CalendarDays, description: 'Incoming reservations, guest details, and room preparation.' },
  { id: 'walkIns', label: 'Walk-in bookings', icon: Plus, description: 'Record on-site guests and collect their full booking payment.' },
  { id: 'lifecycle', label: 'Check-in / out', icon: ClipboardCheck, description: 'Welcome arrivals, settle balances, and complete departures.' },
  { id: 'payments', label: 'Payment settlement', icon: CreditCard, description: 'Collect outstanding balances through cash or QRPh.' },
  { id: 'staff', label: 'Staff monitoring', icon: Users, description: 'See the staff scheduled to clean and prepare each villa on a specific day.' },
];
const actionLabel = { payment: 'Settle payment', checkin: 'Check in', checkout: 'Check out' };
function Badge({ children, tone = '' }) { return <span className={`fd-badge ${tone}`}>{children}</span>; }

export default function FrontDeskDashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const section = frontDeskSection(location);
  const meta = sections.find(item => item.id === (section === 'newWalkIn' ? 'walkIns' : section)) || sections[0];
  const [today, setToday] = useState(dateKey);
  const [profile, setProfile] = useState(() => deskSession().value.user || {});
  const [rawBookings, setRawBookings] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [staff, setStaff] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [day, setDay] = useState(dateKey);
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState('arrivals');
  const [monitorDay, setMonitorDay] = useState(dateKey);
  const [owner, setOwner] = useState('');
  const [selected, setSelected] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [working, setWorking] = useState(false);
  const [actionError, setActionError] = useState('');
  const [paymentBooking, setPaymentBooking] = useState(null);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [pendingPayment, setPendingPayment] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const detailsDialog = useRef(null);
  const lifecycleDialog = useRef(null);

  const fetchSnapshot = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await deskApi('/front-desk/bootstrap');
      const data = result.data || {};
      if (data.profile?.id) setProfile(data.profile);
      setRawBookings(current => snapshotRows(current, data.bookings, Boolean(data.bookingError)));
      setTasks(current => snapshotRows(current, data.tasks));
      setStaff(current => snapshotRows(current, data.staff));
      setReceipts(current => snapshotRows(current, data.paymentTransactions));
      setError(data.bookingError || (data.snapshotErrors?.length ? 'Some updates are unavailable. Showing the last available records.' : ''));
      setToday(dateKey());
    } catch (failure) { setError(failure.message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  const refresh = useMemo(() => singleFlightRefresh(fetchSnapshot), [fetchSnapshot]);
  const live = useLiveUpdates({ domains: ['bookings', 'tasks', 'staff', 'payments'], onChange: refresh, refreshAuth: refreshDeskSession, safetyRefreshMs: 60000 });
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { const timer = setInterval(() => setToday(dateKey()), 30000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (selected && !detailsDialog.current.open) detailsDialog.current.showModal();
    if (!selected && detailsDialog.current?.open) detailsDialog.current.close();
  }, [selected]);
  useEffect(() => {
    if (confirm && !lifecycleDialog.current.open) lifecycleDialog.current.showModal();
    if (!confirm && lifecycleDialog.current?.open) lifecycleDialog.current.close();
  }, [confirm]);

  const bookings = useMemo(() => rawBookings.map(normalizeDeskBooking), [rawBookings]);
  const active = bookings.filter(booking => !booking.cancelled && !booking.checkedOut);
  const outstanding = active.filter(booking => !booking.external && booking.balanceAmount > 0 && booking.verified);
  const query = search.trim().toLowerCase();
  const visible = bookings.filter(booking => {
    if (section === 'walkIns' && !booking.walkIn) return false;
    if (section === 'lifecycle' && (booking.cancelled || booking.checkedOut || (!booking.checkedIn && booking.checkIn !== today))) return false;
    if (section === 'payments' && !outstanding.some(item => item.id === booking.id)) return false;
    if (['bookings', 'walkIns'].includes(section)) {
      if (scope === 'arrivals' && (booking.cancelled || booking.checkedOut || booking.checkedIn || (day && booking.checkIn !== day))) return false;
      if (scope === 'inHouse' && !booking.checkedIn) return false;
    }
    return !query || [booking.guestName, booking.bookingCode, booking.villaName, booking.phone].join(' ').toLowerCase().includes(query);
  }).sort((a, b) => (section === 'lifecycle' ? a.checkOut : a.checkIn).localeCompare(section === 'lifecycle' ? b.checkOut : b.checkIn));

  const go = id => { navigate({ pathname: '/front-desk', search: id === 'bookings' ? '' : `?section=${id}` }); setSearch(''); };
  const openOperation = booking => {
    setActionError('');
    const action = deskBookingAction(booking, today);
    if (action === 'payment') {
      if (!pendingPayment) setPaymentBooking(booking);
      setPaymentOpen(true);
    } else if (action) setConfirm({ booking, action });
  };
  const completedPayment = useCallback(async message => {
    setPaymentBooking(null); setPaymentOpen(false); setPendingPayment(false); setNotice(message);
    await refresh();
  }, [refresh]);
  async function confirmLifecycle() {
    if (!confirm || working) return;
    setWorking(true); setActionError('');
    try {
      await deskApi(`/front-desk/bookings/${encodeURIComponent(confirm.booking.id)}/${confirm.action === 'checkin' ? 'check-in' : 'checkout'}`, { method: 'POST', body: JSON.stringify({ notes: 'Handled by Front Desk / Operations.' }) });
      setNotice(`${confirm.booking.guestName} ${confirm.action === 'checkin' ? 'checked in' : 'checked out'}.`);
      setConfirm(null);
      await refresh();
    } catch (failure) { setActionError(failure.message); }
    finally { setWorking(false); }
  }

  function renderBookings() {
    return <div className="fd-stack"><div className="fd-toolbar">
      {['bookings', 'walkIns'].includes(section) && <div className="fd-segments" role="group" aria-label="Booking view">{[['arrivals', 'Incoming'], ['inHouse', 'In house'], ['all', 'All bookings']].map(([value, text]) => <button type="button" key={value} aria-pressed={scope === value} onClick={() => setScope(value)}>{text}</button>)}</div>}
      <label className="fd-search"><Search size={16} /><input type="search" aria-label="Search bookings" placeholder="Search guest, villa, or booking…" value={search} onChange={event => setSearch(event.target.value)} /></label>
      {scope === 'arrivals' && ['bookings', 'walkIns'].includes(section) && <label className="fd-date">Arrival day<input type="date" value={day} onChange={event => setDay(event.target.value)} /><button type="button" onClick={() => setDay(today)}>Today</button></label>}
      {section === 'walkIns' && <button type="button" className="fd-button primary" onClick={() => go('newWalkIn')}><Plus size={16} /> Record walk-in</button>}
    </div><section className="fd-panel fd-table-panel"><header><div><h2>{section === 'lifecycle' ? 'Arrivals and current stays' : section === 'payments' ? 'Bookings with a balance' : scope === 'arrivals' ? `Incoming · ${deskDate(day)}` : scope === 'inHouse' ? 'Current stays' : 'Booking register'}</h2><p>{visible.length} reservation{visible.length === 1 ? '' : 's'}{section === 'payments' ? ' · Airbnb payments are handled externally.' : ''}</p></div></header>
      <div className="fd-table-wrap"><table><thead><tr><th>Guest / booking</th><th>Villa / stay</th><th>Payment</th><th>Stay status</th><th>Room preparation</th><th>Action</th></tr></thead><tbody>{visible.map(booking => {
        const readiness = bookingReadiness(booking, tasks);
        const action = deskBookingAction(booking, today);
        return <tr key={booking.id}><td><strong>{booking.guestName}</strong><small>{booking.bookingCode}</small><small>{booking.phone}</small></td><td><strong>{booking.villaName}</strong><small>{deskDate(booking.checkIn)} → {deskDate(booking.checkOut)}</small><small>{booking.guestCount} guests{booking.walkIn ? ' · Walk-in' : ''}</small></td><td><Badge tone={booking.external ? 'neutral' : booking.balanceAmount > 0 ? 'warning' : 'success'}>{booking.paymentStatus}</Badge><small>{booking.external ? 'External payment' : `${peso(booking.balanceAmount)} remaining`}</small></td><td><Badge tone={booking.cancelled ? 'danger' : booking.checkedIn ? 'success' : ''}>{booking.checkedOut ? 'Checked out' : booking.checkedIn ? 'Checked in' : booking.bookingStatus}</Badge></td><td>{!booking.checkedOut && !booking.cancelled && <><Badge tone={readiness.tone}>{readiness.label}</Badge><small>{readiness.staff}</small></>}</td><td><div className="fd-row-actions"><button type="button" className="fd-button" onClick={() => setSelected(booking)}>Details</button>{action && <button type="button" className="fd-button primary" onClick={() => openOperation(booking)}>{actionLabel[action]}</button>}{!action && !booking.checkedOut && !booking.cancelled && <small>{booking.checkIn > today ? 'Scheduled arrival' : !booking.verified ? 'Awaiting initial payment' : 'No action due'}</small>}</div></td></tr>;
      })}{!visible.length && <tr><td colSpan="6" className="fd-empty">{loading ? 'Loading reservations…' : 'No bookings match this view. Choose another day or view all bookings.'}</td></tr>}</tbody></table></div>
    </section>{section === 'payments' && <section className="fd-panel fd-table-panel"><header><div><h2>Recorded front desk payments</h2><p>Confirmed cash and QRPh settlements.</p></div></header><div className="fd-table-wrap"><table><thead><tr><th>Receipt / booking</th><th>Guest</th><th>Method</th><th>Amount</th><th>Processed</th></tr></thead><tbody>{receipts.slice(0, 50).map(receipt => <tr key={receipt.id}><td><strong>{receipt.receiptNumber || receipt.reference || 'Payment'}</strong><small>{receipt.bookingCode}</small></td><td>{receipt.guestName || receipt.customerName || 'Guest'}</td><td>{receipt.method}</td><td>{peso(receipt.amount)}</td><td>{receipt.processedAt ? new Date(receipt.processedAt).toLocaleString('en-PH', { timeZone: 'Asia/Manila' }) : 'Recorded'}</td></tr>)}{!receipts.length && <tr><td colSpan="5" className="fd-empty">No front desk payments recorded.</td></tr>}</tbody></table></div></section>}</div>;
  }

  function renderStaff() {
    const scheduled = tasks.filter(task => ['housekeeping-pre-arrival', 'housekeeping-turnover'].includes(task.assignmentType || task.assignment_type) && task.status !== 'Cancelled' && (!monitorDay || task.dueDate === monitorDay) && (!owner || task.assignedStaffId === owner) && (!query || [task.villaName, task.assignedTo, task.bookingCode].join(' ').toLowerCase().includes(query)))
      .sort((a, b) => `${a.dueDate} ${a.dueTime || ''}`.localeCompare(`${b.dueDate} ${b.dueTime || ''}`));
    const unassigned = active.filter(booking => !booking.checkedIn && booking.verified && (!monitorDay || booking.checkIn === monitorDay) && bookingReadiness(booking, tasks).label === 'No preparation assigned');
    return <div className="fd-stack"><div className="fd-toolbar"><label className="fd-date">Preparation day<input type="date" value={monitorDay} onChange={event => setMonitorDay(event.target.value)} /><button type="button" onClick={() => setMonitorDay(today)}>Today</button></label><button type="button" className="fd-button" onClick={() => setMonitorDay('')}>All days</button><label>Staff member<select value={owner} onChange={event => setOwner(event.target.value)}><option value="">All staff</option>{staff.filter(member => tasks.some(task => task.assignedStaffId === member.id)).map(member => <option key={member.id} value={member.id}>{member.name || member.fullName}</option>)}</select></label><label className="fd-search"><Search size={16} /><input type="search" aria-label="Search cleaning assignments" placeholder="Search villa, staff, or booking…" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
      {unassigned.length > 0 && <div className="fd-notice warning"><strong>{unassigned.length} arrivals need preparation staff.</strong><span>{unassigned.map(booking => `${booking.villaName} (${booking.bookingCode})`).join(', ')}. Ask Admin to review staff assignments.</span></div>}
      <section className="fd-panel fd-table-panel"><header><div><h2>Cleaning and room preparation</h2><p>{monitorDay ? deskDate(monitorDay) : 'All scheduled days'} · {scheduled.length} assignments</p></div><Badge>Monitoring only</Badge></header><div className="fd-table-wrap"><table><thead><tr><th>Villa / booking</th><th>Assigned staff</th><th>Scheduled preparation</th><th>Work</th><th>Status</th><th>Checklist</th></tr></thead><tbody>{scheduled.map(task => <tr key={task.id}><td><strong>{task.villaName || task.title}</strong><small>{task.bookingCode}</small></td><td><strong>{task.assignedTo || 'Unassigned'}</strong><small>{staff.find(member => member.id === task.assignedStaffId)?.shift || ''}</small></td><td><strong>{deskDate(task.dueDate)}</strong><small>{timeLabel(task.dueTime)}</small></td><td>{(task.assignmentType || task.assignment_type) === 'housekeeping-turnover' ? 'Check-out cleaning' : 'Arrival preparation'}</td><td><Badge tone={task.status === 'Completed' ? 'success' : isLate(task) ? 'danger' : 'warning'}>{task.status === 'Completed' ? 'Ready · approved' : isLate(task) ? 'Overdue' : task.status === 'Pending Review' ? 'Awaiting approval' : task.status === 'Pending' ? 'Assigned' : task.status}</Badge></td><td><span>{(task.checklist || []).filter(item => item.done).length} / {(task.checklist || []).length} steps</span><progress aria-label={`Checklist progress for ${task.villaName || task.title}`} value={(task.checklist || []).filter(item => item.done).length} max={Math.max(1, (task.checklist || []).length)} /></td></tr>)}{!scheduled.length && <tr><td colSpan="6" className="fd-empty">No cleaning assignments match this day and staff filter.</td></tr>}</tbody></table></div></section></div>;
  }

  return <div className="fd-shell" data-live-status={live}>
    <aside className="fd-sidebar"><Link to="/front-desk" className="fd-brand"><img src="/favicon.png" alt="The Villa" /><span>The Villa<small>Front Desk / Operations</small></span></Link><div className="fd-identity"><span className="fd-avatar">{String(profile.fullName || profile.full_name || profile.name || 'FD').split(' ').map(word => word[0]).slice(0, 2).join('')}</span><strong>{profile.fullName || profile.full_name || profile.name || 'Front Desk'}</strong><small>Guest operations workspace</small></div><nav aria-label="Front Desk navigation">{sections.map(item => { const Icon = item.icon; const current = item.id === (section === 'newWalkIn' ? 'walkIns' : section); return <button type="button" key={item.id} aria-current={current ? 'page' : undefined} onClick={() => go(item.id === 'walkIns' ? 'newWalkIn' : item.id)}><Icon size={18} /><span>{item.label}</span></button>; })}</nav><footer><button type="button" onClick={() => setSignOutOpen(true)}><LogOut size={16} /> Sign out</button></footer></aside>
    <main className="fd-main"><header className="fd-page-heading"><div><span className="fd-eyebrow">Front Desk / Operations</span><h1>{section === 'newWalkIn' ? 'Record a walk-in' : meta.label}</h1><p>{meta.description}</p></div><div><span className="fd-today">{deskDate(today)} · Philippine time</span><button type="button" className="fd-button" disabled={refreshing} onClick={() => refresh()}><RefreshCw size={15} className={refreshing ? 'fd-spin' : ''} />{refreshing ? 'Updating…' : 'Refresh'}</button></div></header>
      {error && <div className="fd-notice error" role="alert"><span>{error}</span><button type="button" className="fd-button" onClick={() => refresh()}>Retry</button></div>}
      {notice && <div className="fd-notice success" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button type="button" className="fd-icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={16} /></button></div>}
      {pendingPayment && <div className="fd-notice warning"><span>A QRPh payment for {paymentBooking?.bookingCode} is awaiting verification.</span><button type="button" className="fd-button" onClick={() => setPaymentOpen(true)}>Resume payment</button></div>}
      {section === 'staff' ? renderStaff() : section !== 'newWalkIn' ? renderBookings() : null}
      <div hidden={section !== 'newWalkIn'}><FrontDeskWalkIn active={section === 'newWalkIn'} onChanged={refresh} /></div>
    </main>
    <dialog ref={detailsDialog} className="fd-dialog" onCancel={() => setSelected(null)}><header><div><span className="fd-eyebrow">Booking details</span><h2>{selected?.bookingCode}</h2></div><button type="button" className="fd-icon-button" aria-label="Close booking details" onClick={() => setSelected(null)}><X size={20} /></button></header>{selected && <div className="fd-stack"><dl className="fd-details">{[['Guest', selected.guestName], ['Contact', selected.phone || 'Not provided'], ['Email', selected.email || 'Not provided'], ['Villa', selected.villaName], ['Check-in', deskDate(selected.checkIn)], ['Check-out', deskDate(selected.checkOut)], ['Guests', selected.guestCount], ['Payment', selected.paymentStatus], ['Booking total', peso(selected.totalAmount)], ['Balance', selected.external ? 'Handled by Airbnb' : peso(selected.balanceAmount)]].map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><p>{selected.notes || 'No guest notes.'}</p><div className="fd-notice"><strong>{bookingReadiness(selected, tasks).label}</strong><span>{bookingReadiness(selected, tasks).staff}</span><button type="button" className="fd-button" onClick={() => { setSelected(null); setMonitorDay(selected.checkIn); go('staff'); }}>View staff monitoring</button></div><footer><button type="button" className="fd-button" onClick={() => setSelected(null)}>Close</button>{deskBookingAction(selected, today) && <button type="button" className="fd-button primary" onClick={() => { setSelected(null); openOperation(selected); }}>{actionLabel[deskBookingAction(selected, today)]}</button>}</footer></div>}</dialog>
    <dialog ref={lifecycleDialog} className="fd-dialog" onCancel={event => { if (working) event.preventDefault(); else setConfirm(null); }}><header><h2>Confirm {confirm?.action === 'checkin' ? 'check-in' : 'check-out'}</h2><button type="button" className="fd-icon-button" disabled={working} aria-label="Close confirmation" onClick={() => setConfirm(null)}><X size={20} /></button></header>{confirm && <div className="fd-stack"><p><strong>{confirm.booking.guestName}</strong> · {confirm.booking.villaName}<br />{confirm.booking.bookingCode}</p><p>{confirm.action === 'checkin' ? 'Confirm that the guest has arrived. Check-in is available on the booked arrival day.' : 'Confirm the guest has departed. Checkout starts the room turnover workflow.'}</p>{actionError && <div className="fd-notice error" role="alert">{actionError}</div>}<footer><button type="button" className="fd-button" disabled={working} onClick={() => setConfirm(null)}>Cancel</button><button type="button" className="fd-button primary" disabled={working} onClick={confirmLifecycle}>{working ? 'Saving…' : actionLabel[confirm.action]}</button></footer></div>}</dialog>
    {paymentBooking && <FrontDeskSettlement key={paymentBooking.id} booking={paymentBooking} open={paymentOpen} onClose={hold => { setPaymentOpen(false); if (!hold) setPaymentBooking(null); }} onPending={setPendingPayment} onComplete={completedPayment} />}
    <ConfirmSignOut open={signOutOpen} busy={signingOut} cancel={() => setSignOutOpen(false)} confirm={async () => { setSigningOut(true); try { await signOutDesk(); } catch { /* Local session is cleared even if server logout fails. */ } finally { navigate('/login', { replace: true }); } }} />
  </div>;
}
