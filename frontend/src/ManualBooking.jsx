import { AlertMessage } from "./SystemFeedback";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useLiveUpdates from "./useLiveUpdates";
import { formatUserFacingMessage, getUserFacingError } from "./errorMessages.mjs";
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardCopy,
  CreditCard,
  ExternalLink,
  LoaderCircle,
  MessageCircle,
  Plus,
  ShieldCheck,
  Users,
  QrCode,
  ArrowRight,
  CalendarCheck2,
  LockKeyhole,
  FileCheck2,
  AlertCircle,
  X,
} from "lucide-react";
import "./ManualBooking.css";

const EMPTY_FORM = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  check_in_date: "",
  guest_count: "1",
  notes: "",
  payment_choice: "half",
  payment_method: "qrph",
};

function requiredVillaCount(guests, villas) {
  const wanted = Number(guests);
  if (!Number.isInteger(wanted) || wanted < 1 || wanted > 32) return Infinity;
  const sizes = villas.filter((villa) => villa.available === true)
    .map((villa) => Number(villa.capacity || 0)).filter((size) => size > 0)
    .sort((a, b) => b - a);
  let seats = 0;
  for (let index = 0; index < sizes.length; index += 1) {
    seats += sizes[index];
    if (seats >= wanted) return index + 1;
  }
  return Infinity;
}

function canAddVilla(villa, villas, selectedIds, guests, required) {
  if (!villa || villa.available !== true) return false;
  if (selectedIds.includes(villa.villa_id)) return true; // Selected rooms remain removable.
  if (!Number.isFinite(required) || selectedIds.length >= required) return false;
  const selected = villas.filter((item) => selectedIds.includes(item.villa_id));
  const used = selected.reduce((sum, item) => sum + Number(item.capacity || 0), 0);
  if (used >= Number(guests)) return false;
  const seatsAfterAdding = used + Number(villa.capacity || 0);
  const openSlots = required - selectedIds.length - 1;
  const bestRemaining = villas.filter((item) => item.available === true &&
    !selectedIds.includes(item.villa_id) && item.villa_id !== villa.villa_id)
    .map((item) => Number(item.capacity || 0))
    .sort((a, b) => b - a).slice(0, openSlots)
    .reduce((sum, count) => sum + count, 0);
  return seatsAfterAdding + bestRemaining >= Number(guests);
}

function fixSelectedVillas(ids, guests, villas) {
  const count = requiredVillaCount(guests, villas);
  if (!Number.isFinite(count)) return [];
  return ids.reduce((next, id) => {
    const villa = villas.find((item) => item.villa_id === id);
    return canAddVilla(villa, villas, next, guests, count) ? [...next, id] : next;
  }, []);
}

function peso(value) {
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function manilaToday() {
  // All reservation dates are interpreted in the property's Asia/Manila timezone.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

function nextCalendarDate(date) {
  const next = new Date(`${date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString().slice(0, 10);
}

function formatDate(date) {
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-PH", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-PH", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Manila",
  }).format(new Date(value));
}

const PENDING_MANUAL_STORAGE = "theVillaAdminManualPayment";

function paymentIsVerified(payment) {
  return Number(payment?.amount_paid || 0) > 0 &&
    ["confirmed", "checked in", "completed"].includes(
      String(payment?.booking_status || "").trim().toLowerCase()
    );
}

function readManualPaymentSession() {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(PENDING_MANUAL_STORAGE) || "null");
    if (!saved || !saved.savedAt || Date.now() - saved.savedAt > 72 * 3600000) return null;
    if (!saved.bookingResult?.booking_id || !saved.bookingResult?.checkout_url) return null;
    return saved;
  } catch { return null; }
}

export default function ManualBooking({ apiRequest, onViewBookings, onBookingCreated }) {
  const initial = useMemo(readManualPaymentSession, []);
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, ...initial?.form, payment_method: "qrph" }));
  const [selectedIds, setSelectedIds] = useState(() => initial?.selectedIds || []);
  const [availability, setAvailability] = useState(() => initial?.availability || null);
  const [airbnbCheck, setAirbnbCheck] = useState({ check_in_date: "", guest_count: "1" });
  const [airbnbModalOpen, setAirbnbModalOpen] = useState(false);
  const [airbnbAvailability, setAirbnbAvailability] = useState(null);
  const [selectedAirbnbVillaIds, setSelectedAirbnbVillaIds] = useState([]);
  const [airbnbStays, setAirbnbStays] = useState([]);
  const [airbnbStaysLoading, setAirbnbStaysLoading] = useState(true);
  const [airbnbChecking, setAirbnbChecking] = useState(false);
  const [airbnbSaving, setAirbnbSaving] = useState("");
  const [airbnbError, setAirbnbError] = useState("");
  const [airbnbNotice, setAirbnbNotice] = useState("");
  const [loadingVillas, setLoadingVillas] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checkingPayment, setCheckingPayment] = useState(Boolean(initial));
  const [bookingResult, setBookingResult] = useState(() => initial?.bookingResult || null);
  const [latestPayment, setLatestPayment] = useState(() => initial?.latestPayment || null);
  const livePaymentRefresh = useRef(null);
  useLiveUpdates({
    domains: ["bookings", "payments"],
    enabled: Boolean(bookingResult?.booking_id),
    onChange: () => livePaymentRefresh.current?.(),
  });
  const [paymentSyncError, setPaymentSyncError] = useState("");
  // A paid booking displays a brief processing screen and then an Okay confirmation.
  // A reload restores this state from sessionStorage until the administrator clicks Okay.
  const [completionStage, setCompletionStage] = useState(() =>
    paymentIsVerified(initial?.latestPayment) ? "processing" : "idle"
  );
  const notifyRef = useRef(onBookingCreated);
  const requestRef = useRef(apiRequest);
  useEffect(() => { notifyRef.current = onBookingCreated; requestRef.current = apiRequest; }, [onBookingCreated, apiRequest]);
  const [error, setError] = useState("");
  const [copyNotice, setCopyNotice] = useState("");

  const refreshAirbnbStays = useCallback(async () => {
    setAirbnbStaysLoading(true);
    try {
      const response = await requestRef.current("/admin/manual-bookings/airbnb-stays");
      setAirbnbStays(response?.data || []);
      setAirbnbError("");
    } catch (requestError) {
      setAirbnbError(getUserFacingError(requestError, "Airbnb stay records could not be loaded."));
    } finally {
      setAirbnbStaysLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshAirbnbStays();
  }, [refreshAirbnbStays]);

  useEffect(() => {
    if (!airbnbModalOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setAirbnbModalOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [airbnbModalOpen]);

  const setField = (field, value) => {
    setForm((previous) => ({ ...previous, [field]: value }));
    setError("");
  };

  const setNameField = (field, value) => {
    if (/\p{N}/u.test(value)) {
      setError("Names must not contain numbers.");
      return;
    }
    setField(field, value);
  };

  const setAirbnbCheckField = (field, value) => {
    setAirbnbCheck((current) => ({ ...current, [field]: value }));
    setAirbnbAvailability(null);
    setSelectedAirbnbVillaIds([]);
    setAirbnbError("");
    setAirbnbNotice("");
  };

  async function checkAirbnbAvailability(event) {
    event.preventDefault();
    setAirbnbError("");
    setAirbnbNotice("");
    setAirbnbAvailability(null);
    setSelectedAirbnbVillaIds([]);
    const guests = Number(airbnbCheck.guest_count);
    if (!airbnbCheck.check_in_date ||
        airbnbCheck.check_in_date < manilaToday() ||
        !Number.isInteger(guests) || guests < 1 || guests > 32) {
      setAirbnbError("Enter a valid future check-in date and 1–32 guests.");
      return;
    }
    const checkOutDate = nextCalendarDate(airbnbCheck.check_in_date);
    setAirbnbChecking(true);
    try {
      const params = new URLSearchParams({
        check_in_date: airbnbCheck.check_in_date,
        check_out_date: checkOutDate,
        guest_count: String(guests),
      });
      setAirbnbAvailability(await requestRef.current(
        `/admin/manual-bookings/airbnb-availability?${params.toString()}`
      ));
    } catch (requestError) {
      setAirbnbError(getUserFacingError(requestError, "Unable to check availability for this stay."));
    } finally {
      setAirbnbChecking(false);
    }
  }

  async function createAirbnbHold() {
    setAirbnbError("");
    setAirbnbNotice("");
    const selectedVillas = airbnbAvailability?.villas?.filter(villa =>
      selectedAirbnbVillaIds.includes(villa.villa_id)
    ) || [];
    const selectedCapacity = selectedVillas.reduce((total, villa) => total + Number(villa.capacity || 0), 0);
    if (!selectedVillas.length || selectedCapacity < Number(airbnbCheck.guest_count)) {
      setAirbnbError("Select available villa(s) with enough combined guest capacity.");
      return;
    }
    setAirbnbSaving("create");
    try {
      const result = await requestRef.current("/admin/manual-bookings/airbnb-stays", {
        method: "POST",
        body: JSON.stringify({
          check_in_date: airbnbCheck.check_in_date,
          check_out_date: nextCalendarDate(airbnbCheck.check_in_date),
          guest_count: Number(airbnbCheck.guest_count),
          villa_ids: selectedAirbnbVillaIds,
        }),
      });
      setAirbnbNotice(result?.message || "10-minute Airbnb availability hold created.");
      setAirbnbAvailability(null);
      setSelectedAirbnbVillaIds([]);
      await refreshAirbnbStays();
    } catch (requestError) {
      setAirbnbError(getUserFacingError(requestError, "The Airbnb availability hold could not be created."));
    } finally {
      setAirbnbSaving("");
    }
  }

  async function updateAirbnbStay(stay, action) {
    if (action === "release" &&
        !window.confirm("Release these dates from The Villa calendar? Do this only if the Airbnb request was not accepted or the Airbnb stay was cancelled.")) {
      return;
    }
    setAirbnbError("");
    setAirbnbNotice("");
    setAirbnbSaving(`${stay.id}:${action}`);
    try {
      const result = await requestRef.current(
        `/admin/manual-bookings/airbnb-stays/${encodeURIComponent(stay.id)}/${action}`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setAirbnbNotice(result?.message || "Airbnb stay updated.");
      await refreshAirbnbStays();
    } catch (requestError) {
      setAirbnbError(getUserFacingError(requestError, "The Airbnb stay could not be updated."));
    } finally {
      setAirbnbSaving("");
    }
  }

  const selectedAirbnbCapacity = (airbnbAvailability?.villas || [])
    .filter(villa => selectedAirbnbVillaIds.includes(villa.villa_id))
    .reduce((total, villa) => total + Number(villa.capacity || 0), 0);

  useEffect(() => {
    // The result view retains the villa snapshot during PayMongo verification.
    if (bookingResult?.booking_id) return undefined;
    if (!form.check_in_date) {
      setAvailability(null);
      setSelectedIds([]);
      return undefined;
    }
    let active = true;
    setLoadingVillas(true);
    setAvailability(null);
    setSelectedIds([]);
    requestRef.current(`/admin/manual-bookings/availability?check_in_date=${encodeURIComponent(form.check_in_date)}`)
      .then((response) => {
        if (active) setAvailability(response);
      })
      .catch((requestError) => {
        if (active) setError(getUserFacingError(requestError, "Unable to check villa availability."));
      })
      .finally(() => {
        if (active) setLoadingVillas(false);
      });
    return () => { active = false; };
  }, [form.check_in_date, bookingResult?.booking_id]);

  const villas = useMemo(() => availability?.villas || [], [availability]);
  const selectedVillas = useMemo(
    () => villas.filter((villa) => selectedIds.includes(villa.villa_id)),
    [villas, selectedIds],
  );
  const guestCount = Number(form.guest_count);
  const minimumVillas = requiredVillaCount(guestCount, villas);
  const enoughRooms = Number.isFinite(minimumVillas);
  const villaSelectionComplete = selectedVillas.length === minimumVillas;
  const capacity = selectedVillas.reduce((total, villa) => total + Number(villa.capacity || 0), 0);
  const total = selectedVillas.reduce((amount, villa) => amount + Number(villa.price || 0), 0);
  const due = form.payment_choice === "full" ? total : Math.round(total * 50) / 100;
  const remaining = Math.max(0, total - due);
  const validSelection = enoughRooms && guestCount >= 1 && Number.isInteger(guestCount) && guestCount <= 32 &&
    villaSelectionComplete && selectedVillas.length === selectedIds.length &&
    capacity >= guestCount && selectedVillas.every((villa) => villa.available);

  function toggleVilla(id) {
    const villa = villas.find((item) => item.villa_id === id);
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (!canAddVilla(villa, villas, current, guestCount, minimumVillas)) return current;
      return [...current, id];
    });
  }

  useEffect(() => {
    setSelectedIds((current) => {
      const next = fixSelectedVillas(current, guestCount, villas);
      return current.length === next.length && current.every((id, i) => id === next[i]) ? current : next;
    });
  }, [guestCount, villas]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (/\p{N}/u.test(`${form.first_name} ${form.last_name}`)) {
      setError("Names must not contain numbers.");
      return;
    }
    if (!form.check_in_date || form.check_in_date < manilaToday()) {
      setError("Select today or a future check-in date.");
      return;
    }
    if (!validSelection || !availability || loadingVillas) {
      setError(enoughRooms
        ? `Select ${minimumVillas} ${minimumVillas === 1 ? "villa" : "villas"} for ${guestCount} guests.`
        : "Not enough villas are available for this date.");
      return;
    }
    const phoneDigits = form.phone.replace(/\D/g, "");
    if (!/^(?:09\d{9}|639\d{9}|9\d{9})$/.test(phoneDigits)) {
      setError("Enter a valid Philippine mobile number, such as 09123456789.");
      return;
    }
    setSaving(true);
    try {
      const result = await apiRequest("/admin/manual-bookings", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          email: form.email.trim().toLowerCase(),
          phone: form.phone.trim(),
          guest_count: guestCount,
          villa_ids: selectedIds,
          notes: form.notes.trim() || null,
        }),
      });
      if (!result?.booking_id || !result?.checkout_url) {
        throw new Error("Payment setup did not return a complete checkout link. The booking has not been confirmed.");
      }
      setBookingResult(result);
      setLatestPayment(result.booking || null);
      try {
        window.sessionStorage.setItem(PENDING_MANUAL_STORAGE, JSON.stringify({
          savedAt: Date.now(), bookingResult: result, latestPayment: result.booking,
          form, selectedIds, availability,
        }));
      } catch { /* Auto-sync works without sessionStorage. */ }
    } catch (requestError) {
      setError(getUserFacingError(requestError, "Could not create manual booking."));
    } finally {
      setSaving(false);
    }
  }

  // Automatic server-side PayMongo verification while this page is open.
  // No staff "Check payment" button, and no manual Paid toggle.
  useEffect(() => {
    const bookingId = bookingResult?.booking_id;
    if (!bookingId) return undefined;
    let active = true;
    let busy = false;
    let timer;
    async function sync() {
      if (!active || busy) return;
      busy = true;
      setCheckingPayment(true);
      try {
        const response = await requestRef.current(`/admin/manual-bookings/${bookingId}/sync-payment`, {
          method: "POST",
        });
        if (!active) return;
        setLatestPayment(response?.data || null);
        setPaymentSyncError("");
        try {
          const saved = readManualPaymentSession();
          if (saved?.bookingResult?.booking_id === bookingId) {
            window.sessionStorage.setItem(PENDING_MANUAL_STORAGE,
              JSON.stringify({ ...saved, latestPayment: response?.data || null }));
          }
        } catch { /* Storage is optional. */ }
        const updated = response?.data;
        const confirmed = paymentIsVerified(updated);
        if (confirmed) {
          setCompletionStage((current) => current === "idle" ? "processing" : current);
          notifyRef.current?.();
          return;  // Final state — stop polling after verification.
        }
        if (["expired", "cancelled"].includes(String(updated?.booking_status || "").toLowerCase())) return;
      } catch (failure) {
        if (!active) return;
        setPaymentSyncError(getUserFacingError(failure, "Payment verification could not complete. It will retry automatically."));
      } finally {
        busy = false;
        if (active) setCheckingPayment(false);
      }
      if (active) timer = window.setTimeout(sync, document.hidden ? 60000 : 30000);
    }

    const onVisible = () => {
      if (document.hidden) return;
      window.clearTimeout(timer);
      if (!busy) sync();
    };
    livePaymentRefresh.current = sync;
    sync();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      active = false;
      if (livePaymentRefresh.current === sync) livePaymentRefresh.current = null;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [bookingResult?.booking_id]);

  useEffect(() => {
    if (completionStage !== "processing") return undefined;
    const timer = window.setTimeout(() => setCompletionStage("success"), 1050);
    return () => window.clearTimeout(timer);
  }, [completionStage]);

  async function copy(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyNotice(`${label} copied`);
    } catch {
      setCopyNotice("");
      setError("Copy failed. Select and copy the payment link or message manually.");
    }
  }

  function startNew() {
    setCompletionStage("idle");
    try { window.sessionStorage.removeItem(PENDING_MANUAL_STORAGE); } catch { /* no-op */ }
    setPaymentSyncError("");
    setCheckingPayment(false);
    setBookingResult(null);
    setLatestPayment(null);
    setSelectedIds([]);
    setAvailability(null);
    setForm({ ...EMPTY_FORM });
    setError("");
    setCopyNotice("");
  }

  const confirmed = paymentIsVerified(latestPayment);
  const paymentStatus = latestPayment?.payment_status || "Unpaid";
  const paymentAmount = Number(latestPayment?.amount_paid || 0);
  const isPartialPayment = String(paymentStatus).toLowerCase() === "partial";
  const messengerText = bookingResult
    ? `Hello ${form.first_name.trim()}! Your The Villa booking (${bookingResult.booking_code}) for ${formatDate(form.check_in_date)} at 3:00 PM is awaiting ${form.payment_choice === "half" ? "a 50% downpayment" : "full payment"} of ${peso(bookingResult.payment_due)}.\n\nPay securely here: ${bookingResult.checkout_url}\n\nYour booking will be saved and confirmed only after the payment is verified. Please complete checkout before the payment link expires. Villa availability is checked again before saving.`
    : "";

  return (
    <div className="manual-booking-page" id="manual-booking-top">
      {/* Tailwind utility classes are included for Tailwind projects; equivalent CSS
          is supplied so the screen also works in the existing plain-CSS dashboard. */}
      {completionStage !== "idle" && confirmed && (
        <div
          className="manual-completion-screen fixed inset-0 z-[9999] flex items-center justify-center bg-stone-950/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="manual-completion-title"
        >
          <div className="manual-completion-card w-full max-w-md rounded-3xl border border-stone-200 bg-white px-7 py-10 text-center shadow-2xl sm:px-10">
            {completionStage === "processing" ? (
              <>
                <div className="manual-processing-icon mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-amber-50">
                  <span className="manual-processing-ring h-12 w-12 animate-spin rounded-full border-4 border-stone-200 border-t-amber-700" aria-hidden="true" />
                </div>
                <div className="manual-completion-eyebrow">PAYMENT VERIFIED</div>
                <h2 id="manual-completion-title" className="mt-3 text-2xl font-bold tracking-tight text-stone-900">Finalizing reservation</h2>
                <p className="manual-completion-description mt-3 text-sm leading-6 text-stone-500">Your guest’s payment has been received. Updating the booking details…</p>
                <div className="manual-progress-track mt-7 h-1.5 overflow-hidden rounded-full bg-stone-100"><span /></div>
              </>
            ) : (
              <>
                <div className="manual-complete-icon mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700"><CheckCircle2 size={42} strokeWidth={1.8} /></div>
                <div className="manual-completion-eyebrow">PAYMENT RECEIVED</div>
                <h2 id="manual-completion-title" className="mt-3 text-2xl font-bold tracking-tight text-stone-900">
                  {isPartialPayment ? "Downpayment received" : "Payment completed"}
                </h2>
                <p className="manual-completion-description mt-3 text-sm leading-6 text-stone-500">Reservation confirmed successfully.</p>
                <div className="manual-completion-receipt mt-7 rounded-2xl border border-stone-200 bg-stone-50 px-5 py-4">
                  <div><span>Reference</span><strong>{bookingResult?.booking_code || "—"}</strong></div>
                  <div><span>Amount received</span><strong>{peso(paymentAmount)}</strong></div>
                  <div><span>Payment status</span><strong className="manual-green">{isPartialPayment ? "Partial" : "Paid"}</strong></div>
                  {isPartialPayment && <div><span>Remaining balance</span><strong>{peso(latestPayment?.balance_amount)}</strong></div>}
                </div>
                <button type="button" className="manual-btn-primary manual-completion-okay mt-7 w-full rounded-xl px-6 py-3 font-semibold" onClick={startNew} autoFocus>
                  Okay <ArrowRight size={17} />
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <header className="manual-page-header">
        <div className="manual-header-identity">
          <div className="manual-header-mark"><CalendarCheck2 size={24} strokeWidth={1.8} /></div>
          <div>
            <div className="manual-header-kicker">RESERVATION MANAGEMENT</div>
            <h1>Manual Booking</h1> 
          </div>
        </div>
        <button type="button" className="manual-btn-primary" onClick={() => setAirbnbModalOpen(true)}>
          <CalendarDays size={17} /> Check Airbnb dates
        </button>
      </header>

      {airbnbModalOpen && (
      <div className="manual-airbnb-modal-backdrop" onClick={(event) => {
        if (event.target === event.currentTarget) setAirbnbModalOpen(false);
      }}>
      <section className="manual-panel manual-airbnb-check" role="dialog" aria-modal="true" aria-labelledby="airbnb-check-title">
        <div className="manual-panel-heading">
          <div className="manual-panel-icon"><CalendarDays size={19} /></div>
          <div>
            <h2 id="airbnb-check-title">Check an Airbnb request</h2>
            <p>Check The Villa’s calendar before accepting the request on Airbnb. No Airbnb calendar is connected.</p>
          </div>
          <button type="button" className="manual-airbnb-modal-close" aria-label="Close Airbnb availability" onClick={() => setAirbnbModalOpen(false)}>
            <X size={19} />
          </button>
        </div>
        <form className="manual-airbnb-check-form" onSubmit={checkAirbnbAvailability}>
          <label className="manual-field">Check-in (3:00 PM)
            <input required type="date" min={manilaToday()} value={airbnbCheck.check_in_date}
              onChange={(event) => setAirbnbCheckField("check_in_date", event.target.value)} />
          </label>
          <label className="manual-field">Guests
            <input required type="number" min="1" max="32" step="1" value={airbnbCheck.guest_count}
              onChange={(event) => setAirbnbCheckField("guest_count", event.target.value)} />
          </label>
          <button type="submit" className="manual-btn-primary" disabled={airbnbChecking}>
            {airbnbChecking ? <><LoaderCircle size={16} className="manual-spin" /> Checking…</> : "Check availability"}
          </button>
        </form>
        <p className="manual-airbnb-note">Standard stay: check in at 3:00 PM and check out at 12:00 PM the next day (21 hours).</p>
        {airbnbError && <AlertMessage message={airbnbError} />}
        {airbnbNotice && <AlertMessage message={airbnbNotice} type="success" />}
        {airbnbAvailability && (
          <div className={`manual-airbnb-result ${airbnbAvailability.available ? "available" : "unavailable"}`} role="status" aria-live="polite">
            <strong>
              {airbnbAvailability.available
                ? `${airbnbAvailability.total_available_capacity} guest spaces available`
                : "No available villa combination for this stay"}
            </strong>
            <span>{formatDate(airbnbAvailability.check_in_date)} at 3:00 PM – {formatDate(airbnbAvailability.check_out_date)} at 12:00 PM · 21 hours</span>
            <span>Availability checked {formatDateTime(airbnbAvailability.updated_at)} · The Villa calendar</span>
            <ul>
              {airbnbAvailability.villas.map((villa) => (
                <li key={villa.villa_id}>
                  <label className="manual-airbnb-villa-select">
                    <input
                      type="checkbox"
                      disabled={!villa.available || !airbnbAvailability.available || !!airbnbSaving}
                      checked={selectedAirbnbVillaIds.includes(villa.villa_id)}
                      onChange={() => setSelectedAirbnbVillaIds(current =>
                        current.includes(villa.villa_id)
                          ? current.filter(id => id !== villa.villa_id)
                          : [...current, villa.villa_id]
                      )}
                    />
                    <span>{villa.villa_name} · up to {villa.capacity} guests</span>
                  </label>
                  <strong>{villa.reason}</strong>
                </li>
              ))}
            </ul>
            {airbnbAvailability.available && (
              <div className="manual-airbnb-hold-action">
                <span>Selected capacity: {selectedAirbnbCapacity} / {airbnbAvailability.guest_count} guests</span>
                <button
                  type="button"
                  className="manual-btn-primary"
                  disabled={!!airbnbSaving || selectedAirbnbCapacity < airbnbAvailability.guest_count}
                  onClick={createAirbnbHold}
                >
                  {airbnbSaving === "create" ? <><LoaderCircle size={16} className="manual-spin" /> Holding dates…</> : "Hold selected dates for 10 minutes"}
                </button>
              </div>
            )}
          </div>
        )}
        <p className="manual-airbnb-note">Select the villas and create a 10-minute hold before accepting on Airbnb. After Airbnb accepts the request, confirm it below so the dates remain blocked. Holds expire automatically; release dates only if the Airbnb request was not accepted or the stay was cancelled. This uses The Villa’s calendar only—Airbnb requests, guest details, reviews, and calendar updates are not imported. Do not use the direct Manual Booking form for Airbnb stays because it creates a PayMongo checkout.</p>
        <section className="manual-airbnb-stays" aria-labelledby="manual-airbnb-stays-title">
          <div className="manual-airbnb-stays-heading">
            <h3 id="manual-airbnb-stays-title">Airbnb holds and stays</h3>
            <button type="button" className="manual-btn-outline" onClick={refreshAirbnbStays} disabled={airbnbStaysLoading || !!airbnbSaving}>
              {airbnbStaysLoading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
          {airbnbStaysLoading ? <p>Loading Airbnb stay records…</p> : airbnbStays.length ? (
            <ul className="manual-airbnb-stay-list">
              {airbnbStays.map(stay => (
                <li key={stay.id}>
                  <div className="manual-airbnb-stay-details">
                    <strong>{stay.status === "held" ? "10-minute hold" : "Confirmed Airbnb stay"}</strong>
                    <span>{formatDate(stay.check_in_date)} – {formatDate(stay.check_out_date)} · {stay.guest_count} guests</span>
                    <span>{(stay.villa_names || []).join(", ") || "Villa selection unavailable"}</span>
                    {stay.status === "held" && <span>Expires {formatDateTime(stay.expires_at)}</span>}
                  </div>
                  <div className="manual-airbnb-stay-actions">
                    {stay.status === "held" && (
                      <button
                        type="button"
                        className="manual-btn-primary"
                        disabled={!!airbnbSaving}
                        onClick={() => updateAirbnbStay(stay, "confirm")}
                      >
                        {airbnbSaving === `${stay.id}:confirm` ? "Confirming…" : "Airbnb accepted"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="manual-btn-outline"
                      disabled={!!airbnbSaving}
                      onClick={() => updateAirbnbStay(stay, "release")}
                    >
                      {airbnbSaving === `${stay.id}:release` ? "Releasing…" : "Release dates"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : <p>No active Airbnb holds or stays.</p>}
        </section>
      </section>
      </div>
      )}

      {bookingResult ? (
        <div className="manual-result-layout">
          <section className="manual-panel manual-result-details">
            <div className="manual-result-header">
              <div className="manual-result-icon"><FileCheck2 size={24} /></div>
              <div className="manual-result-header-copy">
                <span className="manual-eyebrow">PAYMENT CHECKOUT</span>
                <h2>{confirmed ? "Booking confirmed" : "Complete payment to save booking"}</h2>
                <span className="manual-reservation-code">{bookingResult.booking_code}</span>
              </div>
            </div>
            <div className={`manual-live-status ${confirmed ? "paid" : "pending"}`} role="status" aria-live="polite">
              {confirmed ? <CheckCircle2 size={17} /> : <LoaderCircle size={17} className="manual-spin" />}
              <div>
                <strong>{confirmed ? (isPartialPayment ? "Downpayment received" : "Fully paid") : "Automatic payment verification"}</strong>
                <span>{confirmed ? "Reservation confirmed" : checkingPayment ? "Checking for payment updates…" : "No booking is saved until the guest’s payment is verified"}</span>
              </div>
            </div>
            <dl className="manual-result-facts">
              <div><dt>Guest</dt><dd>{form.first_name} {form.last_name}</dd></div>
              <div><dt>Check-in</dt><dd>{formatDate(form.check_in_date)} · 3:00 PM</dd></div>
              <div><dt>Selected villas</dt><dd>{selectedVillas.map((villa) => villa.villa_name).join(", ") || "—"}</dd></div>
              <div><dt>Guests</dt><dd>{guestCount}</dd></div>
              <div><dt>Total</dt><dd>{peso(bookingResult.total_amount)}</dd></div>
              <div><dt>Payment due</dt><dd>{peso(bookingResult.payment_due)}</dd></div>
              <div><dt>Payment status</dt><dd><span className={`manual-status-pill ${confirmed ? "success" : "waiting"}`}>{confirmed ? paymentStatus : "Awaiting payment"}</span></dd></div>
              <div><dt>Received</dt><dd>{peso(paymentAmount)}</dd></div>
              <div><dt>Balance</dt><dd>{peso(latestPayment?.balance_amount ?? bookingResult.total_amount)}</dd></div>
            </dl>
            {paymentSyncError && !confirmed && <p className="manual-sync-warning"><AlertCircle size={15} />{formatUserFacingMessage(paymentSyncError)}</p>}
            {error && <AlertMessage message={error}/>}
            <div className="manual-result-actions">
              {confirmed && <button className="manual-btn-outline" type="button" onClick={() => onViewBookings?.()}><ExternalLink size={15} /> View bookings</button>}
              <button className="manual-btn-primary" type="button" onClick={startNew}><Plus size={15} /> New booking</button>
            </div>
          </section>

          <section className="manual-panel manual-share-panel">
            <div className="manual-panel-heading">
              <div className="manual-panel-icon"><MessageCircle size={19} /></div>
              <div><h2>Send to guest</h2><p>Share the payment link in Messenger.</p></div>
            </div>
            <div className="manual-share-content">
              <label className="manual-field">Payment link
                <input readOnly value={bookingResult.checkout_url} onFocus={(e) => e.target.select()} />
              </label>
              <button className="manual-btn-outline manual-copy-button" type="button" onClick={() => copy(bookingResult.checkout_url, "Payment link")}>
                <ClipboardCopy size={15} /> Copy payment link
              </button>
              <label className="manual-field">Messenger message
                <textarea readOnly rows={7} value={messengerText} onFocus={(e) => e.target.select()} />
              </label>
              <button className="manual-btn-primary manual-copy-button" type="button" onClick={() => copy(messengerText, "Messenger message")}>
                <ClipboardCopy size={15} /> Copy message
              </button>
              {copyNotice && <AlertMessage message={copyNotice} type="success"/>}
            </div>
            <div className="manual-panel-footnote"><LockKeyhole size={15} /> Payments are confirmed automatically after verification.</div>
          </section>
        </div>
      ) : (
        <form className="manual-workspace" onSubmit={submit}>
          <div className="manual-booking-main">
            <section className="manual-panel">
              <div className="manual-panel-heading">
                <div className="manual-panel-icon"><Users size={19} /></div>
                <div><h2>Guest information</h2><p>Enter the guest’s contact details.</p></div>
              </div>
              <div className="manual-fields">
                <label className="manual-field">First name
                  <input required maxLength={100} autoComplete="given-name" placeholder="First name" value={form.first_name} onChange={(e) => setNameField("first_name", e.target.value)} />
                </label>
                <label className="manual-field">Last name
                  <input required maxLength={100} autoComplete="family-name" placeholder="Last name" value={form.last_name} onChange={(e) => setNameField("last_name", e.target.value)} />
                </label>
                <label className="manual-field">Mobile number
                  <input required type="tel" autoComplete="tel" placeholder="09XXXXXXXXX" value={form.phone} onChange={(e) => setField("phone", e.target.value)} />
                </label>
                <label className="manual-field">Email address
                  <input required type="email" autoComplete="email" placeholder="name@email.com" value={form.email} onChange={(e) => setField("email", e.target.value)} />
                </label>
              </div>
            </section>

            <section className="manual-panel">
              <div className="manual-panel-heading">
                <div className="manual-panel-icon"><CalendarDays size={19} /></div>
                <div><h2>Stay details</h2><p>Choose the date and available villas.</p></div>
              </div>
              <div className="manual-fields">
                <label className="manual-field">Check-in date
                  <input required type="date" min={manilaToday()} value={form.check_in_date} onChange={(e) => setField("check_in_date", e.target.value)} />
                </label>
                <label className="manual-field">Number of guests
                  <input required type="number" min="1" max="32" step="1" value={form.guest_count} onChange={(e) => setField("guest_count", e.target.value)} />
                </label>
              </div>
              <div className="manual-stay-strip">
                <div><small>Check-in</small><strong>3:00 PM</strong></div>
                <div><small>Check-out</small><strong>Next day</strong></div>
                <div><small>Duration</small><strong>1 night</strong></div>
              </div>
              <div className="manual-select-title">
                <h3>Available villas</h3>
                <span>{enoughRooms ? `${selectedIds.length} of ${minimumVillas} selected` : "Select a date"}</span>
              </div>
              <div className="manual-villas">
                {!form.check_in_date ? (
                  <div className="manual-empty"><CalendarDays size={20} /> Select a check-in date to see villas.</div>
                ) : loadingVillas ? (
                  <div className="manual-empty"><LoaderCircle size={18} className="manual-spin" /> Checking availability…</div>
                ) : villas.length ? villas.map((villa) => {
                  const isSelected = selectedIds.includes(villa.villa_id);
                  const canSelect = canAddVilla(villa, villas, selectedIds, guestCount, minimumVillas);
                  const blocked = !villa.available ? villa.reason :
                    !canSelect && capacity >= guestCount ? "Capacity filled" :
                    !canSelect ? Number(villa.capacity) < guestCount && minimumVillas === 1 ? "Too small" : "Not needed" : "Available";
                  return (
                    <button type="button" key={villa.villa_id} disabled={!isSelected && !canSelect}
                      aria-pressed={isSelected} className={`manual-villa ${isSelected ? "selected" : ""}`}
                      onClick={() => toggleVilla(villa.villa_id)}>
                      <span className="manual-villa-check">{isSelected && <Check size={13} />}</span>
                      <span className="manual-villa-info"><strong>{villa.villa_name}</strong><small>Up to {villa.capacity} guests · {isSelected ? "Selected" : blocked}</small></span>
                      <span className="manual-villa-price">{peso(villa.price)}</span>
                    </button>
                  );
                }) : (
                  <div className="manual-empty">No villa data available for this date.</div>
                )}
              </div>
              <div className={`manual-capacity ${validSelection ? "valid" : ""}`}>
                {validSelection ? <CheckCircle2 size={16} /> : <Users size={16} />}
                {validSelection ? `${capacity} guest capacity · Ready` :
                  !enoughRooms && form.check_in_date && !loadingVillas ? "Not enough villas available" :
                    enoughRooms ? `${guestCount || 0} guests · Choose ${minimumVillas} ${minimumVillas === 1 ? "villa" : "villas"}` : "Select available villas"}
              </div>
              <label className="manual-field manual-notes">Special requests <span className="manual-optional">(optional)</span>
                <textarea rows={3} maxLength={1000} placeholder="Notes for this reservation" value={form.notes} onChange={(e) => setField("notes", e.target.value)} />
              </label>
            </section>
          </div>

          <aside className="manual-panel manual-summary">
            <div className="manual-panel-heading">
              <div className="manual-panel-icon"><CreditCard size={19} /></div>
              <div><h2>Payment details</h2><p>Review and create a secure payment link.</p></div>
            </div>
            <div className="manual-section-caption">BOOKING SUMMARY</div>
            <div className="manual-bill">
              {selectedVillas.length ? selectedVillas.map((villa) => (
                <div key={villa.villa_id}><span>{villa.villa_name}</span><strong>{peso(villa.price)}</strong></div>
              )) : <div><span>No villas selected</span><strong>—</strong></div>}
            </div>
            <div className="manual-total"><span>Total stay</span><strong>{peso(total)}</strong></div>
            <div className="manual-select-title"><h3>Payment amount</h3></div>
            <div className="manual-payment-options">
              <button type="button" aria-pressed={form.payment_choice === "half"} className={form.payment_choice === "half" ? "selected" : ""} onClick={() => setField("payment_choice", "half")}>
                <span className="manual-radio"/><strong>50% deposit</strong><span className="manual-option-price">{peso(total / 2)}</span>
              </button>
              <button type="button" aria-pressed={form.payment_choice === "full"} className={form.payment_choice === "full" ? "selected" : ""} onClick={() => setField("payment_choice", "full")}>
                <span className="manual-radio"/><strong>Full payment</strong><span className="manual-option-price">{peso(total)}</span>
              </button>
            </div>
            <div className="manual-select-title"><h3>Payment method</h3></div>
            <div className="manual-methods">
              <div className="manual-wallet qrph selected" aria-label="Payment method QR Ph">
                <span className="manual-wallet-top">
                  <span className="manual-wallet-symbol"><QrCode size={20} /></span>
                  <CheckCircle2 size={17} className="manual-wallet-selected" />
                </span>
                <span className="manual-wallet-label"><strong>QR Ph</strong><small>Scan to pay</small></span>
              </div>
            </div>
            <div className="manual-due">
              <span>Amount to collect</span>
              <strong>{peso(due)}</strong>
              <small>{remaining > 0 ? `${peso(remaining)} remaining after deposit` : "No remaining balance"}</small>
            </div>
            {error && <AlertMessage message={error}/>}
            <button type="submit" className="manual-btn-primary manual-submit" disabled={saving || loadingVillas || !validSelection}>
              {saving ? <><LoaderCircle size={17} className="manual-spin"/> Creating reservation…</> : <><LockKeyhole size={17} /> Create booking & link <ArrowRight size={16}/></>}
            </button>
            <div className="manual-panel-footnote"><ShieldCheck size={15}/> Reservation confirms after the guest’s payment is verified.</div>
          </aside>
        </form>
      )}
    </div>
  );
}
