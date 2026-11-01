import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, LoaderCircle, RefreshCw } from 'lucide-react';
import { deskApi } from './frontDeskApi.mjs';
import { dateKey } from './taskFlow.mjs';
import { deskDate, minimumVillaCount, peso } from './frontDeskModel.mjs';

const emptyGuest = { first_name: '', last_name: '', email: '', phone: '', notes: '' };

export default function FrontDeskWalkIn({ active, onChanged }) {
  const [day, setDay] = useState(dateKey);
  const [guests, setGuests] = useState('1');
  const [guest, setGuest] = useState(emptyGuest);
  const [villas, setVillas] = useState([]);
  const [availabilityCheckedAt, setAvailabilityCheckedAt] = useState('');
  const [selected, setSelected] = useState([]);
  const [method, setMethod] = useState('cash');
  const [cash, setCash] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState(null);
  const required = minimumVillaCount(guests, villas);
  const chosen = villas.filter(villa => selected.includes(villa.villa_id));
  const total = chosen.reduce((sum, villa) => sum + Number(villa.price || 0), 0);
  const capacity = chosen.reduce((sum, villa) => sum + Number(villa.capacity || 0), 0);
  const valid = selected.length === required && chosen.length === selected.length && capacity >= Number(guests) && total > 0;

  const refresh = useCallback(async signal => {
    if (!day || Number(guests) < 1 || Number(guests) > 32) return;
    setLoading(true);
    setSelected([]);
    setVillas([]);
    setAvailabilityCheckedAt('');
    try {
      const result = await deskApi(`/front-desk/availability?check_in_date=${day}&guest_count=${encodeURIComponent(guests)}`, { signal });
      if (!signal?.aborted) {
        setVillas(result.villas || []);
        setAvailabilityCheckedAt(result.updated_at || '');
        setError('');
      }
    } catch (failure) {
      if (failure.name !== 'AbortError') setError(failure.message);
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [day, guests]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = setTimeout(() => refresh(controller.signal), 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [active, refresh]);

  useEffect(() => {
    if (!pending) return;
    let stopped = false, busy = false;
    const poll = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await deskApi(`/front-desk/walk-ins/${encodeURIComponent(pending.id)}/sync-payment`, { method: 'POST' });
        if (stopped) return;
        if (['Confirmed', 'Checked In'].includes(result.data?.booking_status) && Number(result.data?.amount_paid) > 0) {
          setPending(null);
          setNotice(`Walk-in ${result.data.booking_code} is paid and confirmed.`);
          await onChanged();
          if (active) await refresh();
        } else if (['Cancelled', 'Expired'].includes(result.data?.booking_status)) {
          setPending(null);
          setError('The unpaid reservation expired. Check availability before creating a new walk-in.');
          await onChanged();
        }
      } catch (failure) { if (!stopped) setError(failure.message); }
      finally { busy = false; }
    };
    const timer = setInterval(poll, 10000);
    return () => { stopped = true; clearInterval(timer); };
  }, [pending, active, onChanged, refresh]);

  async function submit(event) {
    event.preventDefault();
    if (!valid || saving || pending) return;
    setSaving(true); setError(''); setNotice('');
    try {
      const result = await deskApi('/front-desk/walk-ins', { method: 'POST', body: JSON.stringify({
        ...Object.fromEntries(Object.entries(guest).map(([key, value]) => [key, value.trim()])),
        check_in_date: day, guest_count: Number(guests), villa_ids: selected,
        payment_choice: 'full', payment_method: method,
        ...(method === 'cash' ? { cash_tendered: Number(cash) } : {}),
      }) });
      if (method === 'cash') {
        if (!result.data?.booking?.id) throw new Error('The booking was not returned. Refresh the booking list before retrying.');
        setNotice(`Walk-in ${result.data.booking.booking_code} confirmed. Change to return: ${peso(result.data.change_given)}.`);
      } else {
        if (!result.booking_id || !result.checkout_url) throw new Error('The checkout could not be opened. Refresh bookings before retrying.');
        setPending({ id: result.booking_id, code: result.booking_code, url: result.checkout_url });
      }
      setGuest(emptyGuest); setCash('');
      await onChanged();
      await refresh();
    } catch (failure) { setError(failure.message); }
    finally { setSaving(false); }
  }

  return <div className="fd-stack">
    {error && <div className="fd-notice error" role="alert">{error}</div>}
    {notice && <div className="fd-notice success" role="status"><CheckCircle2 size={18} />{notice}</div>}
    {pending && <section className="fd-panel fd-pending-payment"><h2>Waiting for QRPh payment</h2><p>Walk-in {pending.code} is reserved temporarily. It becomes confirmed after payment verification.</p><a className="fd-button primary" href={pending.url} target="_blank" rel="noreferrer">Open secure payment checkout</a><small>Payment status updates automatically. You can continue viewing other sections.</small></section>}
    <form className="fd-panel fd-stack" onSubmit={submit}>
      <fieldset disabled={saving || Boolean(pending)}>
        <legend>1. Guest and stay</legend>
        <div className="fd-form-grid">
          <label>Arrival date<input type="date" required min={dateKey()} value={day} onChange={event => setDay(event.target.value)} /></label>
          <label>Number of guests<input type="number" min="1" max="32" required value={guests} onChange={event => setGuests(event.target.value)} /></label>
          {['first_name', 'last_name', 'email', 'phone'].map(key => <label key={key}>{({ first_name: 'First name', last_name: 'Last name', email: 'Email address', phone: 'Mobile number' })[key]}<input required type={key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text'} maxLength={key === 'email' ? 254 : 100} value={guest[key]} onChange={event => setGuest(value => ({ ...value, [key]: event.target.value }))} /></label>)}
        </div>
      </fieldset>
      <fieldset disabled={saving || Boolean(pending)}>
        <legend>2. Choose available villas</legend>
        <div className="fd-section-line"><div><p>{Number.isFinite(required) ? `Select ${required} villa${required === 1 ? '' : 's'} for ${guests} guest${guests === '1' ? '' : 's'}.` : 'No available combination can accommodate this group.'} · {deskDate(day)}</p>{availabilityCheckedAt && <small className="fd-calendar-check">Availability checked {new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Manila' }).format(new Date(availabilityCheckedAt))} · The Villa calendar</small>}</div><button type="button" className="fd-button" disabled={loading} onClick={() => refresh()}><RefreshCw size={15} /> Refresh availability</button></div>
        {loading ? <p role="status">Checking availability…</p> : <div className="fd-villa-grid">{villas.map(villa => <button type="button" key={villa.villa_id} className={`fd-villa ${selected.includes(villa.villa_id) ? 'selected' : ''}`} disabled={!villa.available || (!selected.includes(villa.villa_id) && selected.length >= required)} aria-pressed={selected.includes(villa.villa_id)} onClick={() => setSelected(value => value.includes(villa.villa_id) ? value.filter(id => id !== villa.villa_id) : [...value, villa.villa_id])}>
          {villa.image && <img src={villa.image} alt="" />}<strong>{villa.villa_name}</strong><span>Up to {villa.capacity} guests · {peso(villa.price)}</span><small>{villa.available ? selected.includes(villa.villa_id) ? 'Selected' : 'Available' : villa.reason || 'Unavailable'}</small>
        </button>)}</div>}
      </fieldset>
      <fieldset disabled={saving || Boolean(pending)}>
        <legend>3. Collect full payment</legend>
        <div className="fd-segments" role="group" aria-label="Walk-in payment method">{['cash', 'qrph'].map(value => <button type="button" key={value} aria-pressed={method === value} onClick={() => setMethod(value)}>{value === 'cash' ? 'Cash' : 'QRPh'}</button>)}</div>
        <div className="fd-form-grid"><label>Booking total<strong className="fd-amount">{peso(total)}</strong></label>{method === 'cash' && <label>Cash received<input type="number" required min={total} step="0.01" value={cash} onChange={event => setCash(event.target.value)} />{cash && Number(cash) >= total && <small>Change: {peso(Number(cash) - total)}</small>}</label>}</div>
        <label>Guest notes (optional)<textarea maxLength="1000" rows="2" value={guest.notes} onChange={event => setGuest(value => ({ ...value, notes: event.target.value }))} /></label>
      </fieldset>
      <button className="fd-button primary" type="submit" disabled={saving || loading || !valid || Boolean(pending)}>{saving && <LoaderCircle size={16} className="fd-spin" />}{saving ? 'Saving reservation…' : method === 'cash' ? 'Confirm walk-in and record cash' : 'Create secure QRPh checkout'}</button>
    </form>
  </div>;
}
