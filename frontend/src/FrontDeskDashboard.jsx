import SidebarBrand from "./SidebarBrand";
import usePortalSidebar from "./usePortalSidebar";
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { CalendarDays, CheckCircle2, ClipboardCheck, CreditCard, LogOut, Pencil, Plus, RefreshCw, ReceiptText, Users, X } from 'lucide-react';
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
import FrontDeskTable from './FrontDeskTable';
import FrontDeskRecordDetails from './FrontDeskRecordDetails';
import './FrontDeskDashboard.css';

const sections = [
  { id: 'bookings', label: 'Bookings', icon: CalendarDays, description: 'Incoming reservations, guest details, and room preparation.' },
  { id: 'walkIns', label: 'Walk-in bookings', icon: Plus, description: 'Record on-site guests and collect their full booking payment.' },
  { id: 'lifecycle', label: 'Check-in / out', icon: ClipboardCheck, description: 'Welcome arrivals, settle balances, and complete departures.' },
  { id: 'payments', label: 'Payment settlement', icon: CreditCard, description: 'Collect outstanding balances through cash or QRPh.' },
  { id: 'receipts', label: 'Payment history', icon: ReceiptText, description: 'Search and review recorded cash and QRPh settlements.' },
  { id: 'staff', label: 'Staff monitoring', icon: Users, description: 'See the staff scheduled to clean and prepare each villa on a specific day.' },
];
const actionLabel = { payment: 'Settle payment', checkin: 'Check in', checkout: 'Check out' };
function Badge({ children, tone = '' }) { return <span className={`fd-badge ${tone}`}>{children}</span>; }
const bookingStay = booking => booking.checkedOut ? 'Checked out' : booking.checkedIn ? 'Checked in' : booking.bookingStatus;
const workLabel = task => (task.assignmentType || task.assignment_type) === 'housekeeping-turnover' ? 'Check-out cleaning' : 'Arrival preparation';
const processedDay = value => value && Number.isFinite(new Date(value).getTime()) ? dateKey(new Date(value)) : '';
function preparationState(task) {
  if (task.status === 'Completed') return { label: 'Ready · approved', tone: 'success' };
  if (isLate(task)) return { label: 'Overdue', tone: 'danger' };
  return { label: task.status === 'Pending Review' ? 'Awaiting approval' : task.status === 'Pending' ? 'Assigned' : task.status === 'In Progress' ? 'In progress' : task.status, tone: 'warning' };
}


export default function FrontDeskDashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const section = frontDeskSection(location);
  const meta = sections.find(item => item.id === (section === 'newWalkIn' ? 'walkIns' : section)) || sections[0];
  const [today, setToday] = useState(dateKey);
  const [sidebarCollapsed, setSidebarCollapsed] = usePortalSidebar();
  const [profile, setProfile] = useState(() => deskSession().value.user || {});
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileForm, setProfileForm] = useState({ fullName: '', personalEmail: '', nickname: '', avatarUrl: '' });
  const [profileError, setProfileError] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);
  const [rawBookings, setRawBookings] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [staff, setStaff] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [day, setDay] = useState(dateKey);
  const [villaFilter, setVillaFilter] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('');
  const [stayFilter, setStayFilter] = useState('');
  const [taskStatus, setTaskStatus] = useState('');
  const [taskType, setTaskType] = useState('');
  const [receiptMethod, setReceiptMethod] = useState('');
  const [receiptDate, setReceiptDate] = useState('');
  const [record, setRecord] = useState(null);
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
  const profileDialog = useRef(null);
  const detailsDialog = useRef(null);
  const recordDialog = useRef(null);
  const selectedTask = record?.type === 'task' ? tasks.find(task => task.id === record.id) : null;
  const selectedReceipt = record?.type === 'receipt' ? receipts.find(receipt => receipt.id === record.id) : null;
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
    if (profileOpen && !profileDialog.current?.open) profileDialog.current?.showModal();
    if (!profileOpen && profileDialog.current?.open) profileDialog.current.close();
  }, [profileOpen]);
  useEffect(() => {
    if (selected && !detailsDialog.current.open) detailsDialog.current.showModal();
    if (!selected && detailsDialog.current?.open) detailsDialog.current.close();
  }, [selected]);
  useEffect(() => {
    if (confirm && !lifecycleDialog.current.open) lifecycleDialog.current.showModal();
    if (!confirm && lifecycleDialog.current?.open) lifecycleDialog.current.close();
  }, [confirm]);

  useEffect(() => {
    const element = recordDialog.current;
    if (!selectedTask && !selectedReceipt) {
      if (element?.open) element.close();
      return undefined;
    }
    if (!element.open) element.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, [selectedTask, selectedReceipt]);

  const bookings = useMemo(() => rawBookings.map(normalizeDeskBooking), [rawBookings]);
  const villaNames = [...new Set([...bookings.map(booking => booking.villaName), ...tasks.map(task => task.villaName)].filter(Boolean))].sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
  const active = bookings.filter(booking => !booking.cancelled && !booking.checkedOut);
  const outstanding = active.filter(booking => !booking.external && booking.balanceAmount > 0 && booking.verified);
  const visible = bookings.filter(booking => {
    if (section === 'walkIns' && !booking.walkIn) return false;
    if (section === 'lifecycle' && (booking.cancelled || booking.checkedOut || (!booking.checkedIn && booking.checkIn !== today))) return false;
    if (section === 'payments' && !outstanding.some(item => item.id === booking.id)) return false;
    if (['bookings', 'walkIns'].includes(section)) {
      if (scope === 'arrivals' && (booking.cancelled || booking.checkedOut || booking.checkedIn || (day && booking.checkIn !== day))) return false;
      if (scope === 'inHouse' && !booking.checkedIn) return false;
    }
    return (!villaFilter || booking.villaName === villaFilter) && (!paymentFilter || booking.paymentStatus === paymentFilter) && (!stayFilter || bookingStay(booking) === stayFilter);
  });

  const go = id => { if (window.matchMedia("(max-width: 980px)").matches) setSidebarCollapsed(true); navigate({ pathname: '/front-desk', search: id === 'bookings' ? '' : `?section=${id}` }); setVillaFilter(''); setPaymentFilter(''); setStayFilter(''); setTaskStatus(''); setTaskType(''); setReceiptMethod(''); setReceiptDate(''); };
  function openProfileEditor() {
    setProfileForm({
      fullName: profile.fullName || profile.full_name || profile.name || '',
      personalEmail: profile.personalEmail || deskSession().value.user?.email || '',
      nickname: profile.nickname || '',
      avatarUrl: profile.avatarUrl || profile.avatar_url || '',
    });
    setProfileError('');
    setProfileOpen(true);
  }
  async function chooseProfilePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setProfileError('Choose a JPG, PNG, or WebP image smaller than 5 MB.');
      return;
    }
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 256;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Image processing is unavailable.');
      const size = Math.min(image.width, image.height);
      context.drawImage(image, (image.width - size) / 2, (image.height - size) / 2, size, size, 0, 0, 256, 256);
      setProfileForm(current => ({ ...current, avatarUrl: canvas.toDataURL('image/jpeg', 0.85) }));
      setProfileError('');
    } catch {
      setProfileError('This image could not be opened. Please choose another picture.');
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  async function saveProfile(event) {
    event.preventDefault();
    if (profileSaving) return;
    setProfileSaving(true);
    setProfileError('');
    try {
      const result = await deskApi('/front-desk/profile', {
        method: 'PATCH',
        body: JSON.stringify({
          fullName: profileForm.fullName.trim(),
          personalEmail: profileForm.personalEmail.trim(),
          nickname: profileForm.nickname.trim(),
          avatarUrl: profileForm.avatarUrl,
        }),
      });
      if (!result?.data?.id) throw new Error('Your profile could not be saved.');
      setProfile(result.data);
      const session = deskSession();
      session.storage.setItem('theVillaPortalAuth', JSON.stringify({
        ...session.value,
        user: { ...session.value.user, ...result.data },
      }));
      setProfileOpen(false);
      setNotice('Your profile has been updated.');
    } catch (failure) {
      setProfileError(failure instanceof Error ? failure.message : 'Unable to save your profile.');
    } finally {
      setProfileSaving(false);
    }
  }
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
    const title = section === 'lifecycle' ? 'Arrivals and current stays' : section === 'payments' ? 'Bookings with a balance' : scope === 'arrivals' ? `Incoming · ${deskDate(day)}` : scope === 'inHouse' ? 'Current stays' : 'Booking register';
    const columns = [
      { key: 'guest', label: 'Guest / booking', value: booking => booking.guestName, render: booking => <><strong>{booking.guestName}</strong><small>{booking.bookingCode}</small><small>{booking.phone}</small></> },
      { key: 'stay', label: 'Villa / stay', value: booking => section === 'lifecycle' ? booking.checkOut : booking.checkIn, render: booking => <><strong>{booking.villaName}</strong><small>{deskDate(booking.checkIn)} → {deskDate(booking.checkOut)}</small><small>{booking.guestCount} guests{booking.walkIn ? ' · Walk-in' : ''}</small></> },
      { key: 'total', label: 'Booking total (TCP)', value: booking => booking.totalAmount, render: booking => <strong className="record-money">{peso(booking.totalAmount)}</strong> },
      { key: 'paid', label: 'Amount paid', value: booking => booking.external ? null : booking.amountPaid, render: booking => <span className="record-money">{booking.external ? 'Handled by Airbnb' : peso(booking.amountPaid)}</span> },
      { key: 'balance', label: 'Balance due', value: booking => booking.external ? null : booking.balanceAmount, render: booking => <><strong className="record-money">{booking.external ? 'Handled by Airbnb' : peso(booking.balanceAmount)}</strong><small>{booking.paymentStatus}</small></> },
      { key: 'status', label: 'Stay status', value: bookingStay, render: booking => <Badge tone={booking.cancelled ? 'danger' : booking.checkedIn ? 'success' : ''}>{bookingStay(booking)}</Badge> },
      { key: 'preparation', label: 'Room preparation', value: booking => bookingReadiness(booking, tasks).label, render: booking => { const readiness = bookingReadiness(booking, tasks); return !booking.checkedOut && !booking.cancelled && <><Badge tone={readiness.tone}>{readiness.label}</Badge><small>{readiness.staff}</small></>; } },
      { key: 'action', label: 'Action', render: booking => { const action = deskBookingAction(booking, today); return <div className="fd-row-actions"><button type="button" className="fd-button" onClick={() => setSelected(booking)}>View details</button>{action && <button type="button" className="fd-button primary" onClick={() => openOperation(booking)}>{actionLabel[action]}</button>}{!action && !booking.checkedOut && !booking.cancelled && <small>{booking.checkIn > today ? 'Scheduled arrival' : !booking.verified ? 'Awaiting initial payment' : 'No action due'}</small>}</div>; } },
    ];
    return <FrontDeskTable key={section} title={title} description={section === 'payments' ? 'Outstanding balances only. View recorded settlements on the Payment history page. Airbnb payments are handled externally.' : 'Reservations and guest operations. Open Details for the full booking.'}
      rows={visible} columns={columns} initialSort="stay" loading={loading}
      filterKey={[scope, day, villaFilter, paymentFilter, stayFilter].join('|')}
      searchText={booking => [booking.guestName, booking.bookingCode, booking.villaName, booking.phone, booking.email, booking.paymentStatus, bookingStay(booking), bookingReadiness(booking, tasks).staff].join(' ')}
      actions={section === 'payments' ? <button type="button" className="fd-button" onClick={() => go('receipts')}>View payment history</button> : section === 'walkIns' ? <button type="button" className="fd-button primary" onClick={() => go('newWalkIn')}><Plus size={16}/>Record walk-in</button> : null}
      filters={<>
        {['bookings', 'walkIns'].includes(section) && <div className="fd-segments" role="group" aria-label="Booking view">{[['arrivals', 'Incoming'], ['inHouse', 'In house'], ['all', 'All bookings']].map(([value, text]) => <button type="button" key={value} aria-pressed={scope === value} onClick={() => setScope(value)}>{text}</button>)}</div>}
        {scope === 'arrivals' && ['bookings', 'walkIns'].includes(section) && <label className="fd-date">Arrival day<input type="date" value={day} onChange={event => setDay(event.target.value)}/><button type="button" onClick={() => setDay(today)}>Today</button></label>}
        <label>Villa<select value={villaFilter} onChange={event => setVillaFilter(event.target.value)}><option value="">All villas</option>{villaNames.map(name => <option key={name}>{name}</option>)}</select></label>
        <label>Payment<select value={paymentFilter} onChange={event => setPaymentFilter(event.target.value)}><option value="">All payments</option>{['Paid', 'Partially paid', 'Unpaid', 'Handled by Airbnb'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Stay status<select value={stayFilter} onChange={event => setStayFilter(event.target.value)}><option value="">All statuses</option>{[...new Set(bookings.map(bookingStay))].sort().map(value => <option key={value}>{value}</option>)}</select></label>
        <button type="button" className="fd-button" onClick={() => { setScope('all'); setDay(''); setVillaFilter(''); setPaymentFilter(''); setStayFilter(''); }}>Reset filters</button>
      </>}/>;
  }

  function renderReceipts() {
    const rows = receipts.filter(receipt => (!receiptMethod || receipt.method === receiptMethod) && (!receiptDate || processedDay(receipt.processedAt) === receiptDate));
    const methods = [...new Set(receipts.map(receipt => receipt.method).filter(Boolean))].sort();
    return <FrontDeskTable key="receipts" title="Recorded front desk payments" description="Confirmed cash and QRPh settlements. Search the available history by receipt, booking, guest, or cashier."
      rows={rows} initialSort="processed" initialDirection="desc" loading={loading} filterKey={[receiptMethod, receiptDate].join('|')}
      searchText={receipt => [receipt.receiptNumber, receipt.reference, receipt.bookingCode, receipt.guestName, receipt.customerName, receipt.payerName, receipt.villaName, receipt.cashierName, receipt.method].join(' ')}
      actions={<button type="button" className="fd-button" onClick={() => go('payments')}>Settle a balance</button>}
      filters={<>
        <label>Method<select value={receiptMethod} onChange={event => setReceiptMethod(event.target.value)}><option value="">All methods</option>{methods.map(method => <option key={method} value={method}>{method}</option>)}</select></label>
        <label className="fd-date">Processed day<input type="date" value={receiptDate} onChange={event => setReceiptDate(event.target.value)}/></label>
        <button type="button" className="fd-button" onClick={() => { setReceiptMethod(''); setReceiptDate(''); }}>Reset filters</button>
      </>}
      columns={[
        { key: 'receipt', label: 'Receipt / booking', value: receipt => receipt.receiptNumber || receipt.reference, render: receipt => <><strong>{receipt.receiptNumber || receipt.reference || 'Payment'}</strong><small>{receipt.bookingCode}</small></> },
        { key: 'guest', label: 'Guest', value: receipt => receipt.guestName || receipt.customerName || 'Guest' },
        { key: 'method', label: 'Method', value: receipt => receipt.method },
        { key: 'amount', label: 'Amount', value: receipt => Number(receipt.amount), render: receipt => peso(receipt.amount) },
        { key: 'processed', label: 'Processed', value: receipt => receipt.processedAt ? new Date(receipt.processedAt).getTime() : null, render: receipt => receipt.processedAt ? new Date(receipt.processedAt).toLocaleString('en-PH', { timeZone: 'Asia/Manila' }) : 'Recorded' },
        { key: 'action', label: 'Action', render: receipt => <button type="button" className="fd-button" onClick={() => setRecord({ type: 'receipt', id: receipt.id })}>View details</button> },
      ]}/>;
  }

  function renderStaff() {
    const scheduled = tasks.filter(task => ['housekeeping-pre-arrival', 'housekeeping-turnover'].includes(task.assignmentType || task.assignment_type) && task.status !== 'Cancelled'
      && (!monitorDay || task.dueDate === monitorDay) && (!owner || task.assignedStaffId === owner) && (!villaFilter || task.villaName === villaFilter)
      && (!taskStatus || preparationState(task).label === taskStatus) && (!taskType || (task.assignmentType || task.assignment_type) === taskType));
    const unassigned = active.filter(booking => !booking.checkedIn && booking.verified && (!monitorDay || booking.checkIn === monitorDay) && (!villaFilter || booking.villaName === villaFilter) && bookingReadiness(booking, tasks).label === 'No preparation assigned');
    return <div className="fd-stack">
      {unassigned.length > 0 && <div className="fd-notice warning"><strong>{unassigned.length} arrivals need preparation staff.</strong><span>Ask Admin to review staff assignments for the selected day.</span></div>}
      <FrontDeskTable key="staff" title="Cleaning and room preparation" description={`${monitorDay ? deskDate(monitorDay) : 'All scheduled days'} · Monitoring only. Open Details to view instructions, checklist steps, and handover notes.`}
        rows={scheduled} initialSort="scheduled" loading={loading} filterKey={[monitorDay, owner, villaFilter, taskStatus, taskType].join('|')}
        searchText={task => [task.villaName, task.title, task.assignedTo, task.bookingCode, task.description, task.notes, preparationState(task).label, ...(task.checklist || []).map(item => item.label)].join(' ')}
        filters={<>
          <label className="fd-date">Preparation day<input type="date" value={monitorDay} onChange={event => setMonitorDay(event.target.value)}/><button type="button" onClick={() => setMonitorDay(today)}>Today</button></label>
          <button type="button" className="fd-button" onClick={() => setMonitorDay('')}>All days</button>
          <label>Staff member<select value={owner} onChange={event => setOwner(event.target.value)}><option value="">All staff</option>{staff.filter(member => tasks.some(task => task.assignedStaffId === member.id)).map(member => <option key={member.id} value={member.id}>{member.name || member.fullName}</option>)}</select></label>
          <label>Villa<select value={villaFilter} onChange={event => setVillaFilter(event.target.value)}><option value="">All villas</option>{villaNames.map(name => <option key={name}>{name}</option>)}</select></label>
          <label>Status<select value={taskStatus} onChange={event => setTaskStatus(event.target.value)}><option value="">All statuses</option>{['Assigned', 'In progress', 'Overdue', 'Awaiting approval', 'Ready · approved'].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Work type<select value={taskType} onChange={event => setTaskType(event.target.value)}><option value="">All work</option><option value="housekeeping-pre-arrival">Arrival preparation</option><option value="housekeeping-turnover">Check-out cleaning</option></select></label>
          <button type="button" className="fd-button" onClick={() => { setMonitorDay(''); setOwner(''); setVillaFilter(''); setTaskStatus(''); setTaskType(''); }}>Reset filters</button>
        </>}
        columns={[
          { key: 'villa', label: 'Villa / booking', value: task => task.villaName || task.title, render: task => <><strong>{task.villaName || task.title}</strong><small>{task.bookingCode || 'No booking reference'}</small></> },
          { key: 'staff', label: 'Assigned staff', value: task => task.assignedTo, render: task => <><strong>{task.assignedTo || 'Unassigned'}</strong><small>{staff.find(member => member.id === task.assignedStaffId)?.shift || 'Shift not provided'}</small></> },
          { key: 'scheduled', label: 'Preparation date', value: task => task.dueDate ? `${task.dueDate} ${task.dueTime || '23:59'}` : '', render: task => <><strong>{deskDate(task.dueDate)}</strong><small>{timeLabel(task.dueTime)}</small></> },
          { key: 'work', label: 'Work', value: workLabel },
          { key: 'status', label: 'Status', value: task => preparationState(task).label, render: task => <Badge tone={preparationState(task).tone}>{preparationState(task).label}</Badge> },
          { key: 'checklist', label: 'Checklist', value: task => task.checklist?.length ? task.checklist.filter(item => item.done).length / task.checklist.length : -1, render: task => <><span>{(task.checklist || []).filter(item => item.done).length} / {(task.checklist || []).length} steps</span><progress aria-label={`Checklist progress for ${task.villaName || task.title}`} value={(task.checklist || []).filter(item => item.done).length} max={Math.max(1, (task.checklist || []).length)}/></> },
          { key: 'action', label: 'Action', render: task => <button type="button" className="fd-button" onClick={() => setRecord({ type: 'task', id: task.id })}>View details</button> },
        ]}/>
    </div>;
  }

  const profileName = profile.fullName || profile.full_name || profile.name || 'Front Desk';
  const profileAvatar = profile.avatarUrl || profile.avatar_url;
  const profileInitials = profileName.split(' ').map(word => word[0]).slice(0, 2).join('');
  return <div className={`fd-shell admin-dashboard-shell${sidebarCollapsed ? ' sidebar-collapsed' : ''}`} data-live-status={live}>
    <aside className="fd-sidebar admin-sidebar">
      <div className="fd-sidebar-inner admin-sidebar-inner">
        <header className="fd-brand admin-sidebar-brand">
          <SidebarBrand label="Front desk" collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(value => !value)} />
          </header>
        <nav className="admin-sidebar-nav" aria-label="Front Desk navigation">
          <button type="button" className="fd-identity admin-sidebar-profile-card admin-nav-profile" onClick={openProfileEditor} title="Edit profile">
            <span className="admin-sidebar-avatar-control">
              <span className="admin-avatar-wrap"><span className="admin-avatar">{profileAvatar ? <img src={profileAvatar} alt="" /> : profileInitials}</span></span>
              <span className="admin-sidebar-avatar-edit" aria-hidden="true"><Pencil className="h-3 w-3 shrink-0" size={12} strokeWidth={2.2}/></span>
            </span>
            <span className="admin-sidebar-profile-copy fd-identity-copy">
              <strong>{profileName}{profile.nickname && <> <span className="admin-profile-nickname">({profile.nickname})</span></>}</strong>
              <small className="admin-profile-role-label">{profile.position || 'Front Desk / Operations'}</small>
            </span>
          </button>
          {sections.map(item => {
            const Icon = item.icon;
            const current = item.id === (section === 'newWalkIn' ? 'walkIns' : section);
            return <button type="button" key={item.id} className={`admin-sidebar-nav-btn${current ? ' active' : ''}`} aria-current={current ? 'page' : undefined} onClick={() => go(item.id === 'walkIns' ? 'newWalkIn' : item.id)} aria-label={item.label} title={item.label}><Icon className="h-[18px] w-[18px] shrink-0" size={18}/><span className="admin-nav-label">{item.label}</span></button>;
          })}
        </nav>
        <footer className="admin-sidebar-footer"><button type="button" className="admin-logout-btn" aria-label="Sign out" title="Sign out" onClick={() => setSignOutOpen(true)}><LogOut className="h-4 w-4 shrink-0" size={16}/><span className="admin-nav-label">Sign out</span></button></footer>
      </div>
    </aside>
      {!sidebarCollapsed && <button type="button" className="portal-sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebarCollapsed(true)} />}
    <div className="fd-main-area admin-main-area">
    <main className="fd-main admin-page-content" aria-label={section === 'newWalkIn' ? 'Record a walk-in' : meta.label}>
      <header className="fd-page-heading dashboard-page-heading admin-sticky-page-bar">
        <div className="admin-sticky-page-title"><h1>{section === 'newWalkIn' ? 'Record a walk-in' : meta.label}</h1></div>
        <div className="fd-page-actions"><span className="fd-today">{deskDate(today)} · Philippine time</span><button type="button" className="fd-button" disabled={refreshing} onClick={() => refresh()}><RefreshCw size={15} className={refreshing ? 'fd-spin' : ''} />{refreshing ? 'Updating…' : 'Refresh'}</button></div>
      </header>
      {error && <div className="fd-notice error" role="alert"><span>{error}</span><button type="button" className="fd-button" onClick={() => refresh()}>Retry</button></div>}
      {notice && <div className="fd-notice success" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button type="button" className="fd-icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={16} /></button></div>}
      {pendingPayment && <div className="fd-notice warning"><span>A QRPh payment for {paymentBooking?.bookingCode} is awaiting verification.</span><button type="button" className="fd-button" onClick={() => setPaymentOpen(true)}>Resume payment</button></div>}
      {section === 'staff' ? renderStaff() : section === 'receipts' ? renderReceipts() : section !== 'newWalkIn' ? renderBookings() : null}
      <div hidden={section !== 'newWalkIn'}><FrontDeskWalkIn active={section === 'newWalkIn'} onChanged={refresh} /></div>
    </main>
    </div>
    <dialog ref={recordDialog} className="fd-dialog fd-record-dialog" onCancel={() => setRecord(null)} onClose={() => setRecord(null)} aria-label={selectedTask ? 'Assignment details' : 'Payment details'}>
      <FrontDeskRecordDetails task={selectedTask} receipt={selectedReceipt} staff={staff} bookings={bookings} onClose={() => setRecord(null)} status={selectedTask ? preparationState(selectedTask).label : ''} work={selectedTask ? workLabel(selectedTask) : ''}/>
    </dialog>
    <dialog ref={detailsDialog} className="fd-dialog" onCancel={() => setSelected(null)}><header><div><span className="fd-eyebrow">Booking details</span><h2>{selected?.bookingCode}</h2></div><button type="button" className="fd-icon-button" aria-label="Close booking details" onClick={() => setSelected(null)}><X size={20} /></button></header>{selected && <div className="fd-stack"><dl className="fd-details">{[['Guest', selected.guestName], ['Contact', selected.phone || 'Not provided'], ['Email', selected.email || 'Not provided'], ['Villa', selected.villaName], ['Check-in', deskDate(selected.checkIn)], ['Check-out', deskDate(selected.checkOut)], ['Guests', selected.guestCount], ['Payment', selected.paymentStatus], ['Booking total (TCP)', peso(selected.totalAmount)], ['Amount paid', selected.external ? 'Handled by Airbnb' : peso(selected.amountPaid)], ['Balance due', selected.external ? 'Handled by Airbnb' : peso(selected.balanceAmount)]].map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><p>{selected.notes || 'No guest notes.'}</p><div className="fd-notice"><strong>{bookingReadiness(selected, tasks).label}</strong><span>{bookingReadiness(selected, tasks).staff}</span><button type="button" className="fd-button" onClick={() => { setSelected(null); setMonitorDay(selected.checkIn); go('staff'); }}>View staff monitoring</button></div><footer><button type="button" className="fd-button" onClick={() => setSelected(null)}>Close</button>{deskBookingAction(selected, today) && <button type="button" className="fd-button primary" onClick={() => { setSelected(null); openOperation(selected); }}>{actionLabel[deskBookingAction(selected, today)]}</button>}</footer></div>}</dialog>
    <dialog ref={lifecycleDialog} className="fd-dialog" onCancel={event => { if (working) event.preventDefault(); else setConfirm(null); }}><header><h2>Confirm {confirm?.action === 'checkin' ? 'check-in' : 'check-out'}</h2><button type="button" className="fd-icon-button" disabled={working} aria-label="Close confirmation" onClick={() => setConfirm(null)}><X size={20} /></button></header>{confirm && <div className="fd-stack"><p><strong>{confirm.booking.guestName}</strong> · {confirm.booking.villaName}<br />{confirm.booking.bookingCode}</p><p>{confirm.action === 'checkin' ? 'Confirm that the guest has arrived. Check-in is available on the booked arrival day.' : 'Confirm the guest has departed. Checkout starts the room turnover workflow.'}</p>{actionError && <div className="fd-notice error" role="alert">{actionError}</div>}<footer><button type="button" className="fd-button" disabled={working} onClick={() => setConfirm(null)}>Cancel</button><button type="button" className="fd-button primary" disabled={working} onClick={confirmLifecycle}>{working ? 'Saving…' : actionLabel[confirm.action]}</button></footer></div>}</dialog>
    {paymentBooking && <FrontDeskSettlement key={paymentBooking.id} booking={paymentBooking} open={paymentOpen} onClose={hold => { setPaymentOpen(false); if (!hold) setPaymentBooking(null); }} onPending={setPendingPayment} onComplete={completedPayment} />}
    <dialog ref={profileDialog} className="fd-dialog fd-profile-dialog" aria-labelledby="fd-profile-title" onCancel={event => { if (profileSaving) event.preventDefault(); else setProfileOpen(false); }}>
      <header><div><span className="fd-eyebrow">My account</span><h2 id="fd-profile-title">Edit profile</h2></div><button type="button" className="fd-icon-button" aria-label="Close profile editor" disabled={profileSaving} onClick={() => setProfileOpen(false)}><X size={20}/></button></header>
      <form onSubmit={saveProfile}>
        <fieldset disabled={profileSaving}>
          <div className="fd-profile-photo-editor">
            <span className="fd-avatar">{profileForm.avatarUrl ? <img src={profileForm.avatarUrl} alt="Profile preview"/> : profileForm.fullName.split(' ').map(word => word[0]).slice(0, 2).join('')}</span>
            <label className="fd-button">Change photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseProfilePhoto}/></label>
            {profileForm.avatarUrl && <button type="button" className="fd-button" onClick={() => setProfileForm(current => ({ ...current, avatarUrl: '' }))}>Remove photo</button>}
          </div>
          <div className="fd-profile-fields">
            <label>Full name<input required minLength={3} maxLength={120} value={profileForm.fullName} onChange={event => setProfileForm(current => ({ ...current, fullName: event.target.value }))}/></label>
            <label>Role<input readOnly value={profile.position || profile.role || 'Front Desk'} /></label>
            <label>Personal email<input required type="email" autoComplete="email" maxLength={254} value={profileForm.personalEmail} onChange={event => setProfileForm(current => ({ ...current, personalEmail: event.target.value }))}/></label>
            <label>Nickname<input maxLength={80} value={profileForm.nickname} onChange={event => setProfileForm(current => ({ ...current, nickname: event.target.value }))}/></label>
          </div>
        </fieldset>
        {profileError && <p className="fd-profile-error" role="alert">{profileError}</p>}
        <footer><button type="button" className="fd-button" disabled={profileSaving} onClick={() => setProfileOpen(false)}>Cancel</button><button type="submit" className="fd-button primary" disabled={profileSaving}>{profileSaving ? 'Saving…' : 'Save changes'}</button></footer>
      </form>
    </dialog>
    <ConfirmSignOut open={signOutOpen} busy={signingOut} cancel={() => setSignOutOpen(false)} confirm={async () => { setSigningOut(true); try { await signOutDesk(); } catch { /* Local session is cleared even if server logout fails. */ } finally { navigate('/login', { replace: true }); } }} />
  </div>;
}
