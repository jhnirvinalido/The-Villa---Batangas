import { useCallback, useEffect, useRef, useState } from 'react';
import { LoaderCircle, Plus, X } from 'lucide-react';
import { createDeskQr, deskApi } from './frontDeskApi.mjs';
import { deskDate, peso } from './frontDeskModel.mjs';

export default function FrontDeskSettlement({ booking, open, onClose, onComplete, onPending }) {
  const dialog = useRef(null);
  const [timing, setTiming] = useState(booking.checkedIn ? 'check_out' : booking.paymentTiming || 'check_in');
  const [method, setMethod] = useState('cash');
  const [payer, setPayer] = useState(booking.guestName);
  const [cash, setCash] = useState('');
  const [charges, setCharges] = useState([]);
  const [draft, setDraft] = useState({ description: '', amount: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [qr, setQr] = useState(null);
  const due = Math.round((booking.balanceAmount + charges.reduce((sum, charge) => sum + charge.amount, 0)) * 100) / 100;
  const defer = timing === 'check_out' && !booking.checkedIn;

  useEffect(() => {
    const node = dialog.current;
    if (open && node && !node.open) node.showModal();
    if (!open && node?.open) node.close();
  }, [open]);

  const checkPayment = useCallback(async () => {
    if (!qr?.id) return;
    const result = await deskApi(`/front-desk/payments/${encodeURIComponent(qr.id)}/status`);
    const status = String(result.data?.payment?.status || '').toLowerCase();
    if (status === 'paid') {
      setQr(null); onPending(false);
      await onComplete(`Payment for ${booking.bookingCode} verified.`, result.data);
    } else if (['failed', 'expired', 'cancelled', 'amount_mismatch'].includes(status)) {
      setError(status === 'amount_mismatch' ? 'The payment amount requires administrator review. Do not collect a second payment.' : 'This QRPh payment did not complete. Check payment status before retrying.');
      if (status !== 'amount_mismatch') { setQr(null); onPending(false); }
    }
  }, [qr?.id, booking.bookingCode, onComplete, onPending]);

  useEffect(() => {
    if (!qr?.id) return;
    let stopped = false, running = false;
    const poll = async () => {
      if (running || stopped) return;
      running = true;
      try { await checkPayment(); } catch (failure) { if (!stopped) setError(failure.message); }
      finally { running = false; }
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => { stopped = true; clearInterval(timer); };
  }, [qr?.id, checkPayment]);

  async function submit(event) {
    event.preventDefault();
    if (busy || qr) return;
    if (!defer && (draft.description.trim() || draft.amount)) { setError('Add the extra charge or clear its fields before collecting payment.'); return; }
    setBusy(true); setError('');
    try {
      await deskApi(`/front-desk/bookings/${encodeURIComponent(booking.id)}/payment-timing`, { method: 'PUT', body: JSON.stringify({ payment_timing: timing }) });
      if (defer) {
        await deskApi(`/front-desk/bookings/${encodeURIComponent(booking.id)}/check-in`, { method: 'POST', body: JSON.stringify({ notes: 'Guest chose to pay the remaining balance at check-out.' }) });
        await onComplete(`${booking.guestName} checked in. Balance is due at check-out.`);
      } else if (method === 'cash') {
        const result = await deskApi(`/front-desk/bookings/${encodeURIComponent(booking.id)}/cash-settlement`, { method: 'POST', body: JSON.stringify({ payer_name: payer.trim(), payment_timing: timing, cash_tendered: Number(cash), other_charges: charges }) });
        await onComplete(`Cash payment recorded. Change to return: ${peso(result.data?.change_given ?? Math.max(Number(cash) - due, 0))}.`, result.data);
      } else {
        const result = await createDeskQr(booking, { payerName: payer.trim(), timing, charges });
        setQr(result); onPending(true);
      }
    } catch (failure) {
      setError(failure.message);
      if (failure.paymentIntentId) { setQr({ id: failure.paymentIntentId }); onPending(true); }
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="fd-dialog" onCancel={event => { event.preventDefault(); if (!busy) onClose(Boolean(qr)); }}>
    <header><div><span className="fd-eyebrow">Payment settlement</span><h2>{booking.bookingCode}</h2></div><button type="button" className="fd-icon-button" disabled={busy} onClick={() => onClose(Boolean(qr))} aria-label="Close payment settlement"><X size={20} /></button></header>
    <form className="fd-stack" onSubmit={submit}>
      <div className="fd-payment-summary"><strong>{booking.guestName}</strong><span>{booking.villaName} · {deskDate(booking.checkIn)} – {deskDate(booking.checkOut)}</span><div><span>Room balance</span><strong>{peso(booking.balanceAmount)}</strong></div></div>
      {error && <div className="fd-notice error" role="alert">{error}</div>}
      <fieldset disabled={busy || Boolean(qr)}>
        <legend>Payment timing</legend>
        <div className="fd-segments">{(booking.checkedIn ? ['check_out'] : ['check_in', 'check_out']).map(value => <button type="button" key={value} aria-pressed={timing === value} onClick={() => setTiming(value)}>{value === 'check_in' ? 'Pay at check-in' : 'Pay at check-out'}</button>)}</div>
      </fieldset>
      {defer ? <p className="fd-notice">The guest will be checked in now. The remaining balance must be settled before departure.</p> : <>
        <fieldset disabled={busy || Boolean(qr)}>
          <legend>Additional charges (optional)</legend>
          {charges.map((charge, index) => <div className="fd-charge" key={index}><span>{charge.description}</span><strong>{peso(charge.amount)}</strong><button type="button" className="fd-icon-button" onClick={() => setCharges(value => value.filter((_, item) => item !== index))} aria-label={`Remove ${charge.description}`}><X size={15} /></button></div>)}
          <div className="fd-charge-fields"><input aria-label="Charge description" placeholder="Description" maxLength="160" value={draft.description} onChange={event => setDraft(value => ({ ...value, description: event.target.value }))} /><input aria-label="Charge amount" type="number" min="0.01" step="0.01" placeholder="PHP" value={draft.amount} onChange={event => setDraft(value => ({ ...value, amount: event.target.value }))} /><button type="button" className="fd-button" disabled={draft.description.trim().length < 2 || Number(draft.amount) <= 0} onClick={() => { setCharges(value => [...value, { description: draft.description.trim(), amount: Math.round(Number(draft.amount) * 100) / 100 }]); setDraft({ description: '', amount: '' }); }}><Plus size={15} /> Add</button></div>
        </fieldset>
        <fieldset disabled={busy || Boolean(qr)}><legend>Collect {peso(due)}</legend>
          <div className="fd-segments">{['cash', 'qrph'].map(value => <button type="button" key={value} aria-pressed={method === value} onClick={() => setMethod(value)}>{value === 'cash' ? 'Cash' : 'QRPh'}</button>)}</div>
          <label>Payer name<input required minLength="2" maxLength="160" value={payer} onChange={event => setPayer(event.target.value)} /></label>
          {method === 'cash' && <label>Cash received<input required type="number" min={due} step="0.01" value={cash} onChange={event => setCash(event.target.value)} />{Number(cash) >= due && <small>Change: {peso(Number(cash) - due)}</small>}</label>}
        </fieldset>
      </>}
      {qr && <div className="fd-qr" role="status">{qr.image && <img src={qr.image} alt="Scan this QRPh code to pay" />}<strong>Waiting for payment verification</strong><span>The booking balance updates after payment is confirmed.</span><button type="button" className="fd-button" onClick={() => checkPayment().catch(failure => setError(failure.message))}>Check payment status</button></div>}
      <footer><button type="button" className="fd-button" disabled={busy} onClick={() => onClose(Boolean(qr))}>{qr ? 'Continue working' : 'Cancel'}</button><button type="submit" className="fd-button primary" disabled={busy || Boolean(qr) || (!defer && (!payer.trim() || (method === 'cash' && Number(cash) < due)))}>{busy && <LoaderCircle size={16} className="fd-spin" />}{defer ? 'Confirm check-in · pay at check-out' : method === 'cash' ? 'Confirm cash payment' : 'Generate QRPh code'}</button></footer>
    </form>
  </dialog>;
}
