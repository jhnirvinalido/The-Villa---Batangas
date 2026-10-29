import { AlertMessage, LoadingScreen } from "./SystemFeedback";
import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import useLiveUpdates from "./useLiveUpdates";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FaArrowLeft,
  FaArrowRight,
  FaCalendarAlt,
  FaCheck,
  FaCheckCircle,
  FaChevronLeft,
  FaChevronRight,
  FaClock,
  FaCreditCard,
  FaEnvelope,
  FaExclamationTriangle,
  FaHome,
  FaMoneyBillWave,
  FaPhoneAlt,
  FaShieldAlt,
  FaUser,
  FaUsers,
  FaWallet,
} from "react-icons/fa";
import "./BookForm.css";
import { readBookingToken, saveBookingToken } from "./bookingToken.mjs";

const API_URL = (
  (typeof window !== "undefined" && window.__THE_VILLA_API_BASE__) ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const LANDING_SELECTED_VILLA_KEY =
  "theVillaLandingSelectedVillaId";
const RECENTLY_VIEWED_VILLA_KEY =
  "theVillaRecentlyViewedVillaId";
const MAX_GUESTS = 32;
const GUEST_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8];
const CHECK_IN_TIME = "3:00 PM";
const BOOKING_BACKGROUND_IMAGE = "/background.jpg";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const STEPS = [
  { id: 1, label: "Availability" },
  { id: 2, label: "Villa" },
  { id: 3, label: "Personal Info" },
  { id: 4, label: "Payment" },
  { id: 5, label: "Confirmation" },
];

const PAYMENT_METHODS = [
  {
    id: "gcash",
    title: "GCash",
    description: "Pay securely through GCash.",
    icon: FaWallet,
    logos: [{ src: "/gcash-logo.svg", alt: "GCash" }],
  },
  {
    id: "maya",
    title: "Maya",
    description: "Pay securely through Maya.",
    icon: FaWallet,
    logos: [{ src: "/maya-logo.svg", alt: "Maya" }],
  },
  {
    id: "debit",
    title: "Credit / Debit Card",
    description: "Visa or Mastercard through PayMongo.",
    icon: FaCreditCard,
    logos: [
      { src: "/visa-logo.svg", alt: "Visa" },
      { src: "/mastercard-logo.svg", alt: "Mastercard" },
    ],
  },
  {
    id: "qrph",
    title: "QR Ph",
    description: "Use a compatible bank or e-wallet.",
    icon: FaMoneyBillWave,
    logos: [{ src: "/qrph-logo.svg", alt: "QR Ph" }],
  },
];

const DEFAULT_VILLAS = [
  {
    id: "villa-1",
    title: "Family Villa",
    capacity: 8,
    price: 4500,
    image: "/family.jpg",
    description:
      "A spacious private villa for family gatherings, celebrations, and relaxing weekend stays.",
    amenities: [
      "Heated plunge pool",
      "Complete kitchen",
      "Smart projector",
      "300 Mbps Wi-Fi",
    ],
  },
  {
    id: "villa-2",
    title: "Comfort Villa",
    capacity: 8,
    price: 5500,
    image: "/couple.jpg",
    description:
      "A comfortable private villa for couples, families, and small groups who value privacy and convenience.",
    amenities: [
      "Heated plunge pool",
      "Air-conditioned rooms",
      "Smart TV",
      "Kitchen appliances",
    ],
  },
  {
    id: "villa-3",
    title: "Group Villa",
    capacity: 8,
    price: 6500,
    image: "/barkada.jpg",
    description:
      "A roomy villa with shared spaces for barkada bonding, birthdays, and overnight celebrations.",
    amenities: [
      "Group lounge",
      "Smart projector",
      "Kitchen access",
      "BBQ area",
    ],
  },
  {
    id: "villa-4",
    title: "Intimate Villa",
    capacity: 4,
    price: 7500,
    image: "/image4.jpg",
    description:
      "A quieter private villa for couples, small families, and guests looking for a relaxed stay.",
    amenities: [
      "Private plunge pool",
      "Two double beds",
      "Smart TV",
      "Kitchen",
    ],
  },
];

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
  if (selectedIds.includes(villa.id)) return true; // Selected rooms remain removable.
  if (!Number.isFinite(required) || selectedIds.length >= required) return false;
  const selected = villas.filter((item) => selectedIds.includes(item.id));
  const used = selected.reduce((sum, item) => sum + Number(item.capacity || 0), 0);
  if (used >= Number(guests)) return false;
  const seatsAfterAdding = used + Number(villa.capacity || 0);
  const openSlots = required - selectedIds.length - 1;
  const bestRemaining = villas.filter((item) => item.available === true &&
    !selectedIds.includes(item.id) && item.id !== villa.id)
    .map((item) => Number(item.capacity || 0))
    .sort((a, b) => b - a).slice(0, openSlots)
    .reduce((sum, count) => sum + count, 0);
  return seatsAfterAdding + bestRemaining >= Number(guests);
}

function fixSelectedVillas(ids, guests, villas) {
  const count = requiredVillaCount(guests, villas);
  if (!Number.isFinite(count)) return [];
  return ids.reduce((next, id) => {
    const villa = villas.find((item) => item.id === id);
    return canAddVilla(villa, villas, next, guests, count) ? [...next, id] : next;
  }, []);
}

function money(value) {
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function toIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) {
    return null;
  }

  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function todayValue() {
  return toIsoDate(new Date());
}

function startOfMonth(value) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function endOfMonth(value) {
  return new Date(value.getFullYear(), value.getMonth() + 1, 0);
}

function calendarCells(activeMonth) {
  const monthStart = startOfMonth(activeMonth);
  const firstCell = new Date(
    monthStart.getFullYear(),
    monthStart.getMonth(),
    1 - monthStart.getDay()
  );

  return Array.from({ length: 42 }, (_, index) => {
    return new Date(
      firstCell.getFullYear(),
      firstCell.getMonth(),
      firstCell.getDate() + index
    );
  });
}

function formatDate(value) {
  const parsed = parseIsoDate(value);

  if (!parsed) {
    return "Not selected";
  }

  return new Intl.DateTimeFormat("en-PH", {
    weekday: "short",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function normalizePhone(value) {
  const digits = String(value || "").replace(/\D/g, "");

  if (digits.length === 10 && digits.startsWith("9")) {
    return `+63${digits}`;
  }

  if (digits.length === 11 && digits.startsWith("09")) {
    return `+63${digits.slice(1)}`;
  }

  if (digits.length === 12 && digits.startsWith("639")) {
    return `+${digits}`;
  }

  return "";
}

function flattenAmenities(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .flatMap((group) => {
      if (typeof group === "string") {
        return [group];
      }

      return Array.isArray(group?.items) ? group.items : [];
    })
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 5);
}

function normalizeCatalog(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return DEFAULT_VILLAS;
  }

  const fallbackById = new Map(
    DEFAULT_VILLAS.map((villa) => [villa.id, villa])
  );

  const normalized = rows
    .map((row) => {
      const id = String(row?.id || "").trim();
      const fallback = fallbackById.get(id) || DEFAULT_VILLAS[0];
      const amenities = flattenAmenities(row?.amenities);

      return {
        ...fallback,
        id: id || fallback.id,
        title:
          row?.landing_title ||
          row?.title ||
          row?.name ||
          fallback.title,
        capacity: Number(row?.capacity || fallback.capacity),
        price: Number(row?.price ?? fallback.price),
        image: row?.image_url || row?.image || fallback.image,
        description:
          row?.short_description ||
          row?.description ||
          row?.details ||
          fallback.description,
        amenities: amenities.length ? amenities : fallback.amenities,
      };
    })
    .filter((villa) => villa.id);

  return normalized.length ? normalized : DEFAULT_VILLAS;
}

async function readApiError(response) {
  try {
    const payload = await response.json();

    if (typeof payload?.detail === "string") {
      return payload.detail;
    }

    if (Array.isArray(payload?.detail)) {
      return payload.detail
        .map((item) => item?.msg || "Invalid value.")
        .join(" ");
    }

    return (
      payload?.detail?.message ||
      payload?.message ||
      "The request could not be completed."
    );
  } catch {
    return "The server returned an unreadable response.";
  }
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.json();
}

function readInitialBookingSelection() {
  if (typeof window === "undefined") {
    return {
      villaId: "",
      recentlyViewedVillaId: "",
      guestCount: "1",
      checkInDate: "",
    };
  }

  const query = new URLSearchParams(
    window.location.search
  );

  let villaId = String(
    query.get("villa") || ""
  ).trim();

  let recentlyViewedVillaId = "";

  try {
    if (!villaId) {
      villaId = String(
        window.sessionStorage.getItem(
          LANDING_SELECTED_VILLA_KEY
        ) || ""
      ).trim();
    }

    recentlyViewedVillaId = String(
      window.sessionStorage.getItem(
        RECENTLY_VIEWED_VILLA_KEY
      ) || ""
    ).trim();
  } catch {
    // URL selection still works if sessionStorage is unavailable.
  }

  const requestedGuests = Number(
    query.get("guests")
  );

  const guestCount =
    Number.isFinite(requestedGuests) &&
    requestedGuests >= 1 &&
    requestedGuests <= MAX_GUESTS
      ? String(requestedGuests)
      : "1";

  const requestedDate = String(
    query.get("date") || ""
  ).trim();

  const validDate =
    /^\d{4}-\d{2}-\d{2}$/.test(requestedDate) &&
    requestedDate >= todayValue()
      ? requestedDate
      : "";

  return {
    villaId,
    recentlyViewedVillaId,
    guestCount,
    checkInDate: validDate,
  };
}

function ProgressSteps({ currentStep }) {
  return (
    <div className="booking-progress" aria-label="Booking progress">
      {STEPS.map((item, index) => {
        const complete = currentStep > item.id;
        const active = currentStep === item.id;

        return (
          <div className="booking-progress-item" key={item.id}>
            <span
              className={`booking-progress-dot ${
                active ? "active" : ""
              } ${complete ? "complete" : ""}`}
            >
              {complete ? <FaCheck /> : item.id}
            </span>

            <small>{item.label}</small>

            {index < STEPS.length - 1 && (
              <i className={complete ? "complete" : ""} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Field({
  label,
  icon: Icon,
  required = false,
  helper = "",
  children,
}) {
  return (
    <label className="booking-field">
      <span className="booking-field-label">
        {Icon ? <Icon /> : null}
        {label}
        {required ? <b>*</b> : null}
      </span>

      {children}

      {helper ? <small>{helper}</small> : null}
    </label>
  );
}

function AvailabilityCalendar({
  guestCount,
  selectedDate,
  preferredVillaId,
  onSelectDate,
}) {
  const initialMonth = useMemo(() => {
    const parsed = parseIsoDate(selectedDate);
    return startOfMonth(parsed || new Date());
  }, []);

  const [calendarRevision, setCalendarRevision] = useState(0);
  useLiveUpdates({ audience: "public", domains: ["availability", "catalog"], onChange: () => setCalendarRevision(value => value + 1) });
  const [activeMonth, setActiveMonth] = useState(initialMonth);
  const [days, setDays] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function loadCalendar() {
      setLoading(true);
      setError("");

      const params = new URLSearchParams({
        start_date: toIsoDate(startOfMonth(activeMonth)),
        end_date: toIsoDate(endOfMonth(activeMonth)),
        guest_count: "1",
      });

      try {
        const response = await fetch(
          `${API_URL}/public-bookings/calendar-availability?${params.toString()}`,
          {
            signal: controller.signal,
            headers: {
              Accept: "application/json",
            },
          }
        );

        if (!response.ok) {
          throw new Error(await readApiError(response));
        }

        const payload = await response.json();

        if (!active) {
          return;
        }

        setDays(payload?.days || {});
      } catch (requestError) {
        if (requestError?.name === "AbortError" || !active) {
          return;
        }

        setDays({});
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load available dates."
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadCalendar();

    return () => {
      active = false;
      controller.abort();
    };
  }, [activeMonth, guestCount, calendarRevision]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const currentMonth = startOfMonth(new Date());
  const previousDisabled = activeMonth <= currentMonth;

  return (
    <div className="booking-calendar">
      <div className="booking-calendar-topbar">
        <div>
          <span>Available dates</span>
          <strong>
            {activeMonth.toLocaleDateString("en-PH", {
              month: "long",
              year: "numeric",
            })}
          </strong>
        </div>

        <div className="booking-calendar-controls">
          <button
            type="button"
            disabled={previousDisabled}
            onClick={() =>
              setActiveMonth(
                (current) =>
                  new Date(
                    current.getFullYear(),
                    current.getMonth() - 1,
                    1
                  )
              )
            }
            aria-label="Previous month"
          >
            <FaChevronLeft />
          </button>

          <button
            type="button"
            onClick={() =>
              setActiveMonth(
                (current) =>
                  new Date(
                    current.getFullYear(),
                    current.getMonth() + 1,
                    1
                  )
              )
            }
            aria-label="Next month"
          >
            <FaChevronRight />
          </button>
        </div>
      </div>

      <div
        className={`booking-calendar-status ${
          error ? "error" : ""
        }`}
      >
        {loading ? (
          <>
            <BookingSpinner compact />

          </>
        ) : error ? (
          <>
            <FaExclamationTriangle />
            {error}
          </>
        ) : (
          <>
            <FaCheckCircle />
            Please select date you preferred.
          </>
        )}
      </div>

      <div className="booking-calendar-weekdays">
        {WEEKDAYS.map((weekday) => (
          <span key={weekday}>{weekday}</span>
        ))}
      </div>

      <div className="booking-calendar-grid">
        {calendarCells(activeMonth).map((cellDate) => {
          const key = toIsoDate(cellDate);
          const inMonth =
            cellDate.getMonth() === activeMonth.getMonth();
          const isPast = cellDate < today;
          const dayState = days[key];

          const preferredAvailable =
            !preferredVillaId ||
            Boolean(
              dayState?.available_villa_ids?.some(
                (id) =>
                  String(id) === String(preferredVillaId)
              )
            );

          const available =
            inMonth &&
            !isPast &&
            Number(dayState?.total_available_capacity || 0) >= Number(guestCount || 1) &&
            preferredAvailable;

          const selected = selectedDate === key;

          return (
            <button
              type="button"
              key={key}
              className={`booking-calendar-day ${
                !inMonth ? "outside" : ""
              } ${available ? "available" : "disabled"} ${
                !available && inMonth && !isPast ? "full" : ""
              } ${
                selected ? "selected" : ""
              }`}
              disabled={!available || loading}
              onClick={() => onSelectDate(key)}
              title={
                !available && inMonth && !isPast
                  ? "Fully booked / unavailable"
                  : available
                    ? "Available date"
                    : ""
              }
              aria-label={
                available
                  ? `${formatDate(key)}, ${
                      dayState?.available_count || 0
                    } villa options available`
                  : `${formatDate(key)}, fully booked or unavailable`
              }
            >
              <span>{cellDate.getDate()}</span>

              {inMonth && !isPast ? (
                <>
                  <small className="booking-calendar-status-wide">
                    {available
                      ? preferredVillaId
                        ? "Villa available"
                        : `${dayState?.available_count || 0} open`
                      : "Unavailable"}
                  </small>
                  <small
                    className="booking-calendar-status-compact"
                    aria-hidden="true"
                  >
                    {available ? dayState?.available_count || 0 : "Full"}
                  </small>
                </>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="booking-calendar-legend">
        <span>
          <i className="open" />
          Available
        </span>

        <span>
          <i className="full" />
          Unavailable
        </span>

        <span>
          <i className="picked" />
          Selected
        </span>
      </div>
    </div>
  );
}

function MessageModal({ message, onClose }) {
  const dialog = useRef(null);
  const open = Boolean(message);
  useEffect(() => {
    if (!open || !dialog.current) return;
    const node = dialog.current;
    const previous = document.activeElement;
    node.showModal();
    return () => { node.close(); previous?.focus(); };
  }, [open]);
  if (!open) return null;
  return <dialog ref={dialog} role="alertdialog" aria-label="Please check your details" onCancel={event=>{event.preventDefault();onClose();}} className="m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl backdrop:bg-stone-950/40 backdrop:backdrop-blur-sm"><h2 className="mb-4 text-lg font-bold text-stone-900">Please check your details</h2><AlertMessage message={message}/><button type="button" autoFocus onClick={onClose} className="mt-5 rounded-xl border border-amber-900 bg-amber-900 px-5 py-3 text-sm font-semibold text-white">OK</button></dialog>;
}

/** A bare spinner in the Villa's bronze palette. */
function BookingSpinner({ compact = false }) {
  return (
    <span
      className={`booking-spinner animate-spin${compact ? " compact" : ""}`}
      role="status"
      aria-label="Loading"
    />
  );
}

function LoadingOverlay({ message }) {
  return <LoadingScreen message={message || "Loading your booking…"}/>;
}


export default function BookForm() {
  const navigate = useNavigate();
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  useLiveUpdates({ audience: "public", domains: ["catalog"], onChange: () => setCatalogRevision(value => value + 1) });
  useLiveUpdates({ audience: "public", domains: ["availability", "catalog"], onChange: () => setAvailabilityRevision(value => value + 1) });
  const initialSelection = useMemo(
    readInitialBookingSelection,
    []
  );

  const returnHandledRef = useRef(false);


  const [step, setStep] = useState(1);
  const [catalog, setCatalog] = useState(DEFAULT_VILLAS);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const maxGuestCount = catalog.reduce((total, villa) => total + Math.max(0, Number(villa.capacity) || 0), 0);

  const [preferredVillaId, setPreferredVillaId] = useState(
    initialSelection.villaId
  );

  const [selectedVillaId, setSelectedVillaId] = useState(
    initialSelection.villaId
  );
  const [selectedVillaIds, setSelectedVillaIds] = useState(
    initialSelection.villaId ? [initialSelection.villaId] : []
  );

  const [
    recentlyViewedVillaId,
    setRecentlyViewedVillaId,
  ] = useState(
    initialSelection.recentlyViewedVillaId ||
      initialSelection.villaId
  );

  const [availability, setAvailability] = useState(null);
  const [availabilityLoading, setAvailabilityLoading] =
    useState(false);

  const [paymentChoice, setPaymentChoice] = useState("half");
  const [paymentMethod, setPaymentMethod] = useState("gcash");
  const [acceptedPolicy, setAcceptedPolicy] = useState(false);

  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("");
  const [stepTransition, setStepTransition] = useState({ active: false, message: "" });
  const stepTransitionLock = useRef(false);
  const [message, setMessage] = useState("");
  const [pendingGuestCount, setPendingGuestCount] = useState(null);
  const [guestOptionsOpen, setGuestOptionsOpen] = useState(false);
  const [activeGuestOption, setActiveGuestOption] = useState(0);

  const [createdBooking, setCreatedBooking] = useState(null);
  const [paymentResult, setPaymentResult] = useState(null);
  const [liveBooking, setLiveBooking] = useState(null);
  const liveBookingRefresh = useRef(null);
  useLiveUpdates({
    audience: liveBooking ? `booking:${liveBooking.bookingId}` : "booking:inactive",
    bookingToken: liveBooking?.token || "",
    domains: ["bookings", "payments"],
    enabled: Boolean(liveBooking),
    onChange: () => liveBookingRefresh.current?.(),
  });

  const initialGuestCount = useMemo(() => {
    if (initialSelection.guestCount) {
      const parsed = Number(initialSelection.guestCount);
      if (parsed >= 1 && parsed <= maxGuestCount) {
        return String(parsed);
      }
    }

    return "1";
  }, [
    initialSelection.guestCount,
    initialSelection.villaId,
    maxGuestCount,
  ]);

  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    guestCount: initialGuestCount,
    checkInDate: initialSelection.checkInDate,
    checkInTime: CHECK_IN_TIME,
    notes: "",
  });

  const preferredVilla = useMemo(
    () =>
      catalog.find(
        (villa) => villa.id === preferredVillaId
      ) || null,
    [catalog, preferredVillaId]
  );

  const selectedVilla = useMemo(
    () =>
      catalog.find(
        (villa) => villa.id === selectedVillaId
      ) || null,
    [catalog, selectedVillaId]
  );

  const recentlyViewedVilla = useMemo(
    () =>
      catalog.find(
        (villa) =>
          villa.id === recentlyViewedVillaId
      ) || null,
    [catalog, recentlyViewedVillaId]
  );

  const visibleVillas = useMemo(() => {
    const decorated = catalog.map(
      (villa) => {
        const state =
          availability?.villas?.find(
            (item) =>
              item.villa_id === villa.id
          );

        return {
          ...villa,
          available: Array.isArray(
            availability?.available_villa_ids
          )
            ? availability.available_villa_ids.includes(
                villa.id
              )
            : null,
          unavailableReason:
            state?.reason || "Unavailable",
        };
      }
    );

    return decorated.sort((a, b) => {
      if (a.id === preferredVillaId) {
        return -1;
      }

      if (b.id === preferredVillaId) {
        return 1;
      }

      if (
        a.id === recentlyViewedVillaId
      ) {
        return -1;
      }

      if (
        b.id === recentlyViewedVillaId
      ) {
        return 1;
      }

      return 0;
    });
  }, [
    catalog,
    availability,
    preferredVillaId,
    recentlyViewedVillaId,
  ]);

  const selectedVillas = catalog.filter((villa) => selectedVillaIds.includes(villa.id));
  const guestNumber = Number(form.guestCount || 0);
  const guestCountError = guestNumber > maxGuestCount
    ? `All villas can accommodate a maximum of ${maxGuestCount} guests. Please enter ${maxGuestCount} or fewer.`
    : "";
  const selectableVillas = visibleVillas.map((villa) => ({ ...villa, available: villa.available === true }));
  const combinedCapacity = selectedVillas.reduce((sum, villa) => sum + Number(villa.capacity || 0), 0);
  const minimumVillaCount = requiredVillaCount(guestNumber, selectableVillas);
  const canFitGuests = Number.isFinite(minimumVillaCount);
  const selectionValid = canFitGuests && selectedVillas.length === minimumVillaCount &&
    selectedVillaIds.every((id) => selectableVillas.some((villa) => villa.id === id && villa.available)) &&
    combinedCapacity >= guestNumber;
  const totalAmount = selectedVillas.reduce((sum, villa) => sum + Number(villa.price || 0), 0);
  function toggleVilla(id) {
    const villa = selectableVillas.find((item) => item.id === id);
    setSelectedVillaIds((current) => {
      if (!current.includes(id) && !canAddVilla(villa, selectableVillas, current, guestNumber, minimumVillaCount)) return current;
      const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
      setSelectedVillaId(next[0] || "");
      return next;
    });
  }
  useEffect(() => {
    setSelectedVillaIds((current) => {
      const next = fixSelectedVillas(current, guestNumber, selectableVillas);
      if (current.length === next.length && current.every((id, i) => next[i] === id)) return current;
      setSelectedVillaId(next[0] || "");
      return next;
    });
  }, [guestNumber, availability, catalog]);


  const amountDue =
    paymentChoice === "full"
      ? totalAmount
      : Math.ceil(totalAmount * 0.5);

  const remainingBalance = Math.max(
    totalAmount - amountDue,
    0
  );

  useEffect(() => {
    let active = true;

    async function loadCatalog() {
      try {
        const result = await apiRequest(
          "/villa-catalog/public"
        );

        if (!active) {
          return;
        }

        const normalized = normalizeCatalog(
          result?.data
        );

        setCatalog(normalized);

        if (
          preferredVillaId &&
          !normalized.some(
            (villa) =>
              villa.id === preferredVillaId
          )
        ) {
          setPreferredVillaId("");
          setSelectedVillaId("");
        }
      } catch {
        if (active) {
          setCatalog(DEFAULT_VILLAS);
        }
      } finally {
        if (active) {
          setCatalogLoading(false);
        }
      }
    }

    loadCatalog();

    window.addEventListener(
      "focus",
      loadCatalog
    );

    return () => {
      active = false;
      window.removeEventListener(
        "focus",
        loadCatalog
      );
    };
  }, [preferredVillaId, catalogRevision]);

  useEffect(() => {
    if (!form.checkInDate) {
      setAvailability(null);
      return undefined;
    }

    let active = true;
    const controller = new AbortController();

    async function loadExactAvailability() {
      setAvailabilityLoading(true);

      const params = new URLSearchParams({
        check_in_date: form.checkInDate,
        guest_count: "1",
      });

      try {
        const response = await fetch(
          `${API_URL}/public-bookings/availability?${params.toString()}`,
          {
            signal: controller.signal,
            headers: {
              Accept: "application/json",
            },
          }
        );

        if (!response.ok) {
          throw new Error(
            await readApiError(response)
          );
        }

        const result = await response.json();

        if (!active) {
          return;
        }

        setAvailability(result);
      } catch (requestError) {
        if (
          requestError?.name === "AbortError" ||
          !active
        ) {
          return;
        }

        setAvailability(null);
        setMessage(
          requestError instanceof Error
            ? requestError.message
            : "Unable to check availability."
        );
      } finally {
        if (active) {
          setAvailabilityLoading(false);
        }
      }
    }

    loadExactAvailability();

    return () => {
      active = false;
      controller.abort();
    };
  }, [
    form.checkInDate,
    form.guestCount,
    availabilityRevision,
  ]);

  useEffect(() => {
    if (returnHandledRef.current) {
      return;
    }

    const params = new URLSearchParams(
      window.location.search
    );

    const payment = params.get("payment");
    const bookingId = params.get("booking");

    if (!payment || !bookingId) {
      return;
    }

    returnHandledRef.current = true;
    setStep(5);

    const token = readBookingToken(bookingId);

    if (!token) {
      setPaymentResult({
        state:
          payment === "cancelled"
            ? "cancelled"
            : "pending",
        message:
          "This browser no longer has its secure checkout token. Please contact The Villa and provide your booking reference.",
      });

      return;
    }

    if (payment === "cancelled") {
      setLoading(true);
      setLoadingMessage(
        "Releasing the cancelled reservation…"
      );

      apiRequest(
        `/public-bookings/${bookingId}/cancel`,
        {
          method: "POST",
          headers: {
            "X-Booking-Token": token,
          },
        }
      )
        .then((result) => {
          setCreatedBooking(
            result?.booking || null
          );

          setPaymentResult({
            state: "cancelled",
            message:
              result?.message ||
              "Payment was cancelled and the selected date has been released.",
          });
        })
        .catch((error) => {
          setPaymentResult({
            state: "cancelled",
            message:
              error instanceof Error
                ? error.message
                : "Payment was cancelled.",
          });
        })
        .finally(() => {
          setLoading(false);
          setLoadingMessage("");
        });

      return;
    }

    setLiveBooking({ bookingId, token });
    setLoading(true);
    setLoadingMessage(
      "Checking your PayMongo payment status…"
    );

    let active = true;
    let checking = false;
    let fallbackTimer;

    async function verifyPayment(attempts = 6) {
      if (!active || checking) return;
      checking = true;
      let latest = null;

      try {
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
          latest = await apiRequest(
            `/public-bookings/${bookingId}/sync-payment`,
            {
              method: "POST",
              headers: { "X-Booking-Token": token },
            }
          );

          if (!active) return;
          if (["paid", "failed", "expired"].includes(latest?.state)) break;
          if (attempt < attempts) {
            await new Promise((resolve) => window.setTimeout(resolve, 1400));
          }
        }

        setCreatedBooking(latest?.booking || null);
        setPaymentResult({
          state: latest?.state || "pending",
          message: latest?.message || "Your payment status is still being confirmed.",
        });
        if (["paid", "failed", "expired"].includes(latest?.state)) {
          window.clearInterval(fallbackTimer);
          liveBookingRefresh.current = null;
          setLiveBooking(null);
        }
      } catch (error) {
        if (active) {
          setPaymentResult({
            state: "pending",
            message: error instanceof Error
              ? error.message
              : "We could not verify the payment yet.",
          });
        }
      } finally {
        checking = false;
        if (active) {
          setLoading(false);
          setLoadingMessage("");
        }
      }
    }

    liveBookingRefresh.current = () => verifyPayment(1);
    fallbackTimer = window.setInterval(() => verifyPayment(1), 30000);
    verifyPayment();
    return () => {
      active = false;
      window.clearInterval(fallbackTimer);
      liveBookingRefresh.current = null;
    };
  }, []);

  function updateForm(field, value) {
    if (field === "guestCount") {
      const next = String(value).trim();
      if (next && !/^\d+$/.test(next)) return;
      setForm((current) => ({ ...current, guestCount: next }));
      setAvailability(null);
      return;
    }
    if (field === "checkInTime") return;

    setForm((current) => ({
      ...current,
      [field]: value,
    }));

    if (field === "checkInDate") {
      setAvailability(null);
      setSelectedVillaIds([]);

      if (!preferredVillaId) {
        setSelectedVillaId("");
      }
    }
  }

  function updatePersonName(field, value) {
    if (/\p{N}/u.test(value)) {
      setMessage("Names must not contain numbers.");
      return;
    }
    setMessage("");
    updateForm(field, value);
  }

  function validatePersonalInfo() {
    if (/\p{N}/u.test(`${form.firstName} ${form.lastName}`)) {
      setMessage("Names must not contain numbers.");
      return false;
    }
    const emailReady =
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
        form.email.trim()
      );

    if (!form.firstName.trim()) {
      setMessage(
        "Please enter the guest's first name."
      );
      return false;
    }

    if (!form.lastName.trim()) {
      setMessage(
        "Please enter the guest's last name."
      );
      return false;
    }

    if (!emailReady) {
      setMessage(
        "Please enter a valid email address."
      );
      return false;
    }

    if (!normalizePhone(form.phone)) {
      setMessage(
        "Please enter a valid Philippine mobile number, for example 09123456789."
      );
      return false;
    }

    return true;
  }

  async function refreshExactAvailability() {
    if (!form.checkInDate) {
      setMessage(
        "Please choose your check-in date first."
      );
      return null;
    }

    setAvailabilityLoading(true);

    try {
      const query = new URLSearchParams({
        check_in_date: form.checkInDate,
        guest_count: "1",
      });

      const result = await apiRequest(
        `/public-bookings/availability?${query.toString()}`
      );

      setAvailability(result);
      return result;
    } finally {
      setAvailabilityLoading(false);
    }
  }

  // The spinner stays visible during the real request, and for a
  // short moment on instant transitions so each step change is perceptible.
  // A ref prevents double-clicks from starting simultaneous transitions.
  async function runStepTransition(targetStep, text, check = null, fallback = "Unable to proceed.") {
    if (stepTransitionLock.current || loading) return;
    stepTransitionLock.current = true;
    setStepTransition({ active: true, message: text });

    try {
      const [result] = await Promise.allSettled([
        check ? Promise.resolve().then(check) : Promise.resolve(true),
        new Promise((resolve) => window.setTimeout(resolve, 480)),
      ]);
      if (result.status === "rejected") {
        setMessage(result.reason instanceof Error ? result.reason.message : fallback);
      } else if (result.value !== false) {
        setStep(targetStep);
      }
    } finally {
      setStepTransition({ active: false, message: "" });
      stepTransitionLock.current = false;
    }
  }

  function continueFromPersonalInfo() {
    if (!validatePersonalInfo()) return;
    runStepTransition(4, "Preparing your reservation and payment details…");
  }

  async function continueFromAvailability() {
    if (
      Number(form.guestCount) < 1 ||
      Number(form.guestCount) > maxGuestCount
    ) {
      setMessage(`Please choose a guest count from 1 to ${maxGuestCount}.`);
      return;
    }

    if (!form.checkInDate) {
      setMessage("Please select an available date.");
      return;
    }

    await runStepTransition(
      2,
      "Checking your date and available villas…",
      async () => {
        const fresh = await refreshExactAvailability();
        const available = (fresh?.villas || []).filter((villa) => villa.available);
        const seats = available.reduce((sum, villa) => sum + Number(villa.capacity || 0), 0);
        if (seats < guestNumber) {
          setMessage("No villas are available for the selected date and guest count.");
          return false;
        }

        const freshVillaCount = requiredVillaCount(guestNumber, available);
        if (
          preferredVillaId &&
          guestNumber <= Number(preferredVilla?.capacity || 0) &&
          freshVillaCount === 1
        ) {
          if (fresh?.available_villa_ids?.includes(preferredVillaId)) {
            setSelectedVillaId(preferredVillaId);
            setSelectedVillaIds((current) => current.includes(preferredVillaId) ? current : [preferredVillaId]);
          } else {
            setForm((current) => ({ ...current, checkInDate: "" }));
            setAvailability(null);
            setMessage(`${preferredVilla?.title || "Your selected villa"} is no longer available for that date. Please choose another available date.`);
            return false;
          }
        }

        return true;
      },
      "Unable to re-check availability."
    );
  }

  async function continueFromVilla() {
    if (!selectionValid) {
      setMessage(
        canFitGuests
          ? `Select ${minimumVillaCount} ${minimumVillaCount === 1 ? "villa" : "villas"} for ${guestNumber} guests.`
          : "There are not enough available villas for this date."
      );
      return;
    }

    await runStepTransition(
      3,
      "Verifying your selected villa…",
      async () => {
        const fresh = await refreshExactAvailability();
        if (!selectedVillaIds.every((id) => fresh?.available_villa_ids?.includes(id))) {
          if (selectedVilla?.id === preferredVillaId) {
            setMessage(`${selectedVilla?.title || "Your selected villa"} is not available for the selected date. Please choose another available villa.`);
          } else {
            setMessage("That villa was just taken for the selected date. Please choose another available villa.");
          }
          return false;
        }
        return true;
      },
      "Unable to re-check the villa."
    );
  }

  async function confirmBooking() {
    if (!selectionValid || loading) {
      return;
    }

    if (!acceptedPolicy) {
      setMessage(
        "Please confirm the booking details and reservation policy."
      );
      return;
    }

    setLoading(true);
    setLoadingMessage(
      "Confirming availability and preparing secure checkout…"
    );

    try {
      const fresh =
        await refreshExactAvailability();

      if (
        !selectedVillaIds.every((id) => fresh?.available_villa_ids?.includes(id))
      ) {
        setStep(3);

        throw new Error(
          "That villa was just reserved by another guest. Please choose another available villa."
        );
      }

      const createResult = await apiRequest(
        "/public-bookings",
        {
          method: "POST",
          body: JSON.stringify({
            first_name:
              form.firstName.trim(),
            last_name:
              form.lastName.trim(),
            email:
              form.email
                .trim()
                .toLowerCase(),
            phone:
              normalizePhone(form.phone),
            villa_id: selectedVillaIds[0],
            villa_ids: selectedVillaIds,
            check_in_date:
              form.checkInDate,
            check_in_time: CHECK_IN_TIME,
            guest_count: Number(
              form.guestCount
            ),
            notes:
              form.notes.trim() || null,
            payment_choice:
              paymentChoice,
            payment_method:
              paymentMethod,
          }),
        }
      );

      const booking =
        createResult?.booking;

      const token =
        createResult?.booking_access_token;

      if (!booking?.id || !token) {
        throw new Error(
          "The server did not return a complete booking confirmation."
        );
      }

      saveBookingToken(booking.id, token);

      setCreatedBooking(booking);

      const checkoutResult =
        await apiRequest(
          `/public-bookings/${booking.id}/checkout`,
          {
            method: "POST",
            headers: {
              "X-Booking-Token": token,
            },
            body: JSON.stringify({
              payment_method:
                paymentMethod,
              payment_scope:
                "selected",
            }),
          }
        );

      if (
        !checkoutResult?.checkout_url
      ) {
        throw new Error(
          "PayMongo did not return a checkout URL."
        );
      }

      window.location.assign(
        checkoutResult.checkout_url
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to create the booking."
      );
    } finally {
      setLoading(false);
      setLoadingMessage("");
    }
  }

  function resetForm() {
    setPreferredVillaId("");
    setSelectedVillaId("");
    setSelectedVillaIds([]);
    setRecentlyViewedVillaId("");

    try {
      window.sessionStorage.removeItem(
        LANDING_SELECTED_VILLA_KEY
      );
      window.sessionStorage.removeItem(
        RECENTLY_VIEWED_VILLA_KEY
      );
    } catch {
      // Ignore storage cleanup errors.
    }

    setPaymentChoice("half");
    setPaymentMethod("gcash");
    setAcceptedPolicy(false);
    setCreatedBooking(null);
    setPaymentResult(null);
    setAvailability(null);

    setForm({
      firstName: "",
      lastName: "",
      email: "",
      phone: "",
      guestCount: "1",
      checkInDate: "",
      checkInTime: CHECK_IN_TIME,
      notes: "",
    });

    window.history.replaceState(
      {},
      "",
      "/book"
    );
  }

  const stepTitle = {
    1: "Choose an available date",
    2: "Choose your villa",
    3: "Your information",
    4: "Review and payment",
    5: "Reservation confirmation",
  }[step];

  const selectedVillaState =
    visibleVillas.find(
      (villa) =>
        villa.id === selectedVillaId
    );

  const preferredVillaAvailable =
    preferredVillaId && guestNumber <= Number(preferredVilla?.capacity || 0)
      ? availability?.available_villa_ids?.includes(
          preferredVillaId
        )
      : null;

  return (
    <main
      className="booking-page"
      style={{
        "--booking-bg-image": `url("${BOOKING_BACKGROUND_IMAGE}")`,
      }}
    >
      <section className="booking-card">
        <header className="booking-card-header">
          <button
            type="button"
            className="booking-brand"
            onClick={() => navigate("/")}
          >
            <img
              src="/favicon.png"
              alt="The Villa"
            />

            <span>
              <strong>The Villa</strong>
              <small>
                Batangas Private Staycation
              </small>
            </span>
          </button>

          <div className="booking-heading">
            <span>
              Secure online reservation
            </span>
            <h1>{stepTitle}</h1>
          </div>

          <button
            type="button"
            className="booking-home-button"
            onClick={() => navigate("/")}
          >
            <FaHome />
            <span>Home</span>
          </button>
        </header>

        <ProgressSteps
          currentStep={step}
        />

        <div className="booking-card-body" key={step}>
          {step === 1 && (
            <section className="booking-step availability-step">
              <div className="booking-section-title">
                <div>
                  <h2>
                    Date availability
                  </h2>
                </div>

                <FaCalendarAlt />
              </div>

           

              <div className="booking-availability-toolbar">
                <Field
                  label="Guests"
                  icon={FaUsers}
                  required
                >
                  <div className="booking-guest-combobox" onBlur={(event) => {
                    if (!event.currentTarget.contains(event.relatedTarget)) setGuestOptionsOpen(false);
                  }}>
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      autoComplete="off"
                      required
                      id="guestCount"
                      name="guestCount"
                      role="combobox"
                      aria-label={`Number of guests, choose or type 1 to ${maxGuestCount}`}
                      aria-expanded={guestOptionsOpen}
                      aria-invalid={Boolean(guestCountError)}
                      aria-describedby={guestCountError ? "booking-guest-error" : undefined}
                      aria-controls="booking-guest-options"
                      aria-autocomplete="list"
                      aria-activedescendant={guestOptionsOpen ? `booking-guest-option-${activeGuestOption}` : undefined}
                      value={form.guestCount}
                      onChange={(event) => updateForm("guestCount", event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                          event.preventDefault();
                          setGuestOptionsOpen(true);
                          setActiveGuestOption((index) => guestOptionsOpen
                            ? (index + (event.key === "ArrowDown" ? 1 : -1) + GUEST_OPTIONS.length) % GUEST_OPTIONS.length
                            : Math.max(0, GUEST_OPTIONS.indexOf(Number(form.guestCount))));
                        } else if (event.key === "Enter" && guestOptionsOpen) {
                          event.preventDefault();
                          updateForm("guestCount", String(GUEST_OPTIONS[activeGuestOption]));
                          setGuestOptionsOpen(false);
                        } else if (event.key === "Escape") {
                          setGuestOptionsOpen(false);
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="booking-guest-toggle"
                      aria-label="Show guest counts"
                      aria-expanded={guestOptionsOpen}
                      aria-controls="booking-guest-options"
                      onClick={() => {
                        setActiveGuestOption(Math.max(0, GUEST_OPTIONS.indexOf(Number(form.guestCount))));
                        setGuestOptionsOpen((open) => !open);
                        document.getElementById("guestCount")?.focus();
                      }}
                    ><span aria-hidden="true">▾</span></button>
                    {guestOptionsOpen && <div id="booking-guest-options" className="booking-guest-options" role="listbox" aria-label="Guest counts">
                      {GUEST_OPTIONS.map((count, index) => (
                        <button
                          type="button"
                          role="option"
                          id={`booking-guest-option-${index}`}
                          key={count}
                          tabIndex={-1}
                          aria-selected={Number(form.guestCount) === count}
                          className={index === activeGuestOption ? "is-active" : ""}
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => {
                            updateForm("guestCount", String(count));
                            setGuestOptionsOpen(false);
                            document.getElementById("guestCount")?.focus();
                          }}
                        >{count} {count === 1 ? "Guest" : "Guests"}</button>
                      ))}
                    </div>}
                  </div>
                  {guestCountError && <small id="booking-guest-error" className="booking-guest-error" role="alert">{guestCountError}</small>}
                </Field>

                <Field
                  label="Check-in time"
                  icon={FaClock}
                  required
                >
                  <input type="text" value="3:00 PM" readOnly aria-label="Fixed check-in time" />
                </Field>

                <div className="booking-field booking-selected-date-field">
                  <span className="booking-field-label"><FaCalendarAlt /> Selected date</span>
                  <div className="booking-selected-date-chip">
                    <strong>{formatDate(form.checkInDate)}</strong>
                  </div>
                </div>
              </div>

              <AvailabilityCalendar
                guestCount={
                  form.guestCount
                }
                selectedDate={
                  form.checkInDate
                }
                preferredVillaId={guestNumber <= Number(preferredVilla?.capacity || 0) ? preferredVillaId : ""}
                onSelectDate={(date) =>
                  updateForm(
                    "checkInDate",
                    date
                  )
                }
              />

            </section>
          )}

          {step === 2 && (
            <section className="booking-step villa-step">
              <div className="booking-section-title">
                <div>
                  <h2>
                    Choose your villa
                  </h2>
                </div>

                <FaHome />
              </div>

              <div className="booking-selection-summary">
                <span>
                  <FaCalendarAlt />
                  {formatDate(
                    form.checkInDate
                  )}
                </span>

                <span>
                  <FaUsers />
                  {form.guestCount}{" "}
                  {Number(
                    form.guestCount
                  ) === 1
                    ? "guest"
                    : "guests"}
                </span>

                <span>
                  <FaClock />
                  {form.checkInTime}
                </span>

                <button
                  type="button"
                  onClick={() => runStepTransition(1, "Returning to date selection…")}
                >
                  Change
                </button>
              </div>

              {preferredVilla &&
              preferredVillaAvailable ===
                false ? (
                <div className="booking-preferred-warning">
                  <FaExclamationTriangle />

                  <div>
                    <strong>
                      Your preferred villa is
                      unavailable on this date.
                    </strong>
                    <div className="booking-preferred-copy">
                      {preferredVilla.title} was saved
                      from the Villas page, but it is
                      currently booked or cannot
                      accommodate this stay. Please
                      choose another available villa.
                    </div>
                  </div>
                </div>
              ) : null}

              <div
                className="booking-multi-villa-notice"
              >
                <strong>{guestNumber} guests · {canFitGuests ? minimumVillaCount : "No"} {minimumVillaCount === 1 ? "villa" : "villas"} required</strong>
                <span>{selectedVillas.length} selected · {combinedCapacity} spaces · {money(totalAmount)}</span>
                {!selectionValid && <small>{canFitGuests ? "Choose an available villa to meet the capacity." : "Not enough villas available."}</small>}
              </div>
              <div className="booking-villa-grid">
                {visibleVillas.map(
                  (villa) => {
                    const available = villa.available === true;
                    const selected = selectedVillaIds.includes(villa.id);
                    const canSelect = canAddVilla(villa, selectableVillas, selectedVillaIds, guestNumber, minimumVillaCount);
                    const locked = !selected && !canSelect;

                    const preferred =
                      villa.id ===
                      preferredVillaId;

                    const recentlyViewed =
                      !preferred &&
                      villa.id ===
                        recentlyViewedVillaId;

                    return (
                      <button
                        type="button"
                        key={villa.id}
                        className={`booking-villa-card ${
                          selected
                            ? "selected"
                            : ""
                        } ${
                          preferred
                            ? "preferred"
                            : ""
                        } ${
                          recentlyViewed
                            ? "recently-viewed"
                            : ""
                        } ${
                          locked ? "unavailable" : ""
                        }`}
                        disabled={locked || catalogLoading}
                        onClick={() => toggleVilla(villa.id)}
                      >
                        <div className="booking-villa-photo">
                          <img
                            src={villa.image}
                            alt={villa.title}
                          />

                          {preferred ? (
                            <span className="booking-preferred-badge">
                              Selected on Villas page
                            </span>
                          ) : recentlyViewed ? (
                            <span className="booking-recent-badge">
                              Recently viewed
                            </span>
                          ) : null}

                          {selected ? (
                            <span className="booking-selected-badge">
                              <FaCheck />
                              Selected
                            </span>
                          ) : null}
                        </div>

                        <div className="booking-villa-copy">
                          <div className="booking-villa-title-row">
                            <div>
                              <h3>
                                {villa.title}
                              </h3>
                              <small>
                                Up to{" "}
                                {
                                  villa.capacity
                                }{" "}
                                guests
                              </small>
                            </div>

                            <strong>
                              {money(
                                villa.price
                              )}
                            </strong>
                          </div>

                          {/* Villa details are available on the Villas page. */}

                          <div className="booking-villa-amenities">
                            {villa.amenities
                              .slice(0, 4)
                              .map(
                                (
                                  amenity
                                ) => (
                                  <span
                                    key={
                                      amenity
                                    }
                                  >
                                    <FaCheck />
                                    {
                                      amenity
                                    }
                                  </span>
                                )
                              )}
                          </div>

                          <div className="booking-villa-status">
                            {selected ? <><FaCheckCircle /> Selected</> : locked ?
                              <><FaExclamationTriangle /> {available ? combinedCapacity >= guestNumber ? "Capacity reached" : Number(villa.capacity) < guestNumber && minimumVillaCount === 1 ? "Too small" : "Not needed" : villa.unavailableReason}</> :
                              <><FaCheckCircle /> Available</>}
                          </div>
                        </div>
                      </button>
                    );
                  }
                )}
              </div>

              {availabilityLoading ? (
                <div className="booking-inline-loading">
                  <BookingSpinner compact />

                </div>
              ) : null}
            </section>
          )}

          {step === 3 && (
            <section className="booking-step personal-step">
              <div className="booking-section-title">
                <div>
                  <h2>
                    Personal information
                  </h2>
                </div>

                <FaUser />
              </div>

              {preferredVilla ? (
  <div className="booking-preference-strip">
    <img
      src={preferredVilla.image}
      alt={preferredVilla.title}
    />

    <span>
      <small>Selected Villa</small>
      <strong>{preferredVilla.title}</strong>
    </span>
  </div>
) : null}

              <div className="booking-form-grid two-columns">
                <Field
                  label="First name"
                  icon={FaUser}
                  required
                >
                  <input
                    type="text"
                    autoComplete="given-name"
                    value={form.firstName}
                    onChange={(event) =>
                      updatePersonName(
                        "firstName",
                        event.target.value
                      )
                    }
                    placeholder="First name"
                  />
                </Field>

                <Field
                  label="Last name"
                  icon={FaUser}
                  required
                >
                  <input
                    type="text"
                    autoComplete="family-name"
                    value={form.lastName}
                    onChange={(event) =>
                      updatePersonName(
                        "lastName",
                        event.target.value
                      )
                    }
                    placeholder="Last name"
                  />
                </Field>

                <Field
                  label="Email address"
                  icon={FaEnvelope}
                  required
                >
                  <input
                    type="email"
                    autoComplete="email"
                    value={form.email}
                    onChange={(event) =>
                      updateForm(
                        "email",
                        event.target.value
                      )
                    }
                    placeholder="you@example.com"
                  />
                </Field>

                <Field
                  label="Mobile number"
                  icon={FaPhoneAlt}
                  required
                  helper="Philippine mobile number, e.g. 09123456789"
                >
                  <input
                    type="tel"
                    autoComplete="tel"
                    value={form.phone}
                    onChange={(event) =>
                      updateForm(
                        "phone",
                        event.target.value
                      )
                    }
                    placeholder="0912 345 6789"
                  />
                </Field>
              </div>

            </section>
          )}

          {step === 4 && (
            <section className="booking-step payment-step">
              <div className="booking-payment-main">
                <div className="booking-section-title">
                  <div>
                    <h2>
                      Payment
                    </h2>
                  </div>

                  <FaCreditCard />
                </div>

                <div className="booking-payment-choice-grid">
                  <button
                    type="button"
                    className={
                      paymentChoice ===
                      "half"
                        ? "selected"
                        : ""
                    }
                    onClick={() =>
                      setPaymentChoice(
                        "half"
                      )
                    }
                  >
                    <span>
                      50% downpayment
                    </span>
                    <strong>
                      {money(
                        Math.ceil(
                          totalAmount *
                            0.5
                        )
                      )}
                    </strong>
                    <small>
                      Pay the remaining balance later.
                    </small>
                  </button>

                  <button
                    type="button"
                    className={
                      paymentChoice ===
                      "full"
                        ? "selected"
                        : ""
                    }
                    onClick={() =>
                      setPaymentChoice(
                        "full"
                      )
                    }
                  >
                    <span>
                      Full payment
                    </span>
                    <strong>
                      {money(
                        totalAmount
                      )}
                    </strong>
                    <small>
                      Settle the full villa amount now.
                    </small>
                  </button>
                </div>

                <div className="booking-section-title small">
                  <div>
                    <h2>
                      Payment method
                    </h2>
                  </div>
                </div>

                <div className="booking-payment-method-grid">
                  {PAYMENT_METHODS.map((method) => (
                    <button
                      type="button"
                      key={method.id}
                      aria-label={`Pay with ${method.title}`}
                      aria-pressed={paymentMethod === method.id}
                      className={`booking-wallet-tile ${method.id} ${paymentMethod === method.id ? "selected" : ""}`}
                      onClick={() => setPaymentMethod(method.id)}
                    >
                      <span className="booking-wallet-top">
                        <span className={`booking-wallet-logo-frame ${method.id === "debit" ? "card-networks" : ""}`}>
                          {method.logos.map((logo) => (
                            <img
                              className="booking-wallet-logo"
                              key={logo.src}
                              src={logo.src}
                              alt={logo.alt}
                            />
                          ))}
                        </span>
                        {paymentMethod === method.id && <FaCheckCircle />}
                      </span>
                      <span className="booking-wallet-name">
                        <strong>{method.title}</strong>
                        <small>{method.id === "debit" ? "Visa / Mastercard" : method.id === "qrph" ? "Scan with a bank app" : "E-wallet"}</small>
                      </span>
                    </button>
                  ))}
                </div>

              </div>

              <aside className="booking-summary">
                <span className="booking-summary-label">
                  Reservation summary
                </span>

                {selectedVillas.length ? (
                  <div className="booking-summary-villa">
                    <img
                      src={
                        selectedVillas[0].image
                      }
                      alt={
                        selectedVillas.map((v) => v.title).join(", ")
                      }
                    />

                    <div>
                      <strong>
                        {
                          selectedVillas.map((v) => v.title).join(", ")
                        }
                      </strong>
                      <small>
                        Up to{" "}
                        {
                          combinedCapacity
                        }{" "}
                        guests
                      </small>
                    </div>
                  </div>
                ) : null}

                <dl>
                  <div>
                    <dt>
                      Guest
                    </dt>
                    <dd>
                      {form.firstName}{" "}
                      {form.lastName}
                    </dd>
                  </div>

                  <div>
                    <dt>
                      Date
                    </dt>
                    <dd>
                      {formatDate(
                        form.checkInDate
                      )}
                    </dd>
                  </div>

                  <div>
                    <dt>
                      Check-in
                    </dt>
                    <dd>
                      {form.checkInTime}
                    </dd>
                  </div>

                  <div>
                    <dt>
                      Guests
                    </dt>
                    <dd>
                      {form.guestCount}
                    </dd>
                  </div>

                  <div>
                    <dt>
                      Villa total
                    </dt>
                    <dd>
                      {money(
                        totalAmount
                      )}
                    </dd>
                  </div>

                  <div className="due">
                    <dt>
                      Due now
                    </dt>
                    <dd>
                      {money(
                        amountDue
                      )}
                    </dd>
                  </div>

                  {paymentChoice ===
                  "half" ? (
                    <div>
                      <dt>
                        Remaining
                      </dt>
                      <dd>
                        {money(
                          remainingBalance
                        )}
                      </dd>
                    </div>
                  ) : null}
                </dl>

                <div className="booking-secure-note">
                  <FaShieldAlt />

                  <span>
                    <strong>
                      Secure checkout
                    </strong>
                    <small>
                      Payment is processed through
                      PayMongo.
                    </small>
                  </span>
                </div>
              </aside>
              <div className="booking-payment-consent">
                <div className="booking-payment-privacy">
                  <FaShieldAlt aria-hidden="true" />
                  <div>
                    <strong>Data privacy &amp; secure payment</strong>
                    <p>We use your personal information to manage your reservation and stay. Review your reservation and payment amount before continuing to secure checkout.</p>
                  </div>
                </div>

                <label className="booking-policy-check">
                  <input
                    type="checkbox"
                    checked={
                      acceptedPolicy
                    }
                    onChange={(
                      event
                    ) =>
                      setAcceptedPolicy(
                        event.target
                          .checked
                      )
                    }
                  />

                  <span>
                    I confirm that the guest details,
                    selected date, villa, payment option,
                    and reservation information are
                    correct.
                  </span>
                </label>
              </div>
            </section>
          )}

          {step === 5 && (
            <section className="booking-step confirmation-step">
              <div className="booking-thankyou-card">
              <img className="booking-thankyou-logo" src="/favicon.png" alt="The Villa" />
              <div
                className={`booking-result-icon ${
                  paymentResult?.state ===
                  "paid"
                    ? "success"
                    : paymentResult?.state ===
                        "cancelled"
                      ? "warning"
                      : ""
                }`}
              >
                {paymentResult?.state ===
                "paid" ? (
                  <FaCheck />
                ) : paymentResult?.state ===
                  "cancelled" ? (
                  <FaExclamationTriangle />
                ) : (
                  <FaClock />
                )}
              </div>

              <span className="booking-result-kicker">
                {paymentResult?.state ===
                "paid"
                  ? "Reservation confirmed"
                  : paymentResult?.state ===
                      "cancelled"
                    ? "Payment cancelled"
                    : "Payment status"}
              </span>

              <h2>
                {paymentResult?.state ===
                "paid"
                  ? "Thank you for choosing The Villa."
                  : paymentResult?.state ===
                      "cancelled"
                    ? "Your reservation was released."
                    : "We are checking your reservation."}
              </h2>

              <div className="booking-confirmation-message">
                {paymentResult?.state === "paid"
                  ? "Your stay is confirmed. We look forward to welcoming you for a relaxing escape and wonderful memories."
                  : paymentResult?.message || "Your reservation details will appear here after payment processing."}
              </div>

              {createdBooking?.booking_code ? (
                <div className="booking-reference">
                  <span>
                    Booking reference
                  </span>
                  <strong>
                    {
                      createdBooking.booking_code
                    }
                  </strong>
                  <small>
                    Keep this reference handy for your stay.
                  </small>
                </div>
              ) : null}

              <div className="booking-confirmation-buttons">
                <button
                  type="button"
                  onClick={() =>
                    navigate("/")
                  }
                >
                  <FaHome />
                  Return home
                </button>

                <button
                  type="button"
                  className="secondary"
                  onClick={() => runStepTransition(
                    1,
                    "Preparing a new reservation…",
                    () => { resetForm(); return true; }
                  )}
                >
                  Book another stay
                </button>
              </div>
              </div>
            </section>
          )}
        </div>

        {step < 5 && (
          <footer className="booking-card-footer">
            <button
              type="button"
              className="booking-back-button"
              disabled={loading || stepTransition.active}
              onClick={() => {
                if (step === 1) {
                  navigate("/");
                  return;
                }

                runStepTransition(step - 1, "Returning to the previous step…");
              }}
            >
              <FaArrowLeft />
              {step === 1
                ? "Cancel"
                : "Back"}
            </button>

            {step === 1 && (
              <button
                type="button"
                className="booking-next-button"
                onClick={
                  continueFromAvailability
                }
                disabled={
                  !form.checkInDate ||
                  availabilityLoading ||
                  stepTransition.active || loading
                }
              >
                Continue
                <FaArrowRight />
              </button>
            )}

            {step === 2 && (
              <button
                type="button"
                className="booking-next-button"
                onClick={
                  continueFromVilla
                }
                disabled={
                  !selectionValid ||
                  stepTransition.active || loading
                }
              >
                Choose villa
                <FaArrowRight />
              </button>
            )}

            {step === 3 && (
              <button
                type="button"
                className="booking-next-button"
                onClick={
                  continueFromPersonalInfo
                }
                disabled={
                  !selectionValid ||
                  availabilityLoading ||
                  stepTransition.active || loading
                }
              >
                Continue
                <FaArrowRight />
              </button>
            )}

            {step === 4 && (
              <button
                type="button"
                className="booking-next-button"
                onClick={
                  confirmBooking
                }
                disabled={
                  !acceptedPolicy ||
                  loading || stepTransition.active
                }
              >
                Confirm and pay
                <FaArrowRight />
              </button>
            )}
          </footer>
        )}
      </section>

      <MessageModal
        message={message}
        onClose={() =>
          setMessage("")
        }
      />

      {(loading || stepTransition.active) && (
        <LoadingOverlay
          message={loading ? loadingMessage : stepTransition.message}
        />
      )}
    </main>
  );
}
