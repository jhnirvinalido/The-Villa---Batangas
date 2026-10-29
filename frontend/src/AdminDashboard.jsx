import { AlertMessage, ConfirmSignOut, LoadingScreen } from "./SystemFeedback";
import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import { singleFlightRefresh } from "./liveTransport.mjs";
import useLiveUpdates from "./useLiveUpdates";
import { snapshotRows } from "./dashboardSnapshot.mjs";
import React from "react";
import VillaMaintenance from "./VillaMaintenance";
import AdminGuestFeedback from "./AdminGuestFeedback";
import { MAINTENANCE_SOURCE } from "./maintenanceModel.mjs";
import { normalizeVillaCatalogRow } from "./villaCatalogModel.mjs";
import {
  AlertCircle,
  Banknote,
  Bell,
  CalendarDays,
  Check,
  CheckCircle2,
  Copy,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Clock3,
  Eye,
  Filter,
  History,
  Home,
  ImagePlus,
  LoaderCircle,
  LogOut,
  Menu,
  MessageCircle,
  KeyRound,
  Mail,
  Power,
  Send,
  UserCog,
  UserPlus,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Printer,
  QrCode,
  ReceiptText,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserRound,
  Users,
  WalletCards,
  Wrench,
  Percent,
  CreditCard,
  UserCheck,
  X,
} from "lucide-react";
import Chart from "chart.js/auto";
import "./AdminDashboard.css";
import AdminTaskHub from "./AdminTaskHub";
import "./StaffFlow.css";
import "./AdminTaskHub.css";
import AssignmentReview from "./AssignmentReview";
import ManualBooking from "./ManualBooking";
import { ProfilePhoto } from "./ProfileIdentity";

// ============================================================
// STORAGE / SHARED DATA
// ============================================================
const STORAGE_KEYS = {
  BOOKINGS: "theVillaConfirmedBookings",
  TASKS: "theVillaStaffTasks",
  NOTIFICATIONS: "theVillaAdminNotifications",
  STAFF_NOTIFICATIONS: "theVillaStaffNotifications",
  ADMIN_AUTH: "theVillaPortalAuth",
  PAYMENT_TRANSACTIONS: "theVillaPaymentTransactions",
  STAFF_DIRECTORY: "theVillaStaffDirectory",
  BOOKING_HISTORY: "theVillaBookingHistory",
};

const DEFAULT_ADMIN = {
  id: "ADMIN-001",
  name: "Villa Administrator",
  role: "Administrator",
  department: "Villa Operations",
  email: "admin@thevilla.ph",
  online: true,
};

// Same staff IDs used by the Staff Dashboard / Team Hub.
const STAFF_DIRECTORY = [
  {
    id: "ST-001",
    name: "Maria Santos",
    role: "Housekeeping Staff",
    department: "Housekeeping",
    shift: "6:00 AM – 3:00 PM",
    email: "maria.santos@thevilla.ph",
    online: true,
  },
  {
    id: "ST-002",
    name: "Jose Ramirez",
    role: "Maintenance Technician",
    department: "Maintenance",
    shift: "7:00 AM – 4:00 PM",
    email: "jose.ramirez@thevilla.ph",
    online: true,
  },
  {
    id: "ST-003",
    name: "Anna Cruz",
    role: "Guest Services Associate",
    department: "Guest Services",
    shift: "9:00 AM – 6:00 PM",
    email: "anna.cruz@thevilla.ph",
    online: true,
  },
  {
    id: "ST-004",
    name: "Carlo Mendoza",
    role: "Security Officer",
    department: "Security",
    shift: "6:00 PM – 3:00 AM",
    email: "carlo.mendoza@thevilla.ph",
    online: false,
  },
  {
    id: "ST-005",
    name: "Liza Flores",
    role: "Food & Beverage Staff",
    department: "F&B",
    shift: "10:00 AM – 7:00 PM",
    email: "liza.flores@thevilla.ph",
    online: true,
  },
  {
    id: "ST-006",
    name: "Paolo Reyes",
    role: "Landscaping Staff",
    department: "Landscaping",
    shift: "6:00 AM – 3:00 PM",
    email: "paolo.reyes@thevilla.ph",
    online: true,
  },
  {
    id: "ST-007",
    name: "Ella Garcia",
    role: "Administrative Assistant",
    department: "Administration",
    shift: "8:00 AM – 5:00 PM",
    email: "ella.garcia@thevilla.ph",
    online: true,
  },
];


function normalizeStaffAccount(staff, index = 0) {
  const email = String(staff?.email || "").trim().toLowerCase();
  const generatedUsername =
    String(staff?.username || email.split("@")[0] || `staff${index + 1}`)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]/g, "") || `staff${index + 1}`;

  return {
    ...staff,
    id: staff?.id || `ST-${String(index + 1).padStart(3, "0")}`,
    name: staff?.name || "Villa Staff",
    role: staff?.role || "Staff Member",
    department: staff?.department || "Administration",
    shift: staff?.shift || "8:00 AM – 5:00 PM",
    email: email || `staff${index + 1}@thevilla.ph`,
    username: generatedUsername,
    online: !!staff?.online,
    accountStatus:
      String(staff?.accountStatus || staff?.account_status || "Active") ===
      "Disabled"
        ? "Disabled"
        : "Active",
    mustChangePassword:
      staff?.mustChangePassword ?? staff?.must_change_password ?? false,
    lastLogin: staff?.lastLogin || staff?.last_login || "",
    createdAt: staff?.createdAt || staff?.created_at || new Date().toISOString(),
    updatedAt: staff?.updatedAt || staff?.updated_at || "",
  };
}

function getStoredStaffDirectory() {
  const stored = readStorage(STORAGE_KEYS.STAFF_DIRECTORY, []);
  const source = Array.isArray(stored) && stored.length ? stored : STAFF_DIRECTORY;
  const normalized = source.map(normalizeStaffAccount);
  writeStorage(STORAGE_KEYS.STAFF_DIRECTORY, normalized);
  return normalized;
}

function emptyStaffAccountForm() {
  return {
    id: "",
    name: "",
    email: "",
    username: "",
    role: "",
    department: "Housekeeping",
    shift: "8:00 AM – 5:00 PM",
    accountStatus: "Active",
    mustChangePassword: true,
  };
}

const DEPARTMENTS = [
  "Housekeeping",
  "Maintenance",
  "Guest Services",
  "F&B",
  "Security",
  "Landscaping",
  "Administration",
];

const PRIORITIES = ["High", "Medium", "Low"];
const ASSIGNMENT_STATUSES = [
  "Pending",
  "In Progress",
  "Pending Review",
  "Completed",
];

// Booking-based assignment presets for all staff departments.
const ASSIGNMENT_TEMPLATES = [
  {
    id: "housekeeping-pre-arrival",
    label: "Pre-arrival Housekeeping",
    department: "Housekeeping",
    priority: "High",
    dueMode: "checkIn",
    title: "Pre-arrival housekeeping preparation",
    description:
      "Prepare the assigned villa before guest arrival. Complete cleaning, linen replacement, bathroom sanitation, amenities restocking, and a final condition check.",
    checklist: [
      "Replace bed linens and towels",
      "Clean and sanitize bathrooms",
      "Vacuum and mop all floors",
      "Dust furniture and fixtures",
      "Restock toiletries and guest amenities",
      "Empty waste bins",
      "Report damages or missing items",
    ],
  },
  {
    id: "housekeeping-turnover",
    label: "Post-checkout Turnover",
    department: "Housekeeping",
    priority: "High",
    dueMode: "checkOut",
    title: "Post-checkout villa turnover",
    description:
      "Complete a full turnover after guest departure and prepare the villa for the next reservation.",
    checklist: [
      "Collect used linens and towels",
      "Deep-clean bedrooms and bathrooms",
      "Clean kitchen and dining areas",
      "Inspect guest-use items",
      "Restock supplies",
      "Document damages or missing items",
    ],
  },
  {
    id: "maintenance-inspection",
    label: "Villa Equipment Inspection",
    department: "Maintenance",
    priority: "High",
    dueMode: "checkIn",
    title: "Pre-arrival villa equipment inspection",
    description:
      "Inspect electricity, water, air-conditioning, locks, Wi-Fi, television, pool equipment, and outdoor lighting before the booking check-in.",
    checklist: [
      "Test electricity and lighting",
      "Check water pressure and drainage",
      "Test air-conditioning units",
      "Inspect doors, locks, and windows",
      "Test Wi-Fi and television",
      "Inspect pool equipment and outdoor lights",
      "Submit inspection notes",
    ],
  },
  {
    id: "guest-services-arrival",
    label: "Guest Arrival Preparation",
    department: "Guest Services",
    priority: "High",
    dueMode: "checkIn",
    title: "Guest arrival and welcome preparation",
    description:
      "Verify arrival details, prepare the welcome kit, review special requests, and coordinate the guest greeting and villa orientation.",
    checklist: [
      "Confirm arrival time and contact details",
      "Prepare welcome kit",
      "Review guest special requests",
      "Coordinate villa readiness with departments",
      "Prepare villa orientation details",
      "Follow up after guest arrival",
    ],
  },
  {
    id: "fb-service",
    label: "Food and Beverage Preparation",
    department: "F&B",
    priority: "Medium",
    dueMode: "checkIn",
    title: "Guest food and beverage preparation",
    description:
      "Review guest preferences and prepare requested food, drinks, dining setup, or welcome refreshments for the booking.",
    checklist: [
      "Review dietary preferences and allergies",
      "Prepare requested ingredients",
      "Prepare welcome refreshments",
      "Set up dining or service area",
      "Verify food safety and cleanliness",
      "Coordinate service time",
    ],
  },
  {
    id: "security-arrival",
    label: "Security Arrival Check",
    department: "Security",
    priority: "Medium",
    dueMode: "checkIn",
    title: "Booking security and access preparation",
    description:
      "Confirm guest access details, inspect entry points, review CCTV coverage, and prepare the arrival security log.",
    checklist: [
      "Verify booking and guest access list",
      "Inspect gates and entry points",
      "Check locks and exterior lighting",
      "Review CCTV status",
      "Prepare security log entry",
      "Brief the next duty officer",
    ],
  },
  {
    id: "landscaping-pre-arrival",
    label: "Grounds Preparation",
    department: "Landscaping",
    priority: "Medium",
    dueMode: "checkIn",
    title: "Villa grounds and garden preparation",
    description:
      "Prepare the outdoor areas, gardens, walkways, and villa surroundings before guest arrival.",
    checklist: [
      "Trim lawns and hedges",
      "Remove weeds and debris",
      "Water plants where required",
      "Inspect irrigation",
      "Clean walkways and outdoor areas",
      "Report damaged plants or fixtures",
    ],
  },
  {
    id: "admin-booking",
    label: "Booking Administration Follow-up",
    department: "Administration",
    priority: "Medium",
    dueMode: "checkIn",
    title: "Booking document and guest record follow-up",
    description:
      "Review booking documents, update internal records, verify guest details, and coordinate outstanding administrative requirements.",
    checklist: [
      "Review booking record",
      "Verify guest contact information",
      "Check payment and document status",
      "Update internal records",
      "Send required communication",
      "Report outstanding requirements",
    ],
  },
  {
    id: "custom",
    label: "Custom Booking Assignment",
    department: "Administration",
    priority: "Medium",
    dueMode: "checkIn",
    title: "",
    description: "",
    checklist: [],
  },
];

const SIDEBAR_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: Home, section: "Overview" },
  { id: "bookings", label: "Bookings", icon: CalendarDays, section: "Overview" },
  { id: "manualBooking", label: "Manual Booking", icon: UserPlus, section: "Overview" },
  { id: "villas", label: "Villas & Pricing", icon: SlidersHorizontal, section: "Content" },
  { id: "assignmentMonitor", label: "Assignment Monitor", icon: ClipboardList, section: "Operations" },
  { id: "history", label: "Booking History", icon: History, section: "Operations" },
  { id: "guestFeedback", label: "Guest Feedback", icon: MessageCircle, section: "Operations" },
  { id: "staff", label: "Staff Directory", icon: Users, section: "People" },
];

const VIEW_META = {
  guestFeedback: { title: "Guest Feedback", description: "Verified post-stay guest reviews." },
  dashboard: {
    title: "Admin Dashboard",
    description: "A clear overview of your reservations, property operations, and guest balances.",
  },
  manualBooking: { title: "Manual Booking", description: "" },
  bookings: {
    title: "Bookings",
    description: "",
  },
  villas: {
    title: "Villas & Pricing",
    description:
      "Manage villa pricing, maintenance, inspections and readiness for guest bookings.",
  },
  history: {
    title: "Booking History",
    description: "View completed guest stays including completed check-ins and check-outs.",
  },
  assignmentMonitor: {
    title: "Assignment Monitor",
    description: "Monitor automatic booking preparation, staffing gaps, staff progress and readiness approvals.",
  },
  staff: {
    title: "Staff Directory",
    description: "Manage staff profiles, login accounts, access status, shifts, and workloads.",
  },
  payments: {
    title: "Front Desk Payments",
    description: "Review the booking first, then complete the remaining balance through Cash or PayMongo QRPh.",
  },
  notifications: {
    title: "Notifications",
    description: "Review new assignment, booking, and approval alerts.",
  },
  profile: {
    title: "My Profile",
    description: "Your administrator account information.",
  },
};

const API_BASE_URL = (
  (typeof window !== "undefined" && window.__THE_VILLA_API_BASE__) ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const FRONT_DESK_PAYMENT_METHODS = [
  {
    id: "Cash",
    label: "Cash",
    description: "Enter the total cash handed by the customer. Change is calculated automatically.",
    icon: Banknote,
  },
  {
    id: "QRPh",
    label: "QRPh",
    description: "Generate a single-use PayMongo QRPh code for the exact remaining balance.",
    icon: QrCode,
  },
];


// ============================================================
// HELPERS
// ============================================================
function readStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Keep the dashboard usable if storage is unavailable.
  }
}

function readCookie(name) {
  if (typeof document === "undefined") return "";
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || "";
}

const PORTAL_AUTH_STORAGE_KEY =
  "theVillaPortalAuth";

const LEGACY_PORTAL_KEYS = [
  "theVillaAdminAuth",
  "theVillaStaffAuth",
  "theVillaAuthToken",
  "theVillaApiToken",
  "theVillaRefreshToken",
];

const INVALID_PORTAL_TOKEN_VALUES =
  new Set([
    "",
    "undefined",
    "null",
    "none",
  ]);

function normalizePortalToken(value) {
  if (typeof value !== "string") {
    return "";
  }

  const normalized =
    value.trim();

  if (
    INVALID_PORTAL_TOKEN_VALUES.has(
      normalized.toLowerCase()
    )
  ) {
    return "";
  }

  return normalized;
}

function getPortalStorage() {
  const sessionRaw =
    sessionStorage.getItem(
      PORTAL_AUTH_STORAGE_KEY
    );

  if (sessionRaw) {
    return {
      storage:
        sessionStorage,
      raw:
        sessionRaw,
    };
  }

  const localRaw =
    localStorage.getItem(
      PORTAL_AUTH_STORAGE_KEY
    );

  if (localRaw) {
    return {
      storage:
        localStorage,
      raw:
        localRaw,
    };
  }

  return {
    storage:
      sessionStorage,
    raw:
      "",
  };
}

function getPortalAuth() {
  const { raw } =
    getPortalStorage();

  if (!raw) {
    return {};
  }

  try {
    const auth =
      JSON.parse(raw);

    return (
      auth &&
      typeof auth === "object"
        ? auth
        : {}
    );
  } catch {
    clearPortalAuth({
      redirect: false,
    });

    return {};
  }
}

function clearPortalAuth({
  redirect = true,
} = {}) {
  localStorage.removeItem(
    PORTAL_AUTH_STORAGE_KEY
  );

  sessionStorage.removeItem(
    PORTAL_AUTH_STORAGE_KEY
  );

  LEGACY_PORTAL_KEYS.forEach(
    (key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    }
  );

  if (
    redirect &&
    typeof window !==
      "undefined" &&
    window.location.pathname !==
      "/admin-login"
  ) {
    window.location.replace("/admin-login");
  }
}

function getPortalAccessToken() {
  const auth =
    getPortalAuth();

  return normalizePortalToken(
    auth?.access_token
  );
}

function getPortalRefreshToken() {
  const auth =
    getPortalAuth();

  return normalizePortalToken(
    auth?.refresh_token
  );
}

function savePortalAuth(payload) {
  const current =
    getPortalAuth();

  const accessToken =
    normalizePortalToken(
      payload?.access_token
    );

  const refreshToken =
    normalizePortalToken(
      payload?.refresh_token
    );

  if (
    !accessToken ||
    !refreshToken
  ) {
    clearPortalAuth();

    throw new Error(
      "The refreshed portal session is incomplete."
    );
  }

  const nextAuth = {
    ...current,
    ...payload,

    authenticated: true,

    user:
      payload?.user ||
      current?.user,

    role:
      payload?.user?.role ||
      payload?.role ||
      current?.role,

    access_token:
      accessToken,

    refresh_token:
      refreshToken,
  };

  const { storage } =
    getPortalStorage();

  localStorage.removeItem(
    PORTAL_AUTH_STORAGE_KEY
  );

  sessionStorage.removeItem(
    PORTAL_AUTH_STORAGE_KEY
  );

  storage.setItem(
    PORTAL_AUTH_STORAGE_KEY,
    JSON.stringify(
      nextAuth
    )
  );

  LEGACY_PORTAL_KEYS.forEach(
    (key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    }
  );

  return nextAuth;
}

let portalRefreshPromise =
  null;

async function refreshPortalSession() {
  if (portalRefreshPromise) {
    return portalRefreshPromise;
  }

  portalRefreshPromise =
    (async () => {
      const refreshToken =
        getPortalRefreshToken();

      if (!refreshToken) {
        clearPortalAuth();

        throw new Error(
          "Your login session has expired. Please sign in again."
        );
      }

      const response =
        await fetch(
          `${API_BASE_URL}/staff-auth/refresh`,
          {
            method: "POST",
            headers: {
              Accept:
                "application/json",
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              refresh_token:
                refreshToken,
            }),
          }
        );

      const payload =
        await response
          .json()
          .catch(() => ({}));

      if (!response.ok) {
        clearPortalAuth();

        throw new Error(
          payload?.detail ||
            payload?.message ||
            "Your login session has expired. Please sign in again."
        );
      }

      return savePortalAuth(
        payload
      );
    })();

  try {
    return await portalRefreshPromise;
  } finally {
    portalRefreshPromise =
      null;
  }
}


let adminPendingRequestCount = 0;

function dispatchAdminSystemAlert(detail = {}) {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") {
    return;
  }

  window.dispatchEvent(
    new CustomEvent("thevilla:system-alert", {
      detail: {
        type: detail.type || "success",
        title: detail.title || "",
        message: String(detail.message || ""),
      },
    })
  );
}

function beginAdminRequestLoading(message = "Please wait while the request is being processed.") {
  adminPendingRequestCount += 1;

  if (adminPendingRequestCount === 1) {
    dispatchAdminSystemAlert({
      type: "loading",
      title: "Processing...",
      message,
    });
  }
}

function endAdminRequestLoading() {
  adminPendingRequestCount = Math.max(0, adminPendingRequestCount - 1);

  if (adminPendingRequestCount === 0) {
    dispatchAdminSystemAlert({
      type: "close-loading",
    });
  }
}

function inferAdminAlertType(message) {
  const text = String(message || "").trim().toLowerCase();

  const successWords = [
    "completed",
    "success",
    "created",
    "saved",
    "updated",
    "sent",
    "reset",
    "generated",
    "confirmed",
    "approved",
    "verified",
    "checked in",
    "checked out",
    "assigned",
    "added",
    "removed",
    "marked",
    "copied",
    "paid",
  ];

  const errorWords = [
    "error",
    "failed",
    "could not",
    "couldn't",
    "unable",
    "invalid",
    "missing",
    "select ",
    "choose ",
    "enter ",
    "must ",
    "cannot",
    "can't",
    "not available",
    "not found",
    "not confirmed",
    "insufficient",
    "expired",
    "disabled",
    "required",
    "before ",
    "earlier",
    "later",
    "no remaining",
    "not verified",
    "attention",
  ];

  if (successWords.some((word) => text.includes(word))) {
    return "success";
  }

  if (errorWords.some((word) => text.includes(word))) {
    return "error";
  }

  return "error";
}

function getBookingLifecycleDateRestriction(booking, action) {
  if (!booking || action === "check_out") return "";

  const today = todayStr();
  const checkInDate = String(
    booking.checkIn ||
      booking.check_in_date ||
      booking.checkInDate ||
      ""
  ).slice(0, 10);
  const checkOutDate = String(
    booking.checkOut ||
      booking.check_out_date ||
      booking.checkOutDate ||
      ""
  ).slice(0, 10);

  const getExactDateMessage = (label, bookedDate) => {
    const formatted = formatDate(bookedDate, true);

    if (today < bookedDate) {
      return `${label} is not available yet. This booking is scheduled for ${formatted}.`;
    }

    return `${label} is no longer available for today. This booking was scheduled for ${formatted}.`;
  };

  if (action === "check_in") {
    if (!checkInDate) {
      return "Check-in is blocked because this booking has no valid check-in date.";
    }

    if (today !== checkInDate) {
      return getExactDateMessage("Check-in", checkInDate);
    }
  }

  if (action === "check_out") {
    if (!checkOutDate) {
      return "Check-out is blocked because this booking has no valid check-out date.";
    }

    if (today !== checkOutDate) {
      return getExactDateMessage("Check-out", checkOutDate);
    }
  }

  return "";
}

async function apiRequest(
  path,
  options = {},
  allowRefresh = true
) {
  const performRequest =
    async () => {
      const token =
        getPortalAccessToken();

      if (!token) {
        clearPortalAuth();

        throw new Error(
          "Your portal session is missing. Please sign in again."
        );
      }

      const headers = {
        Accept:
          "application/json",

        ...(options.body && !(options.body instanceof FormData)
          ? {
              "Content-Type":
                "application/json",
            }
          : {}),

        Authorization:
          `Bearer ${token}`,

        ...(options.headers ||
          {}),
      };

      return fetch(
        `${API_BASE_URL}${path}`,
        {
          ...options,
          headers,
        }
      );
    };

  let response =
    await performRequest();

  if (
    response.status === 401 &&
    allowRefresh
  ) {
    await refreshPortalSession();

    response =
      await performRequest();
  }

  const payload =
    await response
      .json()
      .catch(() => ({}));

  if (!response.ok) {
    if (
      response.status === 401
    ) {
      clearPortalAuth();
    }

    const validationMessage =
      Array.isArray(
        payload?.detail
      )
        ? payload.detail
            .map(
              (item) =>
                item?.msg
            )
            .filter(Boolean)
            .join(" ")
        : payload?.errors
        ? Object.values(
            payload.errors
          )
            .flat()
            .find(Boolean)
        : "";

    throw new Error(
      validationMessage ||
        payload?.detail ||
        payload?.message ||
        `Request failed with status ${response.status}.`
    );
  }

  return payload;
}

async function copyTextToClipboard(
  value
) {
  const text = String(
    value || ""
  );

  if (!text) {
    return false;
  }

  try {
    if (
      navigator?.clipboard &&
      window.isSecureContext
    ) {
      await navigator.clipboard.writeText(
        text
      );

      return true;
    }
  } catch {
    // Continue to the fallback below.
  }

  try {
    const textarea =
      document.createElement(
        "textarea"
      );

    textarea.value = text;
    textarea.setAttribute(
      "readonly",
      ""
    );

    textarea.style.position =
      "fixed";

    textarea.style.opacity =
      "0";

    textarea.style.pointerEvents =
      "none";

    document.body.appendChild(
      textarea
    );

    textarea.focus();
    textarea.select();

    const copied =
      document.execCommand(
        "copy"
      );

    document.body.removeChild(
      textarea
    );

    return copied;
  } catch {
    return false;
  }
}


function todayStr() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

function addDays(dateString, amount) {
  const date = dateString
    ? new Date(`${dateString}T00:00:00`)
    : new Date();
  date.setDate(date.getDate() + amount);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(dateString, long = false) {
  if (!dateString) return "Not scheduled";
  const date = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateString;
  return date.toLocaleDateString("en-PH", {
    weekday: long ? "short" : undefined,
    month: long ? "long" : "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatRelative(isoString) {
  if (!isoString) return "";
  const milliseconds = Date.now() - new Date(isoString).getTime();
  const minutes = Math.max(0, Math.floor(milliseconds / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days}d ago`;
}

function formatDateTime(isoString) {
  if (!isoString) return "Not recorded";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return String(isoString);
  return date.toLocaleString("en-PH", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function makeReceiptNumber() {
  const date = new Date();
  const datePart = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("");
  const timePart = [
    String(date.getHours()).padStart(2, "0"),
    String(date.getMinutes()).padStart(2, "0"),
    String(date.getSeconds()).padStart(2, "0"),
  ].join("");
  return `TV-FD-${datePart}-${timePart}`;
}

function parseAmount(value) {
  if (typeof value === "number") return value;
  return Number(String(value || "").replace(/[^0-9.-]+/g, "")) || 0;
}

function formatPeso(value) {
  return Number(value || 0).toLocaleString("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 0,
  });
}

function normalizeOtherCharges(booking) {
  const storedCharges =
    booking.other_charges ||
    booking.otherCharges ||
    booking.additional_charges ||
    booking.additionalCharges ||
    booking.folio_charges ||
    booking.folioCharges ||
    booking.front_desk_other_charges ||
    booking.frontDeskOtherCharges ||
    [];

  let rawCharges = storedCharges;
  if (typeof storedCharges === "string") {
    try {
      rawCharges = JSON.parse(storedCharges);
    } catch {
      rawCharges = [];
    }
  }

  if (!Array.isArray(rawCharges)) return [];

  return rawCharges
    .map((charge, index) => {
      const quantity = Math.max(
        parseAmount(charge.quantity ?? charge.qty ?? 1),
        1
      );
      const unitAmount = parseAmount(
        charge.unit_amount ??
          charge.unitAmount ??
          charge.unit_price ??
          charge.unitPrice ??
          charge.price
      );
      const amount =
        parseAmount(charge.amount ?? charge.total) ||
        quantity * unitAmount;
      const status = String(charge.status || "Unpaid").toLowerCase();

      return {
        id: charge.id || `CHARGE-${index + 1}`,
        description:
          charge.description ||
          charge.label ||
          charge.name ||
          "Other charge",
        amount: Math.max(amount, 0),
        status,
      };
    })
    .filter((charge) => charge.amount > 0 && charge.status !== "paid");
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function slug(value) {
  return String(value || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function daysUntil(dateString) {
  if (!dateString) return null;
  const today = new Date(`${todayStr()}T00:00:00`);
  const due = new Date(`${dateString}T00:00:00`);
  return Math.round((due.getTime() - today.getTime()) / 86400000);
}

function displayAssignmentStatus(assignment) {
  if (assignment.status === "Completed") return "Completed";
  if (assignment.status === "Pending Review") return "Pending Review";
  if (assignment.dueDate && daysUntil(assignment.dueDate) < 0) return "Overdue";
  return assignment.status || "Pending";
}

function dueLabel(assignment) {
  const status = displayAssignmentStatus(assignment);
  if (status === "Completed") return "Completed";
  if (status === "Overdue") return "Overdue";
  const difference = daysUntil(assignment.dueDate);
  if (difference === 0) return "Due today";
  if (difference === 1) return "Due tomorrow";
  return difference !== null ? `Due in ${difference} days` : "No due date";
}

function getAdminProfile() {
  const stored = readStorage(STORAGE_KEYS.ADMIN_AUTH, {});
  return {
    ...DEFAULT_ADMIN,
    ...stored,
    role: stored.role || DEFAULT_ADMIN.role,
  };
}

function normalizeBooking(booking) {
  const totalAmount = parseAmount(
    booking.total_amount ?? booking.totalAmount ?? booking.amount
  );
  const amountPaid = parseAmount(
    booking.amount_paid ?? booking.amountPaid ?? booking.paid
  );
  const storedBalance =
    booking.balance_amount ?? booking.balanceAmount ?? booking.balance;
  const balanceAmount =
    storedBalance !== undefined && storedBalance !== null
      ? parseAmount(storedBalance)
      : Math.max(totalAmount - amountPaid, 0);

  const rawPaymentChoice = String(
    booking.payment_choice ||
      booking.paymentChoice ||
      (amountPaid >= totalAmount && totalAmount > 0 ? "full" : "half")
  ).toLowerCase();
  const paymentChoice = rawPaymentChoice.includes("full") ? "full" : "half";
  const requiredDownpayment =
    paymentChoice === "full" ? totalAmount : Math.ceil(totalAmount * 0.5);
  const storedDownpayment = parseAmount(
    booking.downpayment_amount ??
      booking.downpaymentAmount ??
      booking.deposit_amount ??
      booking.depositAmount
  );
  const downpaymentAmount =
    storedDownpayment > 0
      ? storedDownpayment
      : Math.min(amountPaid, requiredDownpayment);
  const downpaymentVerified =
    requiredDownpayment > 0 && amountPaid >= requiredDownpayment;

  const rawHistory = Array.isArray(booking.payment_history)
    ? booking.payment_history
    : Array.isArray(booking.paymentHistory)
    ? booking.paymentHistory
    : Array.isArray(booking.payments)
    ? booking.payments
    : [];

  const paymentHistory = rawHistory.map((payment, index) => ({
    id: payment.id || payment.transaction_id || `PAY-${index + 1}`,
    receiptNumber:
      payment.receipt_number ||
      payment.receiptNumber ||
      payment.reference ||
      payment.reference_number ||
      "",
    amount: parseAmount(payment.amount),
    method: payment.method || payment.payment_method || "Online Payment",
    reference:
      payment.reference ||
      payment.reference_number ||
      payment.transaction_reference ||
      "",
    stage: payment.stage || payment.payment_stage || "Payment",
    processedAt:
      payment.processed_at ||
      payment.processedAt ||
      payment.paid_at ||
      payment.paidAt ||
      payment.created_at ||
      payment.createdAt ||
      "",
    processedBy:
      payment.processed_by ||
      payment.processedBy ||
      payment.cashier ||
      "System",
    source: payment.source || "booking",
    status: payment.status || "Completed",
  }));

  const computedPaymentStatus =
    balanceAmount <= 0 && amountPaid > 0
      ? "Paid"
      : paymentChoice === "half" && downpaymentVerified
      ? "50% Downpayment"
      : amountPaid > 0
      ? "Partial"
      : "Unpaid";

  const otherCharges = normalizeOtherCharges(booking);
  const otherChargesTotal = otherCharges.reduce(
    (total, charge) => total + charge.amount,
    0
  );

  return {
    ...booking,
    id:
      booking.id ||
      booking.booking_id ||
      booking.booking_code ||
      `BK-${Date.now()}`,
    bookingCode:
      booking.booking_code ||
      booking.bookingCode ||
      booking.code ||
      booking.id ||
      "No booking code",
    guestName:
      booking.customer_name ||
      booking.guest_name ||
      booking.guestName ||
      booking.guest ||
      booking.customerName ||
      "Villa Guest",
    phone:
      booking.customer_phone ||
      booking.phone ||
      booking.phone_number ||
      "No contact number",
    email:
      booking.customer_email ||
      booking.email ||
      "No email address",
    villaName:
      booking.villa_name ||
      booking.villaName ||
      booking.villa ||
      booking.room ||
      "Villa",
    checkIn:
      booking.check_in_date ||
      booking.checkIn ||
      booking.startDate ||
      addDays(todayStr(), 1),
    checkOut:
      booking.check_out_date ||
      booking.checkOut ||
      booking.endDate ||
      addDays(todayStr(), 2),
    checkInTime:
      booking.check_in_time || booking.checkInTime || "3:00 PM",
    checkOutTime:
      booking.check_out_time || booking.checkOutTime || "11:00 AM",
    guestCount: Number(booking.guest_count || booking.guestCount || 0),
    bookingStatus:
      booking.booking_status ||
      booking.bookingStatus ||
      booking.status ||
      "Confirmed",
    stayStatus:
      booking.stay_status ||
      booking.stayStatus ||
      ((booking.booking_status || booking.bookingStatus || booking.status) === "Checked In"
        ? "Checked In"
        : (booking.booking_status || booking.bookingStatus || booking.status) === "Completed"
        ? "Checked Out"
        : "Not Checked In"),
    checkedInAt:
      booking.checked_in_at || booking.checkedInAt || "",
    checkedOutAt:
      booking.checked_out_at || booking.checkedOutAt || "",
    balancePaymentTiming:
      booking.front_desk_balance_timing ||
      booking.balancePaymentTiming ||
      booking.balance_payment_timing ||
      "",
    createdAt:
      booking.created_at ||
      booking.createdAt ||
      booking.created ||
      booking.booking_created_at ||
      booking.booked_at ||
      "",
    paymentStatus: computedPaymentStatus,
    paymentChoice,
    requiredDownpayment,
    downpaymentAmount,
    downpaymentVerified,
    paymentMethod:
      booking.payment_method ||
      booking.paymentMethod ||
      booking.selected_payment_method ||
      "Online Payment",
    paymentReference:
      booking.payment_reference ||
      booking.paymentReference ||
      booking.reference_number ||
      "",
    lastPaymentAt:
      booking.last_payment_at ||
      booking.lastPaymentAt ||
      booking.payment_date ||
      "",
    paymentHistory,
    totalAmount,
    amountPaid,
    balanceAmount,
    otherCharges,
    otherChargesTotal,
    notes:
      booking.notes ||
      booking.special_request ||
      booking.specialRequest ||
      "No special request.",
  };
}

// These predicates use the booking lifecycle saved by the authenticated
// administrator check-in/check-out endpoints. Paying or reaching the arrival
// date alone never places a guest in the Check In & Out queue.
function normalizeStayLabel(value) {
  return String(value || "").trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}

function hasCompletedCheckOut(booking) {
  if (!booking) return false;
  if (booking.checkedOutAt || booking.checked_out_at) return true;
  const stay = normalizeStayLabel(booking.stayStatus || booking.stay_status);
  const reservation = normalizeStayLabel(booking.bookingStatus || booking.booking_status || booking.status);
  return ["checked out", "checkout", "completed"].includes(stay) ||
    ["checked out", "checkout", "completed"].includes(reservation);
}

function hasAdminCheckedIn(booking) {
  if (!booking || hasCompletedCheckOut(booking)) return false;
  const stay = normalizeStayLabel(booking.stayStatus || booking.stay_status);
  const reservation = normalizeStayLabel(booking.bookingStatus || booking.booking_status || booking.status);
  // Some existing Supabase schemas omit optional audit columns; their admin
  // endpoint still persists Checked In in the lifecycle status column.
  return ["checked in", "check in", "checkin"].includes(stay) ||
    ["checked in", "check in", "checkin"].includes(reservation);
}

function createDemoBookings() {
  return [
    {
      id: "BK-3001",
      booking_code: "TV-2026-3001",
      customer_name: "Angela Reyes",
      customer_phone: "0917 245 8831",
      customer_email: "angela@example.com",
      villa_name: "Villa 1",
      check_in_date: addDays(todayStr(), 1),
      check_out_date: addDays(todayStr(), 2),
      check_in_time: "3:00 PM",
      check_out_time: "11:00 AM",
      guest_count: 8,
      booking_status: "Confirmed",
      payment_status: "50% Downpayment",
      payment_choice: "half",
      payment_method: "QRPh",
      payment_reference: "QRPH-DEMO-3001",
      last_payment_at: new Date().toISOString(),
      total_amount: 4500,
      amount_paid: 2250,
      balance_amount: 2250,
      notes: "Birthday setup and two extra towels.",
    },
    {
      id: "BK-3002",
      booking_code: "TV-2026-3002",
      customer_name: "Paolo Mendoza",
      customer_phone: "0928 553 0901",
      customer_email: "paolo@example.com",
      villa_name: "Villa 2",
      check_in_date: addDays(todayStr(), 2),
      check_out_date: addDays(todayStr(), 3),
      check_in_time: "3:00 PM",
      check_out_time: "11:00 AM",
      guest_count: 6,
      booking_status: "Confirmed",
      payment_status: "Paid",
      payment_choice: "full",
      payment_method: "QRPh",
      payment_reference: "QRPH-DEMO-3002",
      last_payment_at: new Date().toISOString(),
      total_amount: 5500,
      amount_paid: 5500,
      balance_amount: 0,
      notes: "Prepare extra pillows and drinking water.",
    },
    {
      id: "BK-3003",
      booking_code: "TV-2026-3003",
      customer_name: "Carla Ramos",
      customer_phone: "0935 700 1122",
      customer_email: "carla@example.com",
      villa_name: "Villa 3",
      check_in_date: addDays(todayStr(), 4),
      check_out_date: addDays(todayStr(), 5),
      check_in_time: "3:00 PM",
      check_out_time: "11:00 AM",
      guest_count: 8,
      booking_status: "Confirmed",
      payment_status: "Unpaid",
      payment_choice: "half",
      payment_method: "QRPh",
      total_amount: 6500,
      amount_paid: 0,
      balance_amount: 6500,
      notes: "Guest may arrive early to leave some items.",
    },
    {
      id: "BK-3004",
      booking_code: "TV-2026-3004",
      customer_name: "Mark Villanueva",
      customer_phone: "0916 333 6677",
      customer_email: "mark@example.com",
      villa_name: "Villa 4",
      check_in_date: addDays(todayStr(), 6),
      check_out_date: addDays(todayStr(), 7),
      check_in_time: "3:00 PM",
      check_out_time: "11:00 AM",
      guest_count: 4,
      booking_status: "Confirmed",
      payment_status: "50% Downpayment",
      payment_choice: "half",
      payment_method: "GCash",
      payment_reference: "GCASH-DEMO-3004",
      last_payment_at: new Date().toISOString(),
      total_amount: 7500,
      amount_paid: 3750,
      balance_amount: 3750,
      notes: "Needs charcoal and PartyBox rental.",
    },
  ];
}

function getStoredBookings() {
  const stored = readStorage(STORAGE_KEYS.BOOKINGS, []);
  if (Array.isArray(stored) && stored.length) return stored;

  const seededBookings = createDemoBookings();
  writeStorage(STORAGE_KEYS.BOOKINGS, seededBookings);
  return seededBookings;
}

function createInitialAssignments() {
  const now = new Date().toISOString();
  return [
    {
      id: "ASSIGN-001",
      title: "Pre-arrival housekeeping preparation – Villa 1",
      category: "Housekeeping",
      department: "Housekeeping",
      assignmentType: "housekeeping-pre-arrival",
      bookingId: "BK-3001",
      bookingCode: "TV-2026-3001",
      villaName: "Villa 1",
      villa: "Villa 1",
      guestName: "Angela Reyes",
      guest: "Angela Reyes",
      contact: "0917 245 8831",
      assignedStaffId: "",
      assignedTo: "Maria Santos",
      assignedRole: "Housekeeping Staff",
      priority: "High",
      dueDate: addDays(todayStr(), 1),
      dueTime: "11:00 AM",
      status: "In Progress",
      progress: 40,
      assignedBy: "Villa Administrator",
      description:
        "Prepare Villa 1 for Angela Reyes before arrival. Complete cleaning, linen replacement, sanitation, amenities restocking, and final inspection.",
      checklist: ASSIGNMENT_TEMPLATES[0].checklist.map((label, index) => ({
        id: `ASSIGN-001-${index}`,
        label,
        done: index < 2,
      })),
      attachments: [],
      notes: "Birthday setup and two extra towels.",
      createdAt: now,
      fromBooking: true,
    },
    {
      id: "ASSIGN-002",
      title: "Pre-arrival villa equipment inspection – Villa 2",
      category: "Maintenance",
      department: "Maintenance",
      assignmentType: "maintenance-inspection",
      bookingId: "BK-3002",
      bookingCode: "TV-2026-3002",
      villaName: "Villa 2",
      villa: "Villa 2",
      guestName: "Paolo Mendoza",
      guest: "Paolo Mendoza",
      contact: "0928 553 0901",
      assignedStaffId: "ST-002",
      assignedTo: "Jose Ramirez",
      assignedRole: "Maintenance Technician",
      priority: "High",
      dueDate: addDays(todayStr(), 2),
      dueTime: "10:00 AM",
      status: "Pending",
      progress: 0,
      assignedBy: "Villa Administrator",
      description:
        "Inspect utilities, air-conditioning, locks, Wi-Fi, television, and outdoor equipment before guest arrival.",
      checklist: ASSIGNMENT_TEMPLATES[2].checklist.map((label, index) => ({
        id: `ASSIGN-002-${index}`,
        label,
        done: false,
      })),
      attachments: [],
      notes: "Prepare extra pillows and drinking water.",
      createdAt: now,
      fromBooking: true,
    },
    {
      id: "ASSIGN-003",
      title: "Guest arrival and welcome preparation – Villa 3",
      category: "Guest Services",
      department: "Guest Services",
      assignmentType: "guest-services-arrival",
      bookingId: "BK-3003",
      bookingCode: "TV-2026-3003",
      villaName: "Villa 3",
      villa: "Villa 3",
      guestName: "Carla Ramos",
      guest: "Carla Ramos",
      contact: "0935 700 1122",
      assignedStaffId: "ST-003",
      assignedTo: "Anna Cruz",
      assignedRole: "Guest Services Associate",
      priority: "High",
      dueDate: addDays(todayStr(), 4),
      dueTime: "1:00 PM",
      status: "Pending Review",
      progress: 100,
      assignedBy: "Villa Administrator",
      description:
        "Confirm early-arrival arrangements, prepare the welcome kit, and coordinate the guest greeting.",
      checklist: ASSIGNMENT_TEMPLATES[3].checklist.map((label, index) => ({
        id: `ASSIGN-003-${index}`,
        label,
        done: true,
      })),
      attachments: [],
      notes: "Guest may arrive early to leave some items.",
      createdAt: now,
      fromBooking: true,
    },
  ];
}

function mergeById(...groups) {
  const map = new Map();
  groups.flat().forEach((item) => {
    if (item?.id) map.set(item.id, item);
  });
  return Array.from(map.values());
}

function makeChecklist(items, assignmentId) {
  return items
    .map((item) => (typeof item === "string" ? item : item.label))
    .filter(Boolean)
    .map((label, index) => ({
      id: `${assignmentId}-check-${index}`,
      label,
      done: false,
    }));
}

function activeAssignmentStatus(status) {
  return !["Completed", "Cancelled"].includes(status);
}

function assignmentAuditEntry(status, actor, note = "") {
  return {
    id: `AUDIT-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    status,
    actor,
    note,
    timestamp: new Date().toISOString(),
  };
}

function validDateString(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""));
}

function StatusPill({ status }) {
  return (
    <span className={`admin-status-pill status-${slug(status)}`}>{status}</span>
  );
}

function PriorityPill({ priority }) {
  return (
    <span className={`admin-priority-pill priority-${slug(priority)}`}>
      {priority}
    </span>
  );
}


function villaImageDisplayName(imageUrl, index) {
  try {
    const pathname = new URL(imageUrl, window.location.origin).pathname;
    const filename = decodeURIComponent(pathname.split("/").pop() || "");
    const displayName = filename.replace(/^[a-f0-9]{32}-/i, "");
    return displayName && !/^[a-f0-9]{32}\.[a-z0-9]+$/i.test(displayName)
      ? displayName
      : `Villa photo ${index + 1}`;
  } catch {
    return `Villa photo ${index + 1}`;
  }
}

function villaAmenitiesToText(
  amenities
) {
  if (!Array.isArray(amenities)) {
    return "";
  }

  return amenities
    .flatMap((group) => {
      if (
        typeof group === "string"
      ) {
        return [
          `Amenities | ${group}`,
        ];
      }

      const title =
        String(
          group?.title ||
          "Amenities"
        ).trim();

      const items =
        Array.isArray(
          group?.items
        )
          ? group.items
          : [];

      return items.map(
        (item) =>
          `${title} | ${item}`
      );
    })
    .join("\n");
}

function parseVillaAmenitiesText(
  value
) {
  const groups =
    new Map();

  String(value || "")
    .split("\n")
    .map((line) =>
      line.trim()
    )
    .filter(Boolean)
    .forEach((line) => {
      const separatorIndex =
        line.indexOf("|");

      const title =
        separatorIndex >= 0
          ? line
              .slice(
                0,
                separatorIndex
              )
              .trim()
          : "Amenities";

      const item =
        separatorIndex >= 0
          ? line
              .slice(
                separatorIndex + 1
              )
              .trim()
          : line;

      if (!item) {
        return;
      }

      if (!groups.has(title)) {
        groups.set(
          title,
          []
        );
      }

      groups
        .get(title)
        .push(item);
    });

  return Array.from(
    groups.entries()
  ).map(
    ([title, items]) => ({
      title,
      icon: "check",
      items,
    })
  );
}

function createVillaEditForm(
  villa = null
) {
  const normalized =
    normalizeVillaCatalogRow(
      villa || {}
    );

  return {
    ...normalized,
    price:
      normalized.price
        ? String(
            normalized.price
          )
        : "",
    capacity:
      String(
        normalized.capacity ||
        1
      ),
    amenitiesText:
      villaAmenitiesToText(
        normalized.amenities
      ),
  };
}

function Avatar({ name, online = false, size = 38, src, photo = false }) {
  const [imageFailed, setImageFailed] = React.useState(false);
  React.useEffect(() => setImageFailed(false), [src]);
  return (
    <span
      className="admin-avatar-wrap"
      style={{ width: size, height: size, minWidth: size }}
    >
      <span
        className="admin-avatar"
        style={{ width: size, height: size, fontSize: size * 0.35 }}
      >
        {src && !imageFailed
          ? <img src={src} alt={`${name || "Admin"} profile`} onError={() => setImageFailed(true)} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "50%" }} />
          : photo ? <UserRound size={size * 0.52} strokeWidth={1.5} aria-hidden="true" /> : initials(name)}
      </span>
      {online && <i className="admin-online-dot" />}
    </span>
  );
}

function EmptyState({
  icon: Icon,
  title,
  message,
  action = "",
  onAction = () => {},
}) {
  return (
    <div className="admin-empty-state">
      {Icon && <Icon size={46} strokeWidth={1.3} />}
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action && (
        <button className="admin-btn-primary" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

function createChartEntranceAnimation(reducedMotion, stagger = 75) {
  const duration = reducedMotion ? 0 : 420;
  const easing = "easeOutCubic";
  const delay = (context) =>
    reducedMotion || context.type !== "data"
      ? 0
      : context.dataIndex * stagger + context.datasetIndex * 45;

  return {
    duration,
    easing,
    delay,
    animateRotate: !reducedMotion,
    animateScale: !reducedMotion,
  };
}

function createChartRiseAnimation(reducedMotion, stagger = 45) {
  const animation = createChartEntranceAnimation(reducedMotion, stagger);

  const easing = "easeOutCubic";

  return {
    animation: {
      duration: animation.duration,
      easing,
    },
    animations: {
      y: {
        from: (context) => context.chart.scales.y.getPixelForValue(0),
        duration: animation.duration,
        easing,
        delay: animation.delay,
      },
    },
  };
}

function VillaAnalyticsCharts() {


  const bookingTrendRef = React.useRef(null);
  const villaRef = React.useRef(null);
  const reservationRef = React.useRef(null);
  const paymentRef = React.useRef(null);
  
  const charts = React.useRef({});
  
  
  
  React.useEffect(()=>{
  const reducedMotion =
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  
  
  // destroy old charts
  
  Object.values(charts.current).forEach(chart=>{
  
  if(chart){
  
  chart.destroy();
  
  }
  
  });
  
  
  
  // ==============================
  // MONTHLY BOOKING TREND
  // LINE CHART
  // ==============================
  
  
  charts.current.bookingTrend =
  new Chart(
  
  bookingTrendRef.current,
  
  {
  
  
  type:"line",
  
  
  data:{
  
  
  labels:[
  
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec"
  
  ],
  
  
  
  datasets:[
  
  
  
  {
  
  label:"High Booking Months",
  
  data:[
  
  20,
  35,
  50,
  45,
  80,
  95,
  70,
  60,
  85,
  90,
  65,
  100
  
  ],
  
  
  
  borderColor:"#2F80ED",
  
  backgroundColor:
  "rgba(47,128,237,0.15)",
  
  
  borderWidth:3,
  
  
  fill:true,
  
  
  tension:0.45,
  
  
  pointRadius:5,
  
  
  pointHoverRadius:9
  
  
  
  },
  
  
  
  {
  
  
  label:"Low Booking Months",
  
  
  data:[
  
  5,
  10,
  15,
  8,
  20,
  12,
  5,
  18,
  10,
  15,
  8,
  6
  
  ],
  
  
  
  borderColor:"#EB5757",
  
  backgroundColor:
  "rgba(235,87,87,0.12)",
  
  
  borderWidth:3,
  
  
  fill:true,
  
  
  tension:0.45,
  
  
  pointRadius:5,
  
  
  pointHoverRadius:9
  
  
  }
  
  
  
  ]
  
  },
  
  
  
  options:{
  
  
  responsive:true,
  
  
  maintainAspectRatio:false,
  
  
  
  ...createChartRiseAnimation(reducedMotion),
  
  
  
  plugins:{
  
  
  legend:{
  
  
  position:"top"
  
  
  },
  
  
  
  tooltip:{
  
  
  enabled:true,
  
  
  animation:{
  
  
  duration:300
  
  
  }
  
  
  }
  
  
  },
  
  
  
  scales:{
  
  
  y:{
  
  
  beginAtZero:true
  
  
  },
  
  
  
  x:{
  
  
  grid:{
  
  
  display:false
  
  
  }
  
  
  }
  
  
  }
  
  
  
  }
  
  
  
  }
  
  );
  
  
  
  
  
  
  // ==============================
  // VILLA PERFORMANCE
  // VERTICAL BAR CHART
  // ==============================
  
  
  
  charts.current.villa =
  
  new Chart(
  
  villaRef.current,
  
  
  {
  
  
  type:"bar",
  
  
  
  data:{
  
  
  
  labels:[
  
  
  "Villa 1",
  
  "Villa 2",
  
  "Villa 3",
  
  "Villa 4"
  
  
  ],
  
  
  
  datasets:[
  
  
  
  {
  
  
  label:"Bookings",
  
  
  data:[
  
  45,
  70,
  35,
  90
  
  ],
  
  
  
  backgroundColor:"#56CCF2",
  
  
  borderRadius:10,
  
  
  borderSkipped:false
  
  
  
  },
  
  
  
  {
  
  
  label:"Revenue",
  
  
  data:[
  
  120000,
  180000,
  95000,
  250000
  
  ],
  
  
  
  backgroundColor:"#F2994A",
  
  
  borderRadius:10,
  
  
  borderSkipped:false
  
  
  
  }
  
  
  
  ]
  
  },
  
  
  
  options:{
  
  
  responsive:true,
  
  
  maintainAspectRatio:false,
  
  
  
  ...createChartRiseAnimation(reducedMotion),
  
  
  
  plugins:{
  
  
  legend:{
  
  
  position:"top"
  
  
  }
  
  
  },
  
  
  
  scales:{
  
  
  y:{
  
  
  beginAtZero:true
  
  
  },
  
  
  
  x:{
  
  
  grid:{
  
  
  display:false
  
  
  }
  
  
  }
  
  
  }
  
  
  
  }
  
  
  
  }
  
  );
  
  
  
  
  
  
  
  // ==============================
  // RESERVATION STATUS
  // DOUGHNUT
  // ==============================
  
  
  charts.current.reservation =
  
  new Chart(
  
  reservationRef.current,
  
  
  {
  
  
  type:"doughnut",
  
  
  
  data:{
  
  
  labels:[
  
  
  "Pending",
  
  "Confirmed",
  
  "Checked In",
  
  "Completed",
  
  "Cancelled"
  
  
  ],
  
  
  
  datasets:[
  
  
  
  {
  
  
  data:[
  
  
  10,
  40,
  20,
  25,
  5
  
  
  ],
  
  
  
  borderWidth:0,
  
  
  hoverOffset:20
  
  
  }
  
  
  
  ]
  
  
  },
  
  
  
  options:{
  
  
  responsive:true,
  
  
  maintainAspectRatio:false,
  
  
  
  cutout:"65%",
  
  
  
  animation: createChartEntranceAnimation(reducedMotion, 110),
  
  
  
  plugins:{
  
  
  legend:{
  
  
  position:"bottom"
  
  
  }
  
  
  }
  
  
  
  }
  
  
  
  }
  
  );
  
  
  
  
  
  
  
  // ==============================
  // PAYMENT ANALYTICS
  // POLAR AREA
  // ==============================
  
  
  charts.current.payment =
  
  
  new Chart(
  
  paymentRef.current,
  
  
  {
  
  
  type:"polarArea",
  
  
  
  data:{
  
  
  
  labels:[
  
  
  "Paid",
  
  "Partial",
  
  "Unpaid"
  
  
  ],
  
  
  
  datasets:[
  
  
  {
  
  
  data:[
  
  
  70,
  20,
  10
  
  
  ],
  
  
  
  borderWidth:1
  
  
  }
  
  
  
  ]
  
  },
  
  
  
  options:{
  
  
  responsive:true,
  
  
  maintainAspectRatio:false,
  
  
  
  animation: createChartEntranceAnimation(reducedMotion, 140),
  
  
  
  plugins:{
  
  
  legend:{
  
  
  position:"bottom"
  
  
  }
  
  
  }
  
  
  
  }
  
  
  
  }
  
  );
  
  
  
  
  
  
  return()=>{
  
  
  Object.values(charts.current)
  .forEach(chart=>{
  
  
  if(chart){
  
  
  chart.destroy();
  
  
  }
  
  
  });
  
  
  };
  
  
  
  },[]);
  
  
  
  
  
  
  
  return(
  
  <div className="analytics-grid">
  
  
  
  <div className="chart-card">
  
  
  <h3>
  Monthly Booking Trend
  </h3>
  
  
  <p>
  Peak and slow booking months
  </p>
  
  
  <div className="chart-wrapper">
  
  <canvas ref={bookingTrendRef}/>
  
  </div>
  
  
  </div>
  
  
  
  
  
  
  
  <div className="chart-card">
  
  
  <h3>
  Villa Performance
  </h3>
  
  
  <p>
  Most booked villas
  </p>
  
  
  <div className="chart-wrapper">
  
  <canvas ref={villaRef}/>
  
  </div>
  
  
  </div>
  
  
  
  
  
  
  
  <div className="chart-card">
  
  
  <h3>
  Reservation Status
  </h3>
  
  
  <p>
  Booking distribution
  </p>
  
  
  <div className="chart-wrapper">
  
  <canvas ref={reservationRef}/>
  
  </div>
  
  
  </div>
  
  
  
  
  
  
  
  <div className="chart-card">
  
  
  <h3>
  Payment Analytics
  </h3>
  
  
  <p>
  Payment overview
  </p>
  
  
  <div className="chart-wrapper">
  
  <canvas ref={paymentRef}/>
  
  </div>
  
  
  </div>
  
  
  
  </div>
  
  );
  
  
  }
// ============================================================
// MAIN ADMIN DASHBOARD
// ============================================================
export default function AdminDashboard() {
  const today = todayStr();
  const [profile, setProfile] = React.useState(getAdminProfile);
  const [view, setView] = React.useState("dashboard");
  const [notificationOpen, setNotificationOpen] = React.useState(false);
  const [globalSearch, setGlobalSearch] = React.useState("");
  const [systemAlert, setSystemAlert] = React.useState({
    open: false,
    type: "success",
    title: "",
    message: "",
  });
  const [signOutConfirmOpen, setSignOutConfirmOpen] = React.useState(false);
  const [signingOut, setSigningOut] = React.useState(false);
  const [bookings, setBookings] = React.useState([]);
  const [selectedBooking, setSelectedBooking] = React.useState(null);
  const [bookingHistory, setBookingHistory] = React.useState(() => readStorage(STORAGE_KEYS.BOOKING_HISTORY, []));
  const [historySearch, setHistorySearch] = React.useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = React.useState("All");
  const [historyVillaFilter, setHistoryVillaFilter] = React.useState("All");


  // Booking History is an archive, not the active arrival queue. A checkout
  // recorded by the admin takes priority over date-based overdue rules.
  // Guests already checked in stay in Check In & Out until actually checked out.
  React.useEffect(() => {
    if (!Array.isArray(bookings) || bookings.length === 0) return;
    const today = todayStr();
    const normalized = bookings.map(normalizeBooking);
    const serverHistory = normalized
      .filter((booking) => {
        if (hasCompletedCheckOut(booking)) return true;
        return Boolean(booking.checkIn && booking.checkIn < today && !hasAdminCheckedIn(booking));
      })
      .map((booking) => {
        const completed = hasCompletedCheckOut(booking);
        return {
          ...booking,
          id: `HISTORY-${booking.id}`,
          originalBookingId: String(booking.id),
          historyStatus: completed ? "Completed" : "Overdue",
          action: completed ? "Completed Check-out" : "Check-in date passed without arrival",
          completedAt: completed
            ? (booking.checkedOutAt || booking.checked_out_at || booking.updated_at || booking.createdAt || "")
            : `${booking.checkIn}T00:00:00`,
        };
      });

    setBookingHistory((previous) => {
      // Deleted database records must not reappear from old browser snapshots.
      const byBookingId = new Map(serverHistory.map(item => [item.originalBookingId, item]));
      const next = Array.from(byBookingId.values()).sort((a, b) =>
        String(b.completedAt || "").localeCompare(String(a.completedAt || ""))
      );
      if (JSON.stringify(previous) === JSON.stringify(next)) return previous;
      writeStorage(STORAGE_KEYS.BOOKING_HISTORY, next);
      return next;
    });
  }, [bookings]);
  const [staffDirectory, setStaffDirectory] = React.useState([]);
  const [staffAccountModalOpen, setStaffAccountModalOpen] = React.useState(false);
  const [staffAccountMode, setStaffAccountMode] = React.useState("edit");
  const [staffAccountForm, setStaffAccountForm] = React.useState(
    emptyStaffAccountForm
  );
  const [staffAccountError, setStaffAccountError] = React.useState("");

  const [paymentTransactions, setPaymentTransactions] = React.useState([]);
  const [assignments, setAssignments] = React.useState([]);
  const [notifications, setNotifications] = React.useState([]);
  const [dataLoading, setDataLoading] = React.useState(true);
  const [dataError, setDataError] = React.useState("");
  const [bookingDataError, setBookingDataError] = React.useState("");

  const [villaCatalog, setVillaCatalog] =
    React.useState([]);
  const [villaCatalogLoading, setVillaCatalogLoading] =
    React.useState(true);
  const [villaCatalogError, setVillaCatalogError] =
    React.useState("");
  const [villaMaintenanceTarget, setVillaMaintenanceTarget] = React.useState(null);
  const [villaEditorOpen, setVillaEditorOpen] =
    React.useState(false);
  const [villaEditorLoading, setVillaEditorLoading] =
    React.useState(false);
  const [villaEditorForm, setVillaEditorForm] =
    React.useState(
      createVillaEditForm()
    );
  const [villaEditorSaving, setVillaEditorSaving] =
    React.useState(false);
  const [villaEditorError, setVillaEditorError] =
    React.useState("");
  const [villaImageFiles, setVillaImageFiles] =
    React.useState([]);
  const [villaEditorImageIndex, setVillaEditorImageIndex] =
    React.useState(0);
  const [villaImageDragging, setVillaImageDragging] =
    React.useState(false);
  const [villaImagePreview, setVillaImagePreview] =
    React.useState(null);
  const villaImagePreviewUrls = React.useRef(new Set());

  // Shared, guest-facing operations modal. Existing authenticated settlement
  // endpoints remain the source of truth for payments and stay status.
  const [operationsModalOpen, setOperationsModalOpen] = React.useState(false);
  const [operationsMode, setOperationsMode] = React.useState("queue");
  const [operationsStage, setOperationsStage] = React.useState("timing");
  const [operationsBookingId, setOperationsBookingId] = React.useState("");
  const [operationsQuery, setOperationsQuery] = React.useState("");
  const [operationsFilter, setOperationsFilter] = React.useState("All");
  const [operationsBusy, setOperationsBusy] = React.useState(false);
  const [settlementModalOpen, setSettlementModalOpen] = React.useState(false);
  const [settlementBookingId, setSettlementBookingId] = React.useState("");
  const [settlementMethod, setSettlementMethod] = React.useState("Cash");
  const [settlementError, setSettlementError] = React.useState("");
  const [settlementSubmitting, setSettlementSubmitting] = React.useState(false);
  const [qrphPayment, setQrphPayment] = React.useState({
    status: "idle",
    paymentIntentId: "",
    qrImage: "",
    expiresAt: "",
    error: "",
  });
  const [paymentMethodFilter, setPaymentMethodFilter] = React.useState("All");
  const [receiptTransaction, setReceiptTransaction] = React.useState(null);
  const [receiptModalOpen, setReceiptModalOpen] = React.useState(false);
  const [settlementForm, setSettlementForm] = React.useState({
    payerName: "",
    amount: "",
    cashTendered: "",
    paymentTiming: "",
    notes: "",
  });
  const [settlementCharges, setSettlementCharges] = React.useState([]);
  const [chargeDraft, setChargeDraft] = React.useState({
    description: "",
    amount: "",
  });
  const [settlementCustomerSearch, setSettlementCustomerSearch] =
    React.useState("");
  const [frontDeskPaymentStep, setFrontDeskPaymentStep] =
    React.useState("summary");
  const [frontDeskFlowSubmitting, setFrontDeskFlowSubmitting] =
    React.useState(false);

  const [bookingFilter, setBookingFilter] = React.useState("All");
  const [monitorStatus, setMonitorStatus] = React.useState("All");
  const [assignmentHistoryOpen, setAssignmentHistoryOpen] = React.useState(false);
  const [assignmentHistorySearch, setAssignmentHistorySearch] = React.useState("");
  const [assignmentHistoryStatus, setAssignmentHistoryStatus] = React.useState("All");
  const [profileEditOpen, setProfileEditOpen] = React.useState(false);
  const [profileEditForm, setProfileEditForm] = React.useState({ name: "", email: "", nickname: "", phone: "" });
  const [profileEditError, setProfileEditError] = React.useState("");
  const [profileEditSaving, setProfileEditSaving] = React.useState(false);
  const [selectedAssignmentId, setSelectedAssignmentId] = React.useState("");
  const [assignmentModalOpen, setAssignmentModalOpen] = React.useState(false);
  const [editingAssignment, setEditingAssignment] = React.useState(null);
  const [deleteCandidate, setDeleteCandidate] = React.useState(null);
  const [selectedCalendarDate, setSelectedCalendarDate] = React.useState(null);
  const [calendarModalOpen, setCalendarModalOpen] = React.useState(false);
  const [calendarDate, setCalendarDate] = React.useState(() => {
    const date = new Date();
    return { year: date.getFullYear(), month: date.getMonth() };
  });

  const notificationRef = React.useRef(null);

  const loadVillaCatalog =
    React.useCallback(
      async ({
        silent = false,
      } = {}) => {
        if (!silent) {
          setVillaCatalogLoading(
            true
          );
        }

        try {
          const payload =
            await apiRequest(
              "/villa-catalog/admin"
            );

          const rows =
            Array.isArray(
              payload?.data
            )
              ? payload.data.map(
                  normalizeVillaCatalogRow
                )
              : [];

          setVillaCatalog(
            rows
          );
          setVillaCatalogError(
            ""
          );
        } catch (error) {
          const message =
            error instanceof Error
              ? error.message
              : "Unable to load the Villa catalog.";

          setVillaCatalogError(
            message
          );

          if (!silent) {
            showToast(
              message
            );
          }
        } finally {
          if (!silent) {
            setVillaCatalogLoading(
              false
            );
          }
        }
      },
      []
    );

  const fetchAdminData = React.useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setDataLoading(true);
      setDataError("");
    }

    try {
      // Bootstrap includes the saved profile; avoid a duplicate profile/auth round trip.
      const payload = await apiRequest("/admin/bootstrap");
      const data = payload?.data || {};

      setBookingDataError(data.bookingError || "");
      setProfile((current) => ({
        ...current,
        ...(data.profile || {}),
        role:
          data.profile?.role ||
          data.profile?.position ||
          current.role ||
          "Administrator",
      }));
      setBookings(current => snapshotRows(current, data.bookings, Boolean(data.bookingError)));
      setStaffDirectory(current => snapshotRows(current,
        Array.isArray(data.staff) ? data.staff.map(normalizeStaffAccount) : null));
      setAssignments(current => snapshotRows(current,
        Array.isArray(data.tasks) ? data.tasks.filter(task => task.source !== MAINTENANCE_SOURCE) : null));
      setNotifications(current => snapshotRows(current,
        Array.isArray(data.notifications)
          ? data.notifications.filter((item) =>
              !item.messageId && !["message", "staff_message", "staff-message"].includes(
                String(item.type || "").toLowerCase()
              )
            )
          : null
      ));
      setPaymentTransactions(current => snapshotRows(current, data.paymentTransactions));
      setDataError(data.snapshotErrors?.length
        ? `Some updates could not be loaded (${data.snapshotErrors.join(", ")}). Showing the last available data.` : "");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to load the administrator database.";
      setDataError(message);
      if (!silent) showToast(message);
    } finally {
      if (!silent) setDataLoading(false);
    }
  }, []);
  const loadAdminData = React.useMemo(() => singleFlightRefresh(fetchAdminData), [fetchAdminData]);

  const liveStatus = useLiveUpdates({
    domains: ["accounts", "staff", "bookings", "payments", "tasks", "notifications", "messages"],
    onChange: () => loadAdminData({ silent: true }), refreshAuth: refreshPortalSession,
  });
  useLiveUpdates({
    domains: ["payments"],
    onChange: () => {
      if (
        qrphPayment.paymentIntentId &&
        ["awaiting_payment", "processing"].includes(qrphPayment.status)
      ) {
        return checkQrPhSettlementStatus(qrphPayment.paymentIntentId, true);
      }
    },
    refreshAuth: refreshPortalSession,
  });
  useLiveUpdates({ domains: ["catalog"], onChange: () => loadVillaCatalog({ silent: true }) });
  React.useEffect(() => { loadAdminData(); }, [loadAdminData]);
  React.useEffect(() => { loadVillaCatalog(); }, [loadVillaCatalog]);

  React.useEffect(() => {
    const handleOutside = (event) => {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(event.target)
      ) {
        setNotificationOpen(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setNotificationOpen(false);
        setAssignmentHistoryOpen(false);
        setProfileEditOpen(false);
        setAssignmentModalOpen(false);
        setCalendarModalOpen(false);
        setEditingAssignment(null);
        setDeleteCandidate(null);
        setSettlementModalOpen(false);
        setOperationsModalOpen(false);
        setReceiptModalOpen(false);
        setStaffAccountModalOpen(false);
        setVillaEditorOpen(false);
        setVillaEditorError("");
        setStaffAccountError("");
        setSettlementError("");
      }
    };
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const showToast = React.useCallback((message, explicitType = "") => {
    const cleanMessage = String(message || "").trim();
    if (!cleanMessage) return;

    const type =
      explicitType === "success" || explicitType === "error"
        ? explicitType
        : inferAdminAlertType(cleanMessage);

    setSystemAlert({
      open: true,
      type,
      title: type === "success" ? "Success!" : "Something went wrong",
      message: cleanMessage,
    });
  }, []);

  const closeSystemAlert = React.useCallback(() => {
    setSystemAlert((current) =>
      current.type === "loading"
        ? current
        : {
            ...current,
            open: false,
          }
    );
  }, []);

  React.useEffect(() => {
    const handleSystemAlert = (event) => {
      const detail = event?.detail || {};

      if (detail.type === "close-loading") {
        setSystemAlert((current) =>
          current.type === "loading"
            ? {
                ...current,
                open: false,
              }
            : current
        );
        return;
      }

      const type =
        detail.type === "loading" ||
        detail.type === "error" ||
        detail.type === "success"
          ? detail.type
          : "success";

      setSystemAlert({
        open: true,
        type,
        title:
          detail.title ||
          (type === "loading"
            ? "Processing..."
            : type === "success"
            ? "Success!"
            : "Something went wrong"),
        message:
          detail.message ||
          (type === "loading"
            ? "Please wait while the request is being processed."
            : ""),
      });
    };

    window.addEventListener("thevilla:system-alert", handleSystemAlert);
    return () =>
      window.removeEventListener("thevilla:system-alert", handleSystemAlert);
  }, []);


  const navigate = React.useCallback((nextView) => {
    setOperationsModalOpen(false);
    setVillaMaintenanceTarget(null);
    setView(nextView === "maintenance" ? "villas" : nextView);
    setNotificationOpen(false);
    if (!["bookings", "assignmentMonitor", "staff", "payments"].includes(nextView)) {
      setGlobalSearch("");
    }
  }, []);


  const normalizedBookings = React.useMemo(
    
    () => bookings.map(normalizeBooking),
    [bookings]
  );

  const lifecycleBookings = React.useMemo(() => {
    const today = new Date(`${todayStr()}T00:00:00`);
    const availableLimit = new Date(today);
    availableLimit.setMonth(availableLimit.getMonth() + 12);

    return normalizedBookings.map((booking) => {
      const checkout = booking.checkOut
        ? new Date(`${booking.checkOut}T00:00:00`)
        : null;

      const checkin = booking.checkIn
        ? new Date(`${booking.checkIn}T00:00:00`)
        : null;

      let lifecycleStatus = "Active";

      // A real checkout goes to Booking History even when the booking date
      // is in the past; payment or the scheduled date does not count.
      if (hasCompletedCheckOut(booking)) {
        lifecycleStatus = "Completed";
      }

      // A missed arrival moves to History once its check-in date has passed.
      else if (checkin && checkin < today && !hasAdminCheckedIn(booking)) {
        lifecycleStatus = "Overdue";
      }

      // Cancelled bookings stay separated
      else if (
        [
          "cancelled",
          "canceled",
        ].includes(normalizeStayLabel(booking.bookingStatus || booking.booking_status))
      ) {
        lifecycleStatus = "Cancelled";
      }

      // Reservations outside the available booking window are hidden
      const withinBookingWindow =
        (!checkin || checkin <= availableLimit) &&
        (!checkout || checkout >= today);

      return {
        ...booking,
        lifecycleStatus,
        withinBookingWindow,
        bookingStatus:
          lifecycleStatus === "Overdue" ||
          lifecycleStatus === "Cancelled"
            ? lifecycleStatus
            : booking.bookingStatus,
      };
    });
  }, [normalizedBookings]);

  const activeBookings = React.useMemo(
    () =>
      lifecycleBookings.filter(
        (booking) =>
          !["Completed", "Overdue", "Cancelled"].includes(booking.lifecycleStatus) &&
          booking.withinBookingWindow
      ),
    [lifecycleBookings]
  );

  const frontDeskSettlementQueue = React.useMemo(
    () =>
      activeBookings
        .filter(
          (booking) =>
            booking.paymentChoice === "half" &&
            booking.downpaymentVerified &&
            booking.balanceAmount > 0
        )
        .sort((first, second) =>
          String(first.checkIn || "9999").localeCompare(
            String(second.checkIn || "9999")
          )
        ),
    [activeBookings]
  );

  const filteredFrontDeskQueue = React.useMemo(() => {
    const rawQuery = settlementCustomerSearch.trim();
    if (!rawQuery) return [];

    const normalizeLookup = (value) =>
      String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[‐‑‒–—−]/g, "-");

    const compactLookup = (value) =>
      normalizeLookup(value).replace(/[^a-z0-9]/g, "");

    const query = normalizeLookup(rawQuery);
    const compactQuery = compactLookup(rawQuery);

    return frontDeskSettlementQueue
      .map((booking) => {
        const fullCode = String(booking.bookingCode || "").trim();
        const normalizedCode = normalizeLookup(fullCode);
        const codeParts = normalizedCode.split("-").filter(Boolean);
        const lastCodePart =
          codeParts.length > 0
            ? codeParts[codeParts.length - 1]
            : normalizedCode;

        const guestName = normalizeLookup(booking.guestName);
        const compactCode = compactLookup(fullCode);
        const compactLastCode = compactLookup(lastCodePart);

        const exactFullCode =
          normalizedCode === query ||
          (compactQuery && compactCode === compactQuery);

        const exactLastCode =
          lastCodePart === query ||
          (compactQuery && compactLastCode === compactQuery);

        const partialFullCode =
          normalizedCode.includes(query) ||
          (compactQuery && compactCode.includes(compactQuery));

        const partialLastCode =
          lastCodePart.includes(query) ||
          (compactQuery && compactLastCode.includes(compactQuery));

        const guestMatch = guestName.includes(query);

        if (
          !exactFullCode &&
          !exactLastCode &&
          !partialFullCode &&
          !partialLastCode &&
          !guestMatch
        ) {
          return null;
        }

        let matchRank = 5;
        if (exactFullCode) matchRank = 0;
        else if (exactLastCode) matchRank = 1;
        else if (partialLastCode) matchRank = 2;
        else if (partialFullCode) matchRank = 3;
        else if (guestName.startsWith(query)) matchRank = 4;

        return { booking, matchRank };
      })
      .filter(Boolean)
      .sort((first, second) => {
        if (first.matchRank !== second.matchRank) {
          return first.matchRank - second.matchRank;
        }
        return String(first.booking.guestName || "").localeCompare(
          String(second.booking.guestName || "")
        );
      })
      .slice(0, 8)
      .map((item) => item.booking);
  }, [frontDeskSettlementQueue, settlementCustomerSearch]);

  const selectedSettlementBooking = React.useMemo(
    () =>
      normalizedBookings.find(
        (booking) => booking.id === settlementBookingId
      ) || null,
    [normalizedBookings, settlementBookingId]
  );

  const selectedBookingAssignments = React.useMemo(() => {
    if (!selectedBooking) return [];

    return assignments
      .filter(
        (assignment) =>
          String(assignment.bookingId) === String(selectedBooking.id)
      )
      .slice()
      .sort((first, second) =>
        String(first.dueDate || "9999-12-31").localeCompare(
          String(second.dueDate || "9999-12-31")
        )
      );
  }, [assignments, selectedBooking]);

  const selectedBookingAssignedStaff = React.useMemo(() => {
    const groupedStaff = new Map();

    selectedBookingAssignments.forEach((assignment) => {
      const staff =
        staffDirectory.find(
          (member) => member.id === assignment.assignedStaffId
        ) ||
        staffDirectory.find(
          (member) => member.name === assignment.assignedTo
        ) ||
        null;

      const groupKey =
        staff?.id ||
        assignment.assignedStaffId ||
        assignment.assignedTo ||
        assignment.id;

      if (!groupedStaff.has(groupKey)) {
        groupedStaff.set(groupKey, {
          id: groupKey,
          name: staff?.name || assignment.assignedTo || "Assigned Staff",
          avatarUrl: staff?.avatarUrl || staff?.avatar_url || assignment.assignedStaffAvatarUrl || "",
          role: staff?.role || "Villa Staff",
          department:
            staff?.department ||
            assignment.department ||
            assignment.category ||
            "Operations",
          shift: staff?.shift || "Shift not specified",
          online: !!staff?.online,
          tasks: [],
        });
      }

      groupedStaff.get(groupKey).tasks.push(assignment);
    });

    return Array.from(groupedStaff.values());
  }, [selectedBookingAssignments, staffDirectory]);

  React.useEffect(() => {
    if (view !== "payments" || !settlementBookingId) return;

    const selectionIsEligible = frontDeskSettlementQueue.some(
      (booking) => booking.id === settlementBookingId
    );

    if (!selectionIsEligible) {
      setSettlementBookingId("");
      setSettlementCustomerSearch("");
      setFrontDeskPaymentStep("summary");
      resetSettlementForm();
    }
  }, [view, frontDeskSettlementQueue, settlementBookingId]);

  React.useEffect(() => {
    if (view !== "payments") return;
    let active = true;

    apiRequest("/front-desk/payments")
      .then((payload) => {
        if (!active || !Array.isArray(payload?.data)) return;
        const normalized = payload.data.map(normalizeApiTransaction);
        setPaymentTransactions(normalized);
      })
      .catch(() => {
        // Retain the cached register when the backend is temporarily unavailable.
      });

    return () => {
      active = false;
    };
  }, [view]);

  React.useEffect(() => {
    const shouldPoll =
      settlementMethod === "QRPh" &&
      qrphPayment.paymentIntentId &&
      ["awaiting_payment", "processing"].includes(qrphPayment.status);

    if (!shouldPoll) return undefined;

    const timer = window.setInterval(() => {
      checkQrPhSettlementStatus(qrphPayment.paymentIntentId, true);
    }, 30000);

    return () => window.clearInterval(timer);
  }, [
    settlementMethod,
    qrphPayment.paymentIntentId,
    qrphPayment.status,
  ]);

  const filteredPaymentTransactions = React.useMemo(() => {
    const query = globalSearch.trim().toLowerCase();
    return paymentTransactions
      .filter((transaction) => {
        const methodMatches =
          paymentMethodFilter === "All" ||
          transaction.method === paymentMethodFilter;
        const queryMatches =
          !query ||
          [
            transaction.receiptNumber,
            transaction.bookingCode,
            transaction.guestName,
            transaction.villaName,
            transaction.method,
            transaction.reference,
            transaction.cashierName,
          ]
            .join(" ")
            .toLowerCase()
            .includes(query);
        return methodMatches && queryMatches;
      })
      .sort((first, second) =>
        String(second.processedAt || "").localeCompare(
          String(first.processedAt || "")
        )
      );
  }, [paymentTransactions, paymentMethodFilter, globalSearch]);

  const paymentStats = React.useMemo(() => {
    const downpaymentsVerified = activeBookings.filter(
      (booking) =>
        booking.paymentChoice === "half" && booking.downpaymentVerified
    ).length;
    const balanceDue = frontDeskSettlementQueue.reduce(
      (total, booking) => total + booking.balanceAmount,
      0
    );
    const frontDeskCollected = paymentTransactions.reduce(
      (total, transaction) =>
        transaction.status === "Completed"
          ? total + parseAmount(transaction.amount)
          : total,
      0
    );
    const paidBookings = normalizedBookings.filter(
      (booking) => booking.balanceAmount <= 0 && booking.amountPaid > 0
    ).length;
    return {
      downpaymentsVerified,
      balanceDue,
      frontDeskCollected,
      paidBookings,
    };
  }, [activeBookings, frontDeskSettlementQueue, paymentTransactions, normalizedBookings]);

  const otherChargesTotal = React.useMemo(
    () =>
      settlementCharges.reduce(
        (total, charge) => total + parseAmount(charge.amount),
        0
      ),
    [settlementCharges]
  );
  const roomBalanceValue = selectedSettlementBooking
    ? selectedSettlementBooking.balanceAmount
    : 0;
  const settlementAmountValue = roomBalanceValue + otherChargesTotal;
  const cashTenderedRaw = String(settlementForm.cashTendered ?? "").trim();
  const hasCashTendered = cashTenderedRaw !== "";
  const cashTenderedValue = hasCashTendered
    ? parseAmount(cashTenderedRaw)
    : 0;
  const cashDifference = cashTenderedValue - settlementAmountValue;
  const settlementChange =
    settlementMethod === "Cash" && hasCashTendered
      ? Math.max(cashDifference, 0)
      : 0;
  const cashShortage =
    settlementMethod === "Cash" && hasCashTendered
      ? Math.max(-cashDifference, 0)
      : 0;
  const cashIsSufficient =
    settlementMethod !== "Cash" ||
    (hasCashTendered && cashTenderedValue + 0.009 >= settlementAmountValue);
  const settlementChargesLocked =
    settlementMethod === "QRPh" &&
    ["creating", "awaiting_payment", "processing"].includes(
      qrphPayment.status
    );

  const cashSuggestions = React.useMemo(() => {
    if (!selectedSettlementBooking || settlementAmountValue <= 0) {
      return [];
    }

    const due = Number(settlementAmountValue);
    const candidates = [
      due,
      Math.ceil(due / 100) * 100,
      Math.ceil(due / 500) * 500,
      Math.ceil(due / 1000) * 1000,
    ];

    return [...new Set(candidates.filter((value) => value >= due))].slice(0, 4);
  }, [selectedSettlementBooking, settlementAmountValue]);

  const selectedAssignment = React.useMemo(
    () =>
      assignments.find((assignment) => assignment.id === selectedAssignmentId) ||
      null,
    [assignments, selectedAssignmentId]
  );

  const assignmentStats = React.useMemo(() => {
    const total = assignments.length;
    const pending = assignments.filter(
      (assignment) => displayAssignmentStatus(assignment) === "Pending"
    ).length;
    const inProgress = assignments.filter(
      (assignment) => displayAssignmentStatus(assignment) === "In Progress"
    ).length;
    const review = assignments.filter(
      (assignment) => displayAssignmentStatus(assignment) === "Pending Review"
    ).length;
    const completed = assignments.filter(
      (assignment) => displayAssignmentStatus(assignment) === "Completed"
    ).length;
    const overdue = assignments.filter(
      (assignment) => displayAssignmentStatus(assignment) === "Overdue"
    ).length;
    return { total, pending, inProgress, review, completed, overdue };
  }, [assignments]);

  const assignmentHistoryRecords = React.useMemo(() => {
    return assignments.flatMap((assignment) => {
      const entries = Array.isArray(assignment.statusHistory) && assignment.statusHistory.length
        ? assignment.statusHistory
        : [{
            id: `${assignment.id}-created`,
            status: assignment.status || "Pending",
            actor: assignment.assignedBy || "System",
            note: "Assignment created.",
            timestamp: assignment.createdAt,
          }];
      return entries.map((entry, index) => ({
        id: entry.id || `${assignment.id}-${index}`,
        assignmentId: assignment.id,
        title: assignment.title || "Untitled assignment",
        bookingCode: assignment.bookingCode || "",
        assignedTo: assignment.assignedTo || "",
        status: entry.status || assignment.status || "Pending",
        actor: entry.actor || "System",
        note: entry.note || "Assignment status updated.",
        timestamp: entry.timestamp || assignment.updatedAt || assignment.createdAt || "",
      }));
    }).sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
  }, [assignments]);
  const filteredAssignmentHistory = React.useMemo(() => {
    const search = assignmentHistorySearch.trim().toLowerCase();
    return assignmentHistoryRecords.filter((item) => {
      const matchesSearch = !search || [item.title, item.bookingCode, item.assignedTo, item.actor, item.note]
        .join(" ").toLowerCase().includes(search);
      return matchesSearch && (assignmentHistoryStatus === "All" || item.status === assignmentHistoryStatus);
    });
  }, [assignmentHistoryRecords, assignmentHistorySearch, assignmentHistoryStatus]);

  const filteredBookings = React.useMemo(() => {
    const query = globalSearch.trim().toLowerCase();
    return activeBookings.filter((booking) => {
      const matchesQuery =
        !query ||
        [
          booking.bookingCode,
          booking.guestName,
          booking.villaName,
          booking.phone,
          booking.paymentStatus,
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      const normalizedBookingStatus = String(
        booking.bookingStatus || booking.status || ""
      ).toLowerCase();

      const normalizedPaymentStatus = String(
        booking.paymentStatus || ""
      ).toLowerCase();

      const matchesStatus =
        bookingFilter === "All" ||
        (bookingFilter === "Paid" &&
          normalizedPaymentStatus === "paid") ||
        (bookingFilter === "Unpaid" &&
          (normalizedPaymentStatus.includes("unpaid") ||
            normalizedPaymentStatus.includes("partial"))) ||
        (bookingFilter === "Completed" &&
          normalizedBookingStatus.includes("completed")) ||
        (bookingFilter === "Overdue/Cancelled" &&
          (normalizedBookingStatus.includes("overdue") ||
            normalizedBookingStatus.includes("cancelled") ||
            normalizedBookingStatus.includes("canceled")));
      return matchesQuery && matchesStatus;
    });
  }, [activeBookings, globalSearch, bookingFilter]);

  const monitoredAssignments = React.useMemo(() => {
    const query = globalSearch.trim().toLowerCase();
    return assignments
      .filter((assignment) => {
        const status = displayAssignmentStatus(assignment);
        const matchesQuery =
          !query ||
          [
            assignment.title,
            assignment.bookingCode,
            assignment.guestName || assignment.guest,
            assignment.villaName || assignment.villa,
            assignment.assignedTo,
            assignment.department || assignment.category,
          ]
            .join(" ")
            .toLowerCase()
            .includes(query);
        const matchesStatus = monitorStatus === "All" || status === monitorStatus;
        return matchesQuery && matchesStatus;
      })
      .sort((first, second) => {
        const dateCompare = String(first.dueDate || "9999").localeCompare(
          String(second.dueDate || "9999")
        );
        if (dateCompare !== 0) return dateCompare;
        return String(first.title).localeCompare(String(second.title));
      });
  }, [assignments, globalSearch, monitorStatus]);

  const unreadNotificationCount = React.useMemo(
    () => notifications.filter((notification) => notification.unread).length,
    [notifications]
  );

  const staffWorkloads = React.useMemo(
    () =>
      staffDirectory.map((staff) => {
        const staffAssignments = assignments.filter(
          (assignment) => assignment.assignedStaffId === staff.id
        );
        return {
          ...staff,
          total: staffAssignments.length,
          active: staffAssignments.filter(
            (assignment) =>
              !["Completed"].includes(displayAssignmentStatus(assignment))
          ).length,
          review: staffAssignments.filter(
            (assignment) =>
              displayAssignmentStatus(assignment) === "Pending Review"
          ).length,
          overdue: staffAssignments.filter(
            (assignment) => displayAssignmentStatus(assignment) === "Overdue"
          ).length,
        };
      }),
    [assignments]
  );

  const filteredStaffWorkloads = React.useMemo(() => {
    const query = globalSearch.trim().toLowerCase();
    if (!query) return staffWorkloads;
    return staffWorkloads.filter((staff) =>
      [staff.name, staff.role, staff.department, staff.email, staff.phone]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [staffWorkloads, globalSearch]);


  const calendarCells = React.useMemo(() => {
    const { year, month } = calendarDate;
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const previousMonthDays = new Date(year, month, 0).getDate();
    const cells = [];
    for (let index = 0; index < firstDay; index += 1) {
      cells.push({
        day: previousMonthDays - firstDay + 1 + index,
        outside: true,
        dateString: null,
        assignments: [],
      });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const dateString = `${year}-${String(month + 1).padStart(2, "0")}-${String(
        day
      ).padStart(2, "0")}`;
      cells.push({
        day,
        outside: false,
        dateString,
        assignments: assignments
          .filter(
            (assignment) =>
              assignment.dueDate === dateString &&
              displayAssignmentStatus(assignment) !== "Completed"
          )
          .sort((a, b) => String(a.dueTime || "").localeCompare(String(b.dueTime || ""))),
      });
    }
    while (cells.length < 42) {
      cells.push({
        day: cells.length - firstDay - daysInMonth + 1,
        outside: true,
        dateString: null,
        assignments: [],
      });
    }
    return cells;
  }, [calendarDate, assignments]);

  const selectedCalendarAssignments = React.useMemo(
    () =>
      selectedCalendarDate
        ? assignments.filter(
            (assignment) =>
              assignment.dueDate === selectedCalendarDate &&
              displayAssignmentStatus(assignment) !== "Completed"
          )
        : [],
    [assignments, selectedCalendarDate]
  );

  function openAssignment(assignmentId) {
    setSelectedAssignmentId(assignmentId);
    setAssignmentModalOpen(true);
  }

async function updateAssignment(assignmentId, updates, message) {
    try {
      const payload = await apiRequest(
        `/admin/tasks/${encodeURIComponent(assignmentId)}`,
        {
          method: "PATCH",
          body: JSON.stringify(updates),
        }
      );
      const updated = payload?.data;
      if (!updated) {
        throw new Error("The updated assignment was not returned.");
      }

      setAssignments((current) =>
        current.map((assignment) =>
          assignment.id === assignmentId ? updated : assignment
        )
      );
      setSelectedAssignmentId(assignmentId);
      if (message) showToast(message);
      loadAdminData({ silent: true });
      return updated;
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "The assignment could not be updated.";
      showToast(errorMessage);
      throw error;
    }
  }

async function deleteAssignment(assignmentId) {
    const assignment = assignments.find((item) => item.id === assignmentId);
    try {
      await apiRequest(`/admin/tasks/${encodeURIComponent(assignmentId)}`, {
        method: "DELETE",
      });
      setAssignments((current) =>
        current.filter((item) => item.id !== assignmentId)
      );
      setAssignmentModalOpen(false);
      setEditingAssignment(null);
      setDeleteCandidate(null);
      showToast(
        assignment
          ? `“${assignment.title}” was removed.`
          : "Assignment removed."
      );
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "The assignment could not be deleted."
      );
    }
  }

async function saveEditedAssignment(event) {
    event.preventDefault();
    if (!editingAssignment) return;

    const staff = staffDirectory.find(
      (member) => member.id === editingAssignment.assignedStaffId
    );
    const booking = normalizedBookings.find(
      (item) => item.id === editingAssignment.bookingId
    );

    if (!staff) {
      showToast("Select a valid staff member.");
      return;
    }
    if (staff.accountStatus === "Disabled") {
      showToast("Enable the staff account before assigning work.");
      return;
    }
    if (editingAssignment.title.trim().length < 5) {
      showToast("Enter a clear assignment title.");
      return;
    }
    if (!validDateString(editingAssignment.dueDate)) {
      showToast("Select a valid due date.");
      return;
    }
    if (editingAssignment.dueDate < today) {
      showToast("The due date cannot be earlier than today.");
      return;
    }
    if (booking && editingAssignment.dueDate > addDays(booking.checkOut, 1)) {
      showToast("The due date cannot be later than one day after checkout.");
      return;
    }

    try {
      await updateAssignment(
        editingAssignment.id,
        {
          assignedStaffId: staff.id,
          title: editingAssignment.title,
          description: editingAssignment.description,
          priority: editingAssignment.priority,
          dueDate: editingAssignment.dueDate,
          dueTime: editingAssignment.dueTime,
          department: staff.department,
          checklist: editingAssignment.checklist || [],
        },
        "Assignment updated successfully."
      );
      setEditingAssignment(null);
    } catch {
      // updateAssignment already displays the backend error.
    }
  }

async function markAllNotificationsRead() {
    try {
      await apiRequest("/admin/notifications/read-all", {
        method: "PATCH",
      });
      setNotifications((current) =>
        current.map((notification) => ({ ...notification, unread: false }))
      );
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "Notifications could not be updated."
      );
    }
  }

async function handleNotificationClick(notification) {
    setNotifications((current) =>
      current.map((item) =>
        item.id === notification.id ? { ...item, unread: false } : item
      )
    );
    setNotificationOpen(false);

    apiRequest(
      `/admin/notifications/${encodeURIComponent(notification.id)}/read`,
      { method: "PATCH" }
    ).catch(() => {});

    if (notification.taskId) {
      if (assignments.some(item => item.id === notification.taskId)) {
        openAssignment(notification.taskId);
      } else {
        try {
          const payload = await apiRequest('/admin/maintenance');
          const work = (payload.data || []).find(item => item.id === notification.taskId);
          if (work) {
            navigate('villas');
            showVillaOperations(work.maintenance?.villaId || '');
          } else showToast('This operation is no longer available. Refresh your workspace.');
        } catch (error) { showToast(error.message || 'The villa operation could not be opened.'); }
      }
    }
    if (notification.paymentTransactionId) {
      const transaction = paymentTransactions.find(
        (item) => item.id === notification.paymentTransactionId
      );
      if (transaction) {
        setReceiptTransaction(transaction);
        setReceiptModalOpen(true);
      }
    }
  }

  function resetQrPhPayment() {
    setQrphPayment({
      status: "idle",
      paymentIntentId: "",
      qrImage: "",
      expiresAt: "",
      error: "",
    });
  }

  function resetSettlementForm() {
    setSettlementForm({
      payerName: "",
      amount: "",
      cashTendered: "",
      paymentTiming: "",
      notes: "",
    });
    setSettlementCharges([]);
    setChargeDraft({ description: "", amount: "" });
    setSettlementMethod("Cash");
    setSettlementError("");
    setSettlementSubmitting(false);
    resetQrPhPayment();
  }

  function closeSettlement() {
    setOperationsModalOpen(false);
    setSettlementModalOpen(false);
    setSettlementBookingId("");
    setSettlementCustomerSearch("");
    setFrontDeskPaymentStep("summary");
    resetSettlementForm();
  }

  function isNewBooking(booking) {
    const createdValue =
      booking?.createdAt ||
      booking?.created_at ||
      booking?.created ||
      booking?.booking_created_at ||
      booking?.booked_at ||
      "";

    if (!createdValue) return false;

    const created = new Date(createdValue);
    if (Number.isNaN(created.getTime())) return false;

    const age = Date.now() - created.getTime();
    const threeDays = 3 * 24 * 60 * 60 * 1000;

    return age >= 0 && age <= threeDays;
  }

  function openBookingDetails(booking) {
    if (!booking) return;
    setSelectedBooking(normalizeBooking(booking));
  }

  function closeBookingDetails() {
    setSelectedBooking(null);
  }

  function openSettlement(booking) {
    if (!booking) return;
    if (!booking.downpaymentVerified && !hasAdminCheckedIn(booking)) {
      showToast("Verify the customer PayMongo downpayment before settlement.");
      return;
    }
    if (booking.balanceAmount <= 0) {
      showToast("This booking is already fully paid.");
      return;
    }

    setSettlementBookingId(booking.id);
    setSettlementCustomerSearch("");
    setFrontDeskPaymentStep("summary");
    setSettlementMethod("Cash");

    setSettlementForm({
      payerName: booking.guestName,
      amount: String(booking.balanceAmount),
      cashTendered: "",
      paymentTiming:
        String(booking.stayStatus || "").toLowerCase() === "checked in"
          ? "check_out"
          : booking.balancePaymentTiming || booking.front_desk_balance_timing || "",
      notes: "",
    });
    setSettlementCharges(
      Array.isArray(booking.otherCharges)
        ? booking.otherCharges.map((charge, index) => ({
            id: charge.id || `CHARGE-${Date.now()}-${index}`,
            description: charge.description,
            amount: parseAmount(charge.amount),
          }))
        : []
    );
    setChargeDraft({ description: "", amount: "" });
    setSettlementError("");
    resetQrPhPayment();
    setOperationsBookingId(booking.id);
    setOperationsMode("payment");
    setOperationsStage("timing");
    setOperationsModalOpen(true);
    setSettlementModalOpen(false);
  }

  function addSettlementCharge() {
    const description = chargeDraft.description.trim();
    const amount = parseAmount(chargeDraft.amount);

    if (description.length < 2) {
      const message = "Enter a short description for the other charge.";
      setSettlementError(message);
      showToast(message, "error");
      return;
    }
    if (amount <= 0) {
      const message = "Enter a valid amount for the other charge.";
      setSettlementError(message);
      showToast(message, "error");
      return;
    }

    setSettlementCharges((current) => [
      ...current,
      {
        id: `CHARGE-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        description,
        amount: Math.round(amount * 100) / 100,
      },
    ]);
    setChargeDraft({ description: "", amount: "" });
    setSettlementForm((current) => ({ ...current, cashTendered: "" }));
    setSettlementError("");
    resetQrPhPayment();
  }

  function removeSettlementCharge(chargeId) {
    setSettlementCharges((current) =>
      current.filter((charge) => charge.id !== chargeId)
    );
    setSettlementForm((current) => ({ ...current, cashTendered: "" }));
    setSettlementError("");
    resetQrPhPayment();
  }

  function validateSettlement() {
    const booking = selectedSettlementBooking;
    if (!booking) return "Select a valid booking.";
    if (booking.paymentChoice !== "half") {
      return "This front-desk flow is only for bookings that selected 50% downpayment.";
    }
    if (!booking.downpaymentVerified) {
      return "The original customer downpayment has not been verified.";
    }
    if (booking.balanceAmount <= 0) {
      return "This booking has no remaining room balance.";
    }
    if (!["check_in", "check_out"].includes(settlementForm.paymentTiming)) {
      return "Select whether this balance is being paid at check-in or check-out.";
    }

    const paymentDateRestriction = getBookingLifecycleDateRestriction(
      booking,
      settlementForm.paymentTiming
    );
    if (paymentDateRestriction) {
      return paymentDateRestriction;
    }

    const currentStayStatus = String(
      booking.stayStatus || booking.stay_status || booking.bookingStatus || ""
    ).toLowerCase();
    if (
      settlementForm.paymentTiming === "check_out" &&
      currentStayStatus !== "checked in"
    ) {
      return "Mark the guest as Checked In before recording a check-out payment.";
    }
    if (settlementForm.payerName.trim().length < 2) {
      return "Enter the name of the person making the payment.";
    }
    if (
      chargeDraft.description.trim() ||
      String(chargeDraft.amount || "").trim()
    ) {
      return "Add the other charge to the list or clear the unfinished charge.";
    }
    if (settlementMethod === "Cash") {
      if (!hasCashTendered || cashTenderedValue <= 0) {
        return "Enter the total cash amount given by the customer.";
      }
      if (cashTenderedValue + 0.009 < settlementAmountValue) {
        return `The customer cash is insufficient by ${formatPeso(
          settlementAmountValue - cashTenderedValue
        )}.`;
      }
    }
    return "";
  }

  function normalizeApiTransaction(payment, bookingOverride = null) {
    const amount = parseAmount(payment?.amount);
    const metadata = payment?.metadata || {};
    const otherCharges = Array.isArray(
      payment?.otherCharges || payment?.other_charges || metadata.other_charges
    )
      ? payment?.otherCharges || payment?.other_charges || metadata.other_charges
      : [];
    const otherChargesTotal =
      parseAmount(
        payment?.otherChargesTotal ||
          payment?.other_charges_total ||
          metadata.other_charges_total
      ) ||
      otherCharges.reduce(
        (total, charge) => total + parseAmount(charge.amount),
        0
      );
    const roomBalance =
      parseAmount(
        payment?.roomBalance ||
          payment?.room_balance_amount ||
          metadata.room_balance
      ) || Math.max(amount - otherChargesTotal, 0);
    const newAmountPaid = parseAmount(
      bookingOverride?.amount_paid ?? bookingOverride?.amountPaid
    );
    const newBalance = parseAmount(
      bookingOverride?.balance_amount ?? bookingOverride?.balanceAmount
    );

    return {
      id: payment?.id || payment?.paymentIntentId || `PAY-${Date.now()}`,
      receiptNumber:
        payment?.receiptNumber || payment?.receipt_number || "Pending receipt",
      bookingId: payment?.bookingId ?? bookingOverride?.id,
      bookingCode:
        payment?.bookingCode || bookingOverride?.booking_code || "Booking",
      guestName:
        payment?.guestName || bookingOverride?.customer_name || "Villa Guest",
      payerName: payment?.payerName || payment?.guestName || "Villa Guest",
      villaName: payment?.villaName || bookingOverride?.villa_name || "Villa",
      stage: payment?.stage || "Remaining 50% Balance",
      source: "front-desk",
      method:
        String(payment?.method || "").toLowerCase() === "qrph"
          ? "QRPh"
          : "Cash",
      amount,
      roomBalance,
      otherCharges,
      otherChargesTotal,
      reference:
        payment?.reference || payment?.paymentIntentId || payment?.receiptNumber || "",
      cashTendered: parseAmount(payment?.cashTendered),
      changeGiven: parseAmount(payment?.changeGiven),
      previousAmountPaid: Math.max(newAmountPaid - roomBalance, 0),
      previousBalance: roomBalance,
      newAmountPaid,
      newBalance,
      cashierId: payment?.cashierId,
      cashierName: payment?.cashierName || profile.name,
      processedAt: payment?.processedAt || new Date().toISOString(),
      paymentTiming:
        payment?.paymentTiming ||
        payment?.payment_timing ||
        metadata.payment_timing ||
        "",
      notes: payment?.notes || "",
      status:
        String(payment?.status || "").toLowerCase() === "paid"
          ? "Completed"
          : payment?.status || "Pending",
      paymentIntentId: payment?.paymentIntentId || "",
      expiresAt: payment?.expiresAt || "",
    };
  }

  function mergeServerBooking(serverBooking) {
    if (!serverBooking) return null;
    let mergedBooking = null;

    setBookings((current) => {
      const updated = current.map((rawBooking) => {
        const normalized = normalizeBooking(rawBooking);
        const matches =
          String(normalized.id) === String(serverBooking.id) ||
          normalized.bookingCode === serverBooking.booking_code;
        if (!matches) return rawBooking;

        mergedBooking = {
          ...rawBooking,
          ...serverBooking,
          amount_paid: parseAmount(serverBooking.amount_paid),
          amountPaid: parseAmount(serverBooking.amount_paid),
          balance_amount: parseAmount(serverBooking.balance_amount),
          balanceAmount: parseAmount(serverBooking.balance_amount),
          payment_status: serverBooking.payment_status,
          paymentStatus: serverBooking.payment_status,
          front_desk_payment_method: serverBooking.front_desk_payment_method,
          frontDeskPaymentMethod: serverBooking.front_desk_payment_method,
          front_desk_reference: serverBooking.front_desk_reference,
          frontDeskReference: serverBooking.front_desk_reference,
          front_desk_settled_at: serverBooking.front_desk_settled_at,
          frontDeskSettledAt: serverBooking.front_desk_settled_at,
          last_payment_at: serverBooking.last_payment_at,
          lastPaymentAt: serverBooking.last_payment_at,
          last_receipt_number: serverBooking.last_receipt_number,
          lastReceiptNumber: serverBooking.last_receipt_number,
          front_desk_other_charges:
            serverBooking.front_desk_other_charges || [],
          frontDeskOtherCharges:
            serverBooking.front_desk_other_charges || [],
          front_desk_other_charges_total: parseAmount(
            serverBooking.front_desk_other_charges_total
          ),
          frontDeskOtherChargesTotal: parseAmount(
            serverBooking.front_desk_other_charges_total
          ),
          stay_status:
            serverBooking.stay_status ??
            rawBooking.stay_status ??
            normalized.stayStatus,
          stayStatus:
            serverBooking.stay_status ??
            serverBooking.stayStatus ??
            normalized.stayStatus,
          checked_in_at:
            serverBooking.checked_in_at ??
            rawBooking.checked_in_at ??
            normalized.checkedInAt,
          checkedInAt:
            serverBooking.checked_in_at ??
            serverBooking.checkedInAt ??
            normalized.checkedInAt,
          checked_out_at:
            serverBooking.checked_out_at ??
            rawBooking.checked_out_at ??
            normalized.checkedOutAt,
          checkedOutAt:
            serverBooking.checked_out_at ??
            serverBooking.checkedOutAt ??
            normalized.checkedOutAt,
          front_desk_balance_timing:
            serverBooking.front_desk_balance_timing ??
            rawBooking.front_desk_balance_timing ??
            normalized.balancePaymentTiming ??
            "",
          balancePaymentTiming:
            serverBooking.front_desk_balance_timing ??
            serverBooking.balancePaymentTiming ??
            normalized.balancePaymentTiming ??
            "",
        };
        return mergedBooking;
      });

      return updated;
    });

    return mergedBooking;
  }

  async function applyServerSettlement(result, successMessage) {
    const serverBooking = result?.booking;
    const serverPayment = result?.payment;
    if (!serverBooking || !serverPayment) {
      throw new Error("The server returned an incomplete settlement response.");
    }

    const paymentTiming =
      settlementForm.paymentTiming ||
      serverPayment.paymentTiming ||
      serverPayment.payment_timing ||
      serverBooking.front_desk_balance_timing ||
      "";

    let finalBooking = {
      ...serverBooking,
      front_desk_balance_timing: paymentTiming,
    };
    let lifecycleNotice = "";

    mergeServerBooking(finalBooking);
    const transaction = normalizeApiTransaction(serverPayment, finalBooking);

    setPaymentTransactions((current) => {
      const next = [
        transaction,
        ...current.filter((item) => String(item.id) !== String(transaction.id)),
      ];
      return next;
    });

    /*
     * The collection timing controls the stay lifecycle:
     * - Pay at Check-in: payment is completed first, then the guest is checked in.
     * - Pay at Check-out: the guest was already checked in earlier; after the
     *   final balance is paid, the booking is checked out and turnover begins.
     */
    try {
      const currentStay = String(
        finalBooking.stay_status ||
        finalBooking.stayStatus ||
        finalBooking.booking_status ||
        finalBooking.bookingStatus ||
        ""
      ).toLowerCase();

      if (
        paymentTiming === "check_in" &&
        currentStay !== "checked in" &&
        currentStay !== "checked out" &&
        currentStay !== "completed"
      ) {
        const checkInPayload = await apiRequest(
          `/admin/bookings/${encodeURIComponent(finalBooking.id)}/check-in`,
          {
            method: "POST",
            body: JSON.stringify({
              notes: "Checked in after front desk balance payment.",
            }),
          }
        );

        if (checkInPayload?.data) {
          finalBooking = {
            ...checkInPayload.data,
            front_desk_balance_timing: paymentTiming,
          };
          mergeServerBooking(finalBooking);
          lifecycleNotice = " Guest check-in completed.";
        }
      }

      if (paymentTiming === "check_out") {
        const checkoutPayload = await apiRequest(
          `/admin/bookings/${encodeURIComponent(finalBooking.id)}/checkout`,
          {
            method: "POST",
            body: JSON.stringify({
              notes: "Checked out after final front desk balance payment.",
            }),
          }
        );

        if (checkoutPayload?.data) {
          finalBooking = {
            ...checkoutPayload.data,
            front_desk_balance_timing: paymentTiming,
          };
          mergeServerBooking(finalBooking);
        }

        if (checkoutPayload?.turnoverTask) {
          setAssignments((current) => [
            checkoutPayload.turnoverTask,
            ...current.filter(
              (item) => item.id !== checkoutPayload.turnoverTask.id
            ),
          ]);
        }

        lifecycleNotice = checkoutPayload?.turnoverTask
          ? " Guest checkout completed and turnover was assigned."
          : " Guest checkout completed.";
      }
    } catch (lifecycleError) {
      lifecycleNotice = ` Payment succeeded, but the stay status needs attention: ${
        lifecycleError instanceof Error
          ? lifecycleError.message
          : "Unable to update the stay status."
      }`;
    }

    setOperationsModalOpen(false);
    setReceiptTransaction(transaction);
    setReceiptModalOpen(true);
    setSettlementBookingId("");
    setSettlementCustomerSearch("");
    setFrontDeskPaymentStep("summary");
    resetSettlementForm();

    window.dispatchEvent(
      new CustomEvent("theVillaBookingPaymentUpdated", {
        detail: { booking: finalBooking, transaction },
      })
    );

    loadAdminData({ silent: true });
    showToast(`${successMessage}${lifecycleNotice}`);
  }

  async function completeSettlement(event) {
    event.preventDefault();
    if (settlementMethod !== "Cash") return;

    const error = validateSettlement();
    if (error) {
      setSettlementError(error);
      showToast(error);
      return;
    }

    const booking = selectedSettlementBooking;
    if (!booking) return;

    setSettlementSubmitting(true);
    setSettlementError("");
    beginAdminRequestLoading("Processing the cash payment...");

    try {
      const payload = await apiRequest(
        `/front-desk/bookings/${encodeURIComponent(booking.id)}/cash-settlement`,
        {
          method: "POST",
          body: JSON.stringify({
            payer_name: settlementForm.payerName.trim(),
            payment_timing: settlementForm.paymentTiming,
            cash_tendered: cashTenderedValue,
            other_charges: settlementCharges.map((charge) => ({
              description: charge.description,
              amount: parseAmount(charge.amount),
            })),
            notes: settlementForm.notes.trim() || null,
          }),
        }
      );
      await applyServerSettlement(
        payload.data,
        `${formatPeso(settlementAmountValue)} cash settlement completed.`
      );
    } catch (requestError) {
      const message = requestError instanceof Error
        ? requestError.message
        : "Cash settlement failed.";
      setSettlementError(message);
      showToast(message);
    } finally {
      endAdminRequestLoading();
      setSettlementSubmitting(false);
    }
  }

  async function startQrPhSettlement() {
    const booking = selectedSettlementBooking;
    const error = validateSettlement();
    if (error) {
      setSettlementError(error);
      showToast(error);
      return;
    }
    if (!booking) return;

    setSettlementSubmitting(true);
    setSettlementError("");
    setQrphPayment({
      status: "creating",
      paymentIntentId: "",
      qrImage: "",
      expiresAt: "",
      error: "",
    });
    beginAdminRequestLoading("Generating the QRPh payment code...");

    try {
      const intentPayload = await apiRequest(
        `/front-desk/bookings/${encodeURIComponent(booking.id)}/qrph-intent`,
        {
          method: "POST",
          body: JSON.stringify({
            payer_name: settlementForm.payerName.trim(),
            payment_timing: settlementForm.paymentTiming,
            other_charges: settlementCharges.map((charge) => ({
              description: charge.description,
              amount: parseAmount(charge.amount),
            })),
            notes: settlementForm.notes.trim() || null,
          }),
        }
      );
      const session = intentPayload.data;
      const publicAuthorization = `Basic ${btoa(`${session.public_key}:`)}`;

      const methodResponse = await fetch(
        "https://api.paymongo.com/v1/payment_methods",
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            Authorization: publicAuthorization,
          },
          body: JSON.stringify({
            data: {
              attributes: {
                type: "qrph",
                expiry_seconds: 1800,
              },
            },
          }),
        }
      );
      const methodPayload = await methodResponse.json();
      if (!methodResponse.ok) {
        throw new Error(
          methodPayload?.errors?.[0]?.detail ||
            "PayMongo could not create the QRPh payment method."
        );
      }

      const paymentMethodId = methodPayload?.data?.id;
      const attachResponse = await fetch(
        `https://api.paymongo.com/v1/payment_intents/${encodeURIComponent(
          session.payment_intent_id
        )}/attach`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            Authorization: publicAuthorization,
          },
          body: JSON.stringify({
            data: {
              attributes: {
                payment_method: paymentMethodId,
                client_key: session.client_key,
              },
            },
          }),
        }
      );
      const attachPayload = await attachResponse.json();
      if (!attachResponse.ok) {
        throw new Error(
          attachPayload?.errors?.[0]?.detail ||
            "PayMongo could not attach the QRPh payment."
        );
      }

      const attributes = attachPayload?.data?.attributes || {};
      const qrImage = attributes?.next_action?.code?.image_url || "";
      if (!qrImage && attributes.status !== "succeeded") {
        throw new Error("PayMongo did not return a QRPh image.");
      }

      setQrphPayment({
        status:
          attributes.status === "processing"
            ? "processing"
            : attributes.status === "succeeded"
            ? "processing"
            : "awaiting_payment",
        paymentIntentId: session.payment_intent_id,
        qrImage,
        expiresAt: session.expires_at,
        error: "",
      });
      showToast("PayMongo QRPh code generated. Waiting for payment confirmation.");

      if (attributes.status === "succeeded") {
        await checkQrPhSettlementStatus(session.payment_intent_id, false);
      }
    } catch (requestError) {
      const message = requestError instanceof Error
        ? requestError.message
        : "QRPh payment could not be started.";
      setQrphPayment((current) => ({
        ...current,
        status: "failed",
        error: message,
      }));
      setSettlementError(message);
      showToast(message);
    } finally {
      endAdminRequestLoading();
      setSettlementSubmitting(false);
    }
  }

  async function checkQrPhSettlementStatus(paymentIntentId, silent = false) {
    if (!paymentIntentId) return;

    if (!silent) {
      beginAdminRequestLoading("Checking the QRPh payment status...");
    }

    try {
      const payload = await apiRequest(
        `/front-desk/payments/${encodeURIComponent(paymentIntentId)}/status`
      );
      const result = payload.data;
      const status = String(result?.payment?.status || "awaiting_payment").toLowerCase();

      if (["paid", "completed"].includes(status)) {
        setQrphPayment((current) => ({ ...current, status: "paid" }));
        await applyServerSettlement(
          result,
          "QRPh payment confirmed by PayMongo. Booking is now fully paid."
        );
        return;
      }

      if (["failed", "expired", "amount_mismatch"].includes(status)) {
        const message =
          status === "expired"
            ? "The PayMongo QRPh code expired. Generate a new code."
            : status === "amount_mismatch"
            ? "The received QRPh amount did not match the booking balance."
            : "The QRPh payment failed. Generate a new code and try again.";
        setQrphPayment((current) => ({
          ...current,
          status,
          error: message,
        }));
        if (!silent) showToast(message);
        return;
      }

      setQrphPayment((current) => ({
        ...current,
        status: status === "processing" ? "processing" : "awaiting_payment",
      }));
      if (!silent) showToast("Payment is not confirmed yet.");
    } catch (requestError) {
      if (!silent) {
        showToast(
          requestError instanceof Error
            ? requestError.message
            : "Unable to check QRPh payment status."
        );
      }
    } finally {
      if (!silent) {
        endAdminRequestLoading();
      }
    }
  }

  function openReceipt(transaction) {
    if (!transaction) return;
    setReceiptTransaction(transaction);
    setReceiptModalOpen(true);
  }

  function printReceipt() {
    window.print();
  }
  function openNewStaffAccount() {
    setStaffAccountMode("create");
    setStaffAccountForm(emptyStaffAccountForm());
    setStaffAccountError("");
    setStaffAccountModalOpen(true);
  }

  function openStaffAccount(staff) {
    setStaffAccountMode("edit");
    setStaffAccountForm({
      id: staff.id,
      name: staff.name,
      email: staff.email,
      username: staff.username,
      role: staff.role,
      department: staff.department,
      shift: staff.shift,
      accountStatus: staff.accountStatus || "Active",
      mustChangePassword: !!staff.mustChangePassword,
    });
    setStaffAccountError("");
    setStaffAccountModalOpen(true);
  }

async function saveStaffAccount(event) {
    event.preventDefault();
    const name = staffAccountForm.name.trim();
    const email = staffAccountForm.email.trim().toLowerCase();
    const username = staffAccountForm.username
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]/g, "");

    if (name.length < 3) {
      setStaffAccountError("Enter the staff member's complete name.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setStaffAccountError("Enter a valid staff email address.");
      return;
    }
    if (username.length < 3) {
      setStaffAccountError("Enter a username with at least 3 characters.");
      return;
    }
    if (!staffAccountForm.role.trim()) {
      setStaffAccountError("Enter the staff role.");
      return;
    }

    const requestBody = {
      fullName: name,
      email,
      username,
      role: "staff",
      department: staffAccountForm.department,
      position: staffAccountForm.role.trim(),
      shift: staffAccountForm.shift,
      mustChangePassword: !!staffAccountForm.mustChangePassword,
    };

    try {
      const isCreate = staffAccountMode === "create";
      const path = isCreate
        ? "/admin/staff"
        : `/admin/staff/${encodeURIComponent(staffAccountForm.id)}`;
      const payload = await apiRequest(path, {
        method: isCreate ? "POST" : "PATCH",
        body: JSON.stringify(requestBody),
      });

      if (payload?.data) {
        const account = normalizeStaffAccount(payload.data);
        setStaffDirectory((current) =>
          isCreate
            ? [...current, account]
            : current.map((staff) =>
                staff.id === account.id ? account : staff
              )
        );
      }

      setStaffAccountModalOpen(false);
      setStaffAccountError("");
      showToast(
        isCreate
          ? `${name}'s staff account was created.`
          : `${name}'s staff account was updated.`
      );

      if (payload?.temporaryPassword) {
        const copied =
          await copyTextToClipboard(
            payload.temporaryPassword
          );

        window.alert(
          `Temporary password for ${name}:\n\n${payload.temporaryPassword}\n\n${
            copied
              ? "The password was copied to your clipboard automatically."
              : "Automatic copy was blocked. Copy the password manually."
          }\n\nThe staff member must change it after signing in.`
        );

        showToast(
          copied
            ? "Staff password copied to clipboard."
            : "Staff account created. Copy the displayed password."
        );
      }
      loadAdminData({ silent: true });
    } catch (error) {
      setStaffAccountError(
        error instanceof Error
          ? error.message
          : "The staff account could not be saved."
      );
    }
  }

async function toggleStaffAccount(staffId) {
    const staff = staffDirectory.find((member) => member.id === staffId);
    if (!staff) return;
    const nextStatus =
      staff.accountStatus === "Disabled" ? "Active" : "Disabled";

    try {
      const payload = await apiRequest(
        `/admin/staff/${encodeURIComponent(staffId)}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ accountStatus: nextStatus }),
        }
      );
      if (payload?.data) {
        const account = normalizeStaffAccount(payload.data);
        setStaffDirectory((current) =>
          current.map((member) =>
            member.id === staffId ? account : member
          )
        );
      }
      showToast(
        `${staff.name}'s account is now ${nextStatus.toLowerCase()}.`
      );
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "The account status could not be changed."
      );
    }
  }

async function resetStaffPassword(staffId) {
    const staff = staffDirectory.find((member) => member.id === staffId);
    if (!staff) return;

    try {
      const payload = await apiRequest(
        `/admin/staff/${encodeURIComponent(staffId)}/reset-password`,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );
      if (payload?.data) {
        const account = normalizeStaffAccount(payload.data);
        setStaffDirectory((current) =>
          current.map((member) =>
            member.id === staffId ? account : member
          )
        );
      }
      if (payload?.temporaryPassword) {
        const copied =
          await copyTextToClipboard(
            payload.temporaryPassword
          );

        window.alert(
          `New temporary password for ${staff.name}:\n\n${payload.temporaryPassword}\n\n${
            copied
              ? "The password was copied to your clipboard automatically."
              : "Automatic copy was blocked. Copy the password manually."
          }\n\nThe staff member must change it after signing in.`
        );
      }
      showToast(`${staff.name}'s password was reset.`);
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "The staff password could not be reset."
      );
    }
  }

  async function checkInBooking(booking) {
    const dateRestriction = getBookingLifecycleDateRestriction(
      normalizeBooking(booking),
      "check_in"
    );
    if (dateRestriction) {
      showToast(dateRestriction, "error");
      return;
    }

    beginAdminRequestLoading("Checking in the guest...");

    try {
      const payload = await apiRequest(
        `/admin/bookings/${encodeURIComponent(booking.id)}/check-in`,
        {
          method: "POST",
          body: JSON.stringify({ notes: null }),
        }
      );
      if (payload?.data) {
        setBookings((current) =>
          current.map((item) =>
            String(item.id) === String(booking.id) ? payload.data : item
          )
        );
      }
      showToast("Guest check-in completed.");
      loadAdminData({ silent: true });
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "Guest check-in could not be completed."
      );
    } finally {
      endAdminRequestLoading();
    }
  }

  async function checkoutBooking(booking) {
    const dateRestriction = getBookingLifecycleDateRestriction(
      normalizeBooking(booking),
      "check_out"
    );
    if (dateRestriction) {
      showToast(dateRestriction, "error");
      return;
    }

    beginAdminRequestLoading("Checking out the guest...");

    try {
      const payload = await apiRequest(
        `/admin/bookings/${encodeURIComponent(booking.id)}/checkout`,
        {
          method: "POST",
          body: JSON.stringify({ notes: null }),
        }
      );
      if (payload?.data) {
        setBookings((current) =>
          current.map((item) =>
            String(item.id) === String(booking.id) ? payload.data : item
          )
        );
      }
      if (payload?.turnoverTask) {
        setAssignments((current) => [
          payload.turnoverTask,
          ...current.filter(
            (item) => item.id !== payload.turnoverTask.id
          ),
        ]);
      }
      showToast(
        payload?.turnoverTask
          ? "Checkout completed and a turnover task was created."
          : "Guest checkout completed."
      );
      loadAdminData({ silent: true });
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "Guest checkout could not be completed."
      );
    } finally {
      endAdminRequestLoading();
    }
  }

  async function signOut() {
    setSigningOut(true);
    try {
      await apiRequest("/admin/session", { method: "DELETE" });
    } catch {
      // Clear the browser session even if the server is temporarily unavailable.
    }

    [
      "theVillaPortalAuth",
      "theVillaAdminAuth",
      "theVillaStaffAuth",
      "theVillaAuthToken",
      "theVillaRefreshToken",
      "theVillaApiToken",
    ].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });

    window.location.replace("/admin-login");
  }

  // ============================================================
  // SHARED RENDERERS
  // ============================================================
  function renderAssignmentList(items, compact = false) {
    if (!items.length) {
      return (
        <EmptyState
          icon={ClipboardList}
          title="No assignments found"
          message="Create an assignment from a confirmed booking or change the filters."
        />
      );
    }
    return (
      <div className={`admin-assignment-list${compact ? " compact" : ""}`}>
        {items.map((assignment) => {
          const staff = staffDirectory.find(
            (member) => member.id === assignment.assignedStaffId
          );
          const status = displayAssignmentStatus(assignment);
          return (
            <button
              type="button"
              key={assignment.id}
              className="admin-assignment-row"
              onClick={() => openAssignment(assignment.id)}
            >
              <span className="admin-assignment-icon">
                {assignment.department === "Maintenance" ? (
                  <Wrench size={18} />
                ) : (
                  <ClipboardCheck size={18} />
                )}
              </span>
              <span className="admin-assignment-main">
                <strong>{assignment.title}</strong>
                <small>
                  {assignment.bookingCode} · {assignment.villaName || assignment.villa} · {assignment.guestName || assignment.guest}
                </small>
              </span>
              {!compact && (
                <span className="admin-assignee-inline">
                  <Avatar
                    name={assignment.assignedTo}
                    online={staff?.online}
                    size={32}
                  />
                  <span>
                    <strong>{assignment.assignedTo}</strong>
                    <small>{assignment.department || assignment.category}</small>
                  </span>
                </span>
              )}
              <span className="admin-assignment-date">
                <strong>{formatDate(assignment.dueDate)}</strong>
                <small>{assignment.dueTime || dueLabel(assignment)}</small>
              </span>
              <PriorityPill priority={assignment.priority} />
              <StatusPill status={status} />
              <ChevronRight size={16} />
            </button>
          );
        })}
      </div>
    );
  }
  function renderAnalyticsData() {

    const months = [
      "Jan","Feb","Mar","Apr",
      "May","Jun","Jul","Aug",
      "Sep","Oct","Nov","Dec"
    ];
  
  
    let monthlyBookings = Array(12).fill(0);
    let monthlyRevenue = Array(12).fill(0);
  
    let villaPerformance = {};
  
    let bookingStatus = {
      Pending:0,
      Confirmed:0,
      "Checked In":0,
      Completed:0,
      Cancelled:0
    };
  
  
    let paymentStatus = {
      Paid:0,
      Partial:0,
      Unpaid:0
    };
  
  
    let guests = new Set();
  
    let repeatGuests = 0;
  
  
    normalizedBookings.forEach((booking)=>{
  
  
      const date = new Date(
        booking.checkIn
      );
  
  
      if(!isNaN(date)){
  
        const month =
        date.getMonth();
  
  
        monthlyBookings[month]++;
  
        monthlyRevenue[month] +=
        Number(
          booking.totalAmount || 0
        );
  
      }
  
  
  
      const villa =
      booking.villaName || "Unknown";
  
  
      villaPerformance[villa] =
      (villaPerformance[villa] || 0)+1;
  
  
  
      const status =
      booking.bookingStatus ||
      "Pending";
  
  
      if(
        bookingStatus[status]
        !== undefined
      ){
        bookingStatus[status]++;
      }
  
  
  
      if(
        booking.paymentStatus
        ==="Paid"
      ){
        paymentStatus.Paid++;
      }
      else if(
        booking.paymentStatus
        ==="Partial" ||
        booking.paymentStatus
        ==="50% Downpayment"
      ){
        paymentStatus.Partial++;
      }
      else{
        paymentStatus.Unpaid++;
      }
  
  
  
      if(
        booking.guestName
      ){
        if(
          guests.has(
            booking.guestName
          )
        ){
          repeatGuests++;
        }
  
        guests.add(
          booking.guestName
        );
      }
  
  
    });
  
  
  
    const villaChart =
    Object.entries(
      villaPerformance
    )
    .map(([name,value])=>({
      name,
      value
    }))
    .sort(
      (a,b)=>b.value-a.value
    );
  
  
  
    const totalBookings =
    normalizedBookings.length;
  
  
    const occupancyRate =
    Math.min(
      100,
      Math.round(
        (totalBookings /
        (months.length*30))
        *100
      )
    );
  
  
  
    return {
  
      months,
  
      monthlyBookings,
  
      monthlyRevenue,
  
      villaChart,
  
      bookingStatus,
  
      paymentStatus,
  
      totalGuests:
      guests.size,
  
      repeatGuests,
  
      occupancyRate,
  
      mostBookedVilla:
      villaChart[0]?.name || "-",
  
      leastBookedVilla:
      villaChart[villaChart.length-1]
      ?.name || "-"
  
    };
  
  }
  // ============================================================
  // PAGES
  // ============================================================
  function renderDashboard(){

    const analytics = renderAnalyticsData();
    
    
    const totalRevenue =
    normalizedBookings.reduce(
    (sum,item)=>sum+item.totalAmount,
    0
    );
    
    
    const totalSales =
    normalizedBookings?.length || 0;
    
    
    const averageSale =
    totalSales
    ? totalRevenue / totalSales
    :0;
    
    
    const highestMonth =
    analytics.monthlyRevenue
    .map((value,index)=>({
    
        month: analytics.months[index],
    
        value:value
    
    }))
    .reduce(
    (a,b)=>
    a.value > b.value ? a : b,
    {
        month:"-",
        value:0
    }
    );
    
    
    return (
    
    <div className="admin-page">
    
    
    <div className="admin-stat-grid">


<div className="admin-stat-card">

<div className="admin-stat-icon blue">
<CalendarDays size={22}/>
</div>

<div>

<span>
Total Bookings
</span>

<strong>
{analytics.totalBookings}
</strong>

</div>

</div>





<div className="admin-stat-card">

<div className="admin-stat-icon green">

<WalletCards size={22}/>

</div>


<div>

<span>
Total Revenue
</span>


<strong>
{formatPeso(totalRevenue)}
</strong>


</div>

</div>








<div className="admin-stat-card">

<div className="admin-stat-icon amber">

<Users size={22}/>

</div>


<div>

<span>
Active Guests
</span>


<strong>
{analytics.totalGuests}
</strong>


</div>


</div>







<div className="admin-stat-card">

<div className="admin-stat-icon blue">

<Home size={22}/>

</div>


<div>

<span>
Most Booked Villa
</span>


<strong>
{analytics.mostBookedVilla}
</strong>


</div>


</div>






<div className="admin-stat-card">

<div className="admin-stat-icon green">

<Percent size={22}/>

</div>


<div>

<span>
Occupancy Rate
</span>


<strong>
{analytics.occupancyRate}%
</strong>


</div>


</div>







<div className="admin-stat-card">

<div className="admin-stat-icon amber">

<UserCheck size={22}/>

</div>


<div>

<span>
Repeat Guests
</span>


<strong>
{analytics.repeatGuests}
</strong>


</div>


</div>





<div className="admin-stat-card">

<div className="admin-stat-icon red">

<CreditCard size={22}/>

</div>


<div>

<span>
Pending Payments
</span>


<strong>

{
analytics.paymentStatus.Unpaid
}

</strong>


</div>


</div>







<div className="admin-stat-card">

<div className="admin-stat-icon red">

<Wrench size={22}/>

</div>


<div>

<span>
Villas Under Maintenance
</span>


<strong>
<button type="button" className="maintenance-dashboard-count" onClick={() => navigate("villas")} aria-label={`View ${villaCatalog.filter(villa => villa.status === "Under Maintenance").length} villas under maintenance`}>{villaCatalog.filter(villa => villa.status === "Under Maintenance").length}</button>
</strong>


</div>


</div>



</div>
<section className="admin-dashboard-grid">

<VillaAnalyticsCharts
    analytics={analytics}
/>

</section>
   
    
    </div>
    
    );
    
    }
  // An unpaid initial booking cannot be settled manually: the original
  // PayMongo downpayment or full amount must first be verified by the backend.
  function getBookingOperation(booking) {
    if (!booking || hasCompletedCheckOut(booking)) return "";
    if (["cancelled", "canceled", "expired", "refunded"].includes(
      normalizeStayLabel(booking.bookingStatus || booking.booking_status)
    )) return "";
    // Already checked in: the admin can settle the balance or check out.
    // Do not hide an existing stay because older schema payment metadata is incomplete.
    if (hasAdminCheckedIn(booking)) return booking.balanceAmount > 0 ? "payment" : "checkout";
    // Before check-in, retain the existing Bookings-page payment/arrival flow.
    if (!booking.downpaymentVerified) return "";
    return booking.balanceAmount > 0 ? "payment" : "checkin";
  }

  function startBookingOperation(booking) {
    const operation = getBookingOperation(booking);
    if (!operation) return;
    if (operation === "payment") {
      openSettlement(booking);
    } else {
      setOperationsBookingId(booking.id);
      setOperationsMode(operation);
      setOperationsStage("review");
      setOperationsModalOpen(true);
    }
  }

  function closeOperationsModal() {
    if (operationsBusy || settlementSubmitting) return;
    setOperationsModalOpen(false);
    setOperationsBookingId("");
    setSettlementBookingId("");
    resetSettlementForm();
  }

  async function continuePaymentTiming() {
    const selected = normalizedBookings.find((b) => String(b.id) === String(operationsBookingId));
    const timing = settlementForm.paymentTiming;
    if (!selected || !["check_in", "check_out"].includes(timing)) {
      setSettlementError("Select Pay at Check-in or Pay at Check-out.");
      return;
    }
    setOperationsBusy(true);
    setSettlementError("");
    try {
      const payload = await apiRequest(
        `/front-desk/bookings/${encodeURIComponent(selected.id)}/payment-timing`,
        { method: "PUT", body: JSON.stringify({ payment_timing: timing }) }
      );
      if (payload?.data?.booking) {
        mergeServerBooking({ ...payload.data.booking, front_desk_balance_timing: timing });
      }
      const alreadyCheckedIn = String(selected.stayStatus).toLowerCase() === "checked in";
      if (timing === "check_out" && !alreadyCheckedIn) {
        setOperationsMode("checkin");
        setOperationsStage("review");
      } else {
        setOperationsStage("methods");
      }
    } catch (error) {
      setSettlementError(error instanceof Error ? error.message : "Unable to save payment timing.");
    } finally {
      setOperationsBusy(false);
    }
  }

  async function confirmOperationsLifecycle(booking, action) {
    if (!booking || operationsBusy) return;
    // The backend validates payment and lifecycle; checkout dates are unrestricted.
    const restriction = getBookingLifecycleDateRestriction(booking, action === "checkin" ? "check_in" : "check_out");
    if (restriction) {
      setSettlementError(restriction);
      return;
    }
    setOperationsBusy(true);
    setSettlementError("");
    try {
      const payload = await apiRequest(
        `/admin/bookings/${encodeURIComponent(booking.id)}/${action === "checkin" ? "check-in" : "checkout"}`,
        { method: "POST", body: JSON.stringify({ notes: null }) }
      );
      if (payload?.data) mergeServerBooking(payload.data);
      if (payload?.turnoverTask) {
        setAssignments((current) => [payload.turnoverTask, ...current.filter((item) => item.id !== payload.turnoverTask.id)]);
      }
      await loadAdminData({ silent: true });
      showToast(action === "checkin" ? "Guest checked in successfully." : "Guest checked out successfully.");
      closeSettlement();
      setOperationsModalOpen(false);
      setOperationsBookingId("");
    } catch (error) {
      setSettlementError(error instanceof Error ? error.message : "Unable to update the guest stay.");
    } finally {
      setOperationsBusy(false);
    }
  }

  function renderOperationsModal() {
    const selected = normalizedBookings.find((b) => String(b.id) === String(operationsBookingId));
    const isCheckin = operationsMode === "checkin";
    const isCheckout = operationsMode === "checkout";
    const isPayment = operationsMode === "payment";
    const busy = operationsBusy || settlementSubmitting || frontDeskFlowSubmitting;
    const queue = normalizedBookings
      .filter((booking) => hasAdminCheckedIn(booking))
      .filter((booking) => {
        const search = operationsQuery.trim().toLowerCase();
        const matchesSearch = !search ||
          [booking.guestName, booking.bookingCode, booking.villaName].join(" ").toLowerCase().includes(search);
        const action = getBookingOperation(booking);
        const matchesFilter = operationsFilter === "All" ||
          (operationsFilter === "Payment Due" && action === "payment") ||
          (operationsFilter === "Ready to Check Out" && action === "checkout");
        return matchesSearch && matchesFilter && Boolean(action);
      })
      .sort((first, second) => String(first.checkOut || "9999").localeCompare(String(second.checkOut || "9999")));

    return (
      <div className="admin-modal-backdrop admin-ops-backdrop" onClick={closeOperationsModal}>
        <section className="admin-ops-modal" role="dialog" aria-modal="true" aria-label="Guest check-in, check-out and payment" onClick={(event) => event.stopPropagation()}>
          <header className="admin-ops-header">
            <div className="admin-ops-header-mark"><ClipboardCheck size={22} /></div>
            <div className="admin-ops-header-title">
              <span className="admin-eyebrow">The Villa · Guest operations</span>
              <h2>{operationsMode === "queue" ? "Check In & Out" : isPayment ? "Settle Remaining Balance" : isCheckin ? "Guest Check In" : "Guest Check Out"}</h2>
              <p>{operationsMode === "queue" ? "Only guests checked in by an administrator are listed here." : selected ? `${selected.bookingCode} · ${selected.villaName}` : "Booking details"}</p>
            </div>
            <button className="admin-ops-close" type="button" onClick={closeOperationsModal} aria-label="Close modal" disabled={busy}><X size={19}/></button>
          </header>
          <div className="admin-ops-content">
            {operationsMode === "queue" && (
              <>
                <div className="admin-ops-filters">
                  <label className="admin-bookings-search"><Search size={17}/><input type="search" value={operationsQuery} onChange={(e) => setOperationsQuery(e.target.value)} placeholder="Search guest or booking..." /></label>
                  <div className="admin-ops-switch" role="group" aria-label="Filter guests">
                    {["All", "Payment Due", "Ready to Check Out"].map((item) => <button type="button" className={operationsFilter === item ? "active" : ""} onClick={() => setOperationsFilter(item)} key={item}>{item}</button>)}
                  </div>
                </div>
                <div className="admin-ops-queue">
                  {queue.map((booking) => (
                    <article className="admin-ops-queue-row" key={booking.id}>
                      <Avatar name={booking.guestName} size={42}/>
                      <div className="admin-ops-guest"><strong>{booking.guestName}</strong><span>{booking.bookingCode} · {booking.villaName}</span><small>{formatDate(booking.checkIn)} – {formatDate(booking.checkOut)}</small></div>
                      <div className="admin-ops-queue-status"><StatusPill status="Checked In"/><small>{formatPeso(booking.balanceAmount)} due</small></div>
                      <button type="button" className="admin-btn-primary" onClick={() => startBookingOperation(booking)}>{getBookingOperation(booking) === "payment" ? "Pay" : getBookingOperation(booking) === "checkin" ? "Check In" : "Check Out"}<ChevronRight size={16}/></button>
                    </article>
                  ))}
                  {!queue.length && <div className="admin-ops-empty"><CalendarDays size={30}/><strong>No active checked-in guests</strong><p>Guests appear here after an administrator confirms Check In from Bookings. Completed checkouts are listed in Booking History.</p></div>}
                </div>
              </>
            )}
            {selected && (isPayment || isCheckin || isCheckout) && (
              <>
                <div className="admin-ops-summary">
                  <div className="admin-ops-summary-top"><Avatar name={selected.guestName} size={48}/><div><small>Reservation guest</small><strong>{selected.guestName}</strong><span>{selected.bookingCode}</span></div><StatusPill status={selected.paymentStatus}/></div>
                  <div className="admin-ops-facts">
                    <div><small>Villa</small><strong>{selected.villaName}</strong></div>
                    <div><small>Check In</small><strong>{formatDate(selected.checkIn)}</strong></div>
                    <div><small>Check Out</small><strong>{formatDate(selected.checkOut)}</strong></div>
                    <div><small>Guests</small><strong>{selected.guestCount || 1}</strong></div>
                    <div><small>Amount paid</small><strong>{formatPeso(selected.amountPaid)}</strong></div>
                    <div><small>Balance due</small><strong>{formatPeso(selected.balanceAmount)}</strong></div>
                  </div>
                </div>
                {isPayment && operationsStage === "timing" && (
                  <div className="admin-ops-section">
                    <h3>When will the guest settle the balance?</h3>
                    <p>Select the guest’s preferred payment timing. It will be saved with their booking.</p>
                    <div className="admin-ops-choices">
                      {(String(selected.stayStatus).toLowerCase() === "checked in"
                        ? [{id:"check_out",title:"Pay at Check-out",note:"Collect the remaining balance using Cash or QRPh during departure.",Icon:Clock3}]
                        : [{id:"check_in",title:"Pay at Check-in",note:"Collect the balance using Cash or QRPh on arrival.",Icon:CalendarDays},{id:"check_out",title:"Pay at Check-out",note:"Check the guest in first, then collect the balance at departure.",Icon:Clock3}]
                      ).map(({id,title,note,Icon}) => (
                        <button type="button" key={id} className={`admin-ops-choice ${settlementForm.paymentTiming === id ? "selected" : ""}`} onClick={() => {setSettlementForm((current) => ({...current,paymentTiming:id,cashTendered:""}));setSettlementError("");}}>
                          <Icon size={21}/><span><strong>{title}</strong><small>{note}</small></span><span className="admin-ops-radio">{settlementForm.paymentTiming === id && <Check size={14}/>}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {isPayment && operationsStage === "methods" && (
                  <form id="admin-ops-cash-form" onSubmit={completeSettlement} className="admin-ops-section">
                    <div className="admin-ops-method-top"><div><h3>Payment at {settlementForm.paymentTiming === "check_out" ? "Check-out" : "Check-in"}</h3><p>Collect the verified balance using a front desk payment method.</p></div><span className="admin-ops-due">{formatPeso(settlementAmountValue)}</span></div>
                    {settlementCharges.length > 0 && <div className="admin-ops-charge-breakdown"><strong>Included other charges</strong>{settlementCharges.map((charge) => <div key={charge.id}><span>{charge.description}</span><b>{formatPeso(charge.amount)}</b></div>)}<div><span>Room balance</span><b>{formatPeso(selected.balanceAmount)}</b></div></div>}
                    <div className="admin-ops-choices payment">
                      {FRONT_DESK_PAYMENT_METHODS.map(({id,label,description,icon:Icon}) => <button type="button" key={id} className={`admin-ops-choice ${settlementMethod === id ? "selected" : ""}`} disabled={settlementChargesLocked || busy} onClick={() => {setSettlementMethod(id);setSettlementError("");resetQrPhPayment();}}><Icon size={21}/><span><strong>{label}</strong><small>{description}</small></span><span className="admin-ops-radio">{settlementMethod === id && <Check size={14}/>}</span></button>)}
                    </div>
                    <label className="admin-ops-field">Payer name<input type="text" value={settlementForm.payerName} onChange={(event) => setSettlementForm((current) => ({...current,payerName:event.target.value}))} disabled={settlementChargesLocked || busy} required minLength={2}/></label>
                    {settlementMethod === "Cash" ? <>
                      <label className="admin-ops-field">Cash received (PHP)<input type="number" min={settlementAmountValue} step="0.01" value={settlementForm.cashTendered} onChange={(event) => setSettlementForm((current) => ({...current,cashTendered:event.target.value}))} placeholder="Enter cash tendered" required /></label>
                      {hasCashTendered && <div className="admin-ops-change"><span>{cashShortage ? "Amount short" : "Change to return"}</span><strong>{formatPeso(cashShortage || settlementChange)}</strong></div>}
                    </> : <div className="admin-ops-qr">
                      {qrphPayment.qrImage ? <img src={qrphPayment.qrImage} alt="PayMongo QRPh code; scan to pay"/> : <QrCode size={44} strokeWidth={1.3}/>}
                      <strong>{qrphPayment.qrImage ? "Scan QRPh to pay" : "Generate a secure QRPh code"}</strong>
                      <p>{qrphPayment.status === "awaiting_payment" || qrphPayment.status === "processing" ? "Waiting for PayMongo to confirm the payment automatically…" : "The booking is updated only after the payment is confirmed."}</p>
                      {qrphPayment.error && <p className="admin-ops-error">{qrphPayment.error}</p>}
                    </div>}
                  </form>
                )}
                {(isCheckin || isCheckout) && <section className="admin-ops-section admin-ops-confirm"><span className="admin-ops-confirm-icon"><ShieldCheck size={26}/></span><h3>{isCheckin ? "Ready to welcome the guest?" : "Ready to complete the stay?"}</h3><p>{isCheckin ? "Confirm the guest's arrival and mark this reservation as checked in." : "This reservation is fully paid. Confirm departure to check out the guest and begin turnover."}</p>{isCheckin && selected.balanceAmount > 0 && settlementForm.paymentTiming === "check_out" && <p className="admin-ops-deferred">Remaining {formatPeso(selected.balanceAmount)} scheduled for check-out.</p>}</section>}
              </>
            )}
            {settlementError && operationsMode !== "queue" && <div className="admin-ops-error" role="alert"><AlertCircle size={17}/>{settlementError}</div>}
          </div>
          {operationsMode !== "queue" && <footer className="admin-ops-footer">
            <button type="button" className="admin-btn-ghost" disabled={busy || settlementChargesLocked} onClick={() => { if (isPayment && operationsStage === "methods") {setOperationsStage("timing");resetQrPhPayment();} else {setOperationsMode("queue");setOperationsBookingId("");setSettlementError("");} }}><ChevronLeft size={15}/> Back</button>
            {isPayment && operationsStage === "timing" && <button type="button" className="admin-btn-primary" disabled={busy || !settlementForm.paymentTiming} onClick={continuePaymentTiming}>{operationsBusy ? <LoaderCircle className="admin-spin" size={16}/> : <ChevronRight size={16}/>} Continue</button>}
            {isPayment && operationsStage === "methods" && settlementMethod === "Cash" && <button type="submit" form="admin-ops-cash-form" className="admin-btn-primary" disabled={busy || !cashIsSufficient}>{busy ? <LoaderCircle className="admin-spin" size={16}/> : <Banknote size={16}/>} Confirm Cash Payment</button>}
            {isPayment && operationsStage === "methods" && settlementMethod === "QRPh" && <button type="button" className="admin-btn-primary" disabled={busy || settlementChargesLocked} onClick={startQrPhSettlement}>{busy ? <LoaderCircle className="admin-spin" size={16}/> : <QrCode size={16}/>} {qrphPayment.qrImage ? "Generate New QR" : "Generate QRPh"}</button>}
            {(isCheckin || isCheckout) && <button type="button" className="admin-btn-primary" disabled={busy} onClick={() => confirmOperationsLifecycle(selected, isCheckin ? "checkin" : "checkout")}>{busy ? <LoaderCircle className="admin-spin" size={16}/> : <CheckCircle2 size={16}/>} {isCheckin ? "Check In" : "Check Out"}</button>}
          </footer>}
        </section>
      </div>
    );
  }

  function renderBookings() {
    return (
      <div className="admin-page admin-bookings-page">
        {bookingDataError && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert">
          <span>{bookingDataError}</span>
          <button type="button" className="admin-btn-secondary" onClick={() => loadAdminData()}>Retry bookings</button>
        </div>}
        <div className="admin-bookings-controls">
            <div className="admin-bookings-toolbar">
              <label className="admin-bookings-search">
                <Search size={17} />
                <input
                  type="search"
                  placeholder="Search guest, villa or reference..."
                  value={globalSearch}
                  onChange={(event) => setGlobalSearch(event.target.value)}
                  aria-label="Search bookings"
                />
              </label>
              <select
                value={bookingFilter}
                onChange={(event) => setBookingFilter(event.target.value)}
                aria-label="Filter booking payment status"
              >
              <option>All</option>
              <option>Paid</option>
              <option>Unpaid</option>
              <option>Completed</option>
              <option>Overdue/Cancelled</option>
              </select>
            </div>
          <button type="button" className="admin-btn-primary admin-bookings-operations" onClick={() => {
            setOperationsMode("queue"); setOperationsQuery(""); setOperationsFilter("All"); setOperationsModalOpen(true);
          }}><ClipboardCheck size={16} /> Check In / Check Out</button>
        </div>
        <section className="admin-panel">
          <div className="admin-table-wrap">
            <table className="admin-data-table">
              <thead>
                <tr>
                  <th>Guest</th>
                  <th>Booking</th>
                  <th>Stay</th>
                  <th>Payment</th>
                  <th>Balance</th>
                  <th>Assignments</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredBookings.map((booking) => {
                  const bookingAssignments = assignments.filter(
                    (assignment) => assignment.bookingId === booking.id
                  );
                  const preparationAssignment = bookingAssignments.find(
                    assignment => assignment.assignmentType === "housekeeping-pre-arrival" && assignment.status !== "Cancelled"
                  );
                  const preparationNeeded = booking.bookingStatus === "Confirmed" && booking.downpaymentVerified
                    && booking.checkIn >= today && !preparationAssignment;
                  const activeCount = bookingAssignments.filter(
                    (assignment) =>
                      displayAssignmentStatus(assignment) !== "Completed"
                  ).length;
                  return (
                    <tr key={booking.id}>
                      <td>
                        <div className="admin-person-cell">
                          <Avatar name={booking.guestName} size={36} />
                          <span>
                            <strong>{booking.guestName}</strong>
                            <small>{booking.phone}</small>
                          </span>
                        </div>
                      </td>
                      <td>
                        <strong>{booking.bookingCode}</strong>
                        <small>{booking.villaName}</small>
                      </td>
                      <td>
                        <strong>{formatDate(booking.checkIn)}</strong>
                        <small>to {formatDate(booking.checkOut)}</small>
                      </td>
                      <td>
                        <StatusPill status={booking.paymentStatus} />
                      </td>
                      <td>
                        <strong>{formatPeso(booking.balanceAmount)}</strong>
                      </td>
                      <td>
                        <strong>{bookingAssignments.length}</strong>
                        <small>{activeCount} active</small>
                        {preparationAssignment && <small>{preparationAssignment.source === "automatic-booking-preparation" ? "Auto-assigned" : "Preparation"}: {preparationAssignment.assignedTo || "Housekeeping"}</small>}
                        {preparationNeeded && <small className="admin-preparation-needed">Preparation staff needed</small>}
                      </td>
                      <td className="admin-booking-action-cell">

<div className="admin-booking-actions">

<button
  type="button"
  className="admin-btn-secondary admin-table-action-btn"
  onClick={() => openBookingDetails(booking)}
>
  <Eye size={14}/> Details
</button>
{getBookingOperation(booking) && (
  <button
    type="button"
    className="admin-btn-primary admin-table-action-btn"
    onClick={() => startBookingOperation(booking)}
  >
    {getBookingOperation(booking) === "payment" ? <WalletCards size={14} /> : <CheckCircle2 size={14} />}
    {getBookingOperation(booking) === "payment" ? "Pay" : getBookingOperation(booking) === "checkin" ? "Check In" : "Check Out"}
  </button>
)}
</div>

</td>
                    </tr>
                  );
                })}
                {!filteredBookings.length && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState
                        icon={CalendarDays}
                        title="No bookings found"
                        message="Change the search or filter to see more reservations."
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  }

  function renderHistory() {
    const villas = [
      "All",
      ...Array.from(
        new Set(
          bookingHistory
            .map((item) => item.villaName)
            .filter(Boolean)
        )
      ),
    ];

    const filteredHistory = bookingHistory.filter((item) => {
      const keyword = historySearch.trim().toLowerCase();

      const matchesSearch =
        !keyword ||
        String(item.guestName || "").toLowerCase().includes(keyword) ||
        String(item.bookingCode || "").toLowerCase().includes(keyword) ||
        String(item.villaName || "").toLowerCase().includes(keyword);

      const matchesStatus =
        historyStatusFilter === "All" ||
        String(item.historyStatus || "Completed") === historyStatusFilter;

      const matchesVilla =
        historyVillaFilter === "All" ||
        item.villaName === historyVillaFilter;

      return matchesSearch && matchesStatus && matchesVilla;
    });

    return (
      <div className="admin-page admin-booking-history-page">
        <section className="admin-panel booking-history-panel">
          <header className="admin-panel-header">
            <div>
              <h3><History size={18}/> Booking History</h3>
              <p>Completed admin checkouts and past-due reservations are archived here.</p>
            </div>
            <strong>{filteredHistory.length} Records</strong>
          </header>

          <div className="admin-history-toolbar">
            <div className="admin-search-box">
              <Search size={16}/>
              <input
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                placeholder="Search guest, booking code, villa..."
              />
            </div>

            <select
              value={historyStatusFilter}
              onChange={(e) => setHistoryStatusFilter(e.target.value)}
            >
              <option value="All">All Status</option>
              <option value="Completed">Completed</option>
              <option value="Overdue">Overdue</option>
            </select>

            <select
              value={historyVillaFilter}
              onChange={(e) => setHistoryVillaFilter(e.target.value)}
            >
              {villas.map((villa) => (
                <option key={villa} value={villa}>{villa}</option>
              ))}
            </select>
          </div>

          <div className="booking-history-grid">
            {filteredHistory.map((item) => (
              <article className="booking-history-card" key={item.id}>
                <div className="booking-history-card-top">
                  <div>
                    <h4>{item.guestName || "Guest"}</h4>
                    <p>{item.bookingCode || "No booking code"}</p>
                  </div>

                  <span className={`admin-status-pill status-${slug(item.historyStatus || "completed")}`}>
                    {item.historyStatus || "Completed"}
                  </span>
                </div>

                <div className="booking-history-details">
                  <div><small>Villa</small><strong>{item.villaName || "N/A"}</strong></div>
                  <div><small>Check In</small><strong>{formatDate(item.checkIn)}</strong></div>
                  <div><small>Check Out</small><strong>{formatDate(item.checkOut)}</strong></div>
                  <div><small>Status</small><strong>{item.action || "Completed Stay"}</strong></div>
                  <div><small>Recorded</small><strong>{formatDateTime(item.completedAt)}</strong></div>
                </div>
              </article>
            ))}
          </div>

          {!filteredHistory.length && (
            <EmptyState
              icon={History}
              title="No booking history found"
              message="Try changing the search or filters."
            />
          )}
        </section>
      </div>
    );
  }

  function renderAssignmentMonitor() {
    return <AdminTaskHub key="team-board" tasks={assignments} bookings={normalizedBookings} staff={staffDirectory} openTask={openAssignment} openBooking={openBookingDetails} manageStaff={()=>navigate("staff")} />;
  }

  function renderStaff() {
    const activeAccountCount = staffDirectory.filter(
      (staff) => staff.accountStatus !== "Disabled"
    ).length;
    const disabledAccountCount = staffDirectory.length - activeAccountCount;
    const onlineCount = staffDirectory.filter(
      (staff) => staff.online && staff.accountStatus !== "Disabled"
    ).length;

    return (
      <div className="admin-page admin-staff-page admin-staff-accounts-page">
        <section className="admin-directory-heading">
          <div>
            <span className="admin-eyebrow">People and access management</span>
            <h2>Staff Directory & Accounts</h2>
            <p>
              Maintain staff contact information, roles, departments, shifts,
              usernames, password-reset requirements, and account access.
            </p>
          </div>
          <button
            type="button"
            className="admin-btn-primary"
            onClick={openNewStaffAccount}
          >
            <UserPlus size={16} /> Add Staff Account
          </button>
        </section>

        <section className="admin-staff-account-stats">
          <article>
            <span><Users size={20} /></span>
            <div><small>Total staff</small><strong>{staffDirectory.length}</strong></div>
          </article>
          <article>
            <span className="green"><ShieldCheck size={20} /></span>
            <div><small>Active accounts</small><strong>{activeAccountCount}</strong></div>
          </article>
          <article>
            <span className="blue"><CheckCircle2 size={20} /></span>
            <div><small>Online now</small><strong>{onlineCount}</strong></div>
          </article>
          <article>
            <span className="red"><Power size={20} /></span>
            <div><small>Disabled</small><strong>{disabledAccountCount}</strong></div>
          </article>
        </section>

        <section className="admin-panel admin-staff-account-panel">
          <header className="admin-panel-header">
            <div>
              <h3><UserCog size={17} /> Staff account register</h3>
              <p>Account access and staff profile information in one place.</p>
            </div>
            <span className="admin-record-count">
              {filteredStaffWorkloads.length} records
            </span>
          </header>

          <div className="admin-table-wrap">
            <table className="admin-data-table admin-staff-account-table">
              <thead>
                <tr>
                  <th>Staff member</th>
                  <th>Account</th>
                  <th>Department / Shift</th>
                  <th>Workload</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredStaffWorkloads.map((staff) => (
                  <tr key={staff.id}>
                    <td>
                      <div className="admin-person-cell">
                        <Avatar name={staff.name} online={staff.online} size={40} />
                        <span>
                          <strong>{staff.name}</strong>
                          <small>{staff.role}</small>
                        </span>
                      </div>
                    </td>
                    <td>
                      <strong>{staff.username}</strong>
                      <small>{staff.email}</small>
                      {staff.mustChangePassword && (
                        <span className="admin-password-reset-label">
                          Password change required
                        </span>
                      )}
                    </td>
                    <td>
                      <strong>{staff.department}</strong>
                      <small>{staff.shift}</small>
                    </td>
                    <td>
                      <div className="admin-workload-inline">
                        <span><small>Active</small><strong>{staff.active}</strong></span>
                        <span><small>Review</small><strong>{staff.review}</strong></span>
                        <span><small>Overdue</small><strong>{staff.overdue}</strong></span>
                      </div>
                    </td>
                    <td>
                      <StatusPill status={staff.accountStatus || "Active"} />
                      <small className="admin-last-login">
                        {staff.lastLogin
                          ? `Last login ${formatRelative(staff.lastLogin)}`
                          : "No recorded login"}
                      </small>
                    </td>
                    <td>
                      <div className="admin-staff-account-actions">
                        <button
                          type="button"
                          title="Manage staff account"
                          onClick={() => openStaffAccount(staff)}
                        >
                          <UserCog size={15} /> Manage
                        </button>
                        <button
                          type="button"
                          title={
                            staff.accountStatus === "Disabled"
                              ? "Enable account"
                              : "Disable account"
                          }
                          className={
                            staff.accountStatus === "Disabled" ? "enable" : "disable"
                          }
                          onClick={() => toggleStaffAccount(staff.id)}
                        >
                          <Power size={15} />
                          {staff.accountStatus === "Disabled" ? "Enable" : "Disable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredStaffWorkloads.length && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState
                        icon={Users}
                        title="No staff accounts found"
                        message="Change the search or add a new staff account."
                        action="Add Staff Account"
                        onAction={openNewStaffAccount}
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  }

  function renderPayments() {
    const selected = selectedSettlementBooking;

    const selectedVillaCatalog = selected
      ? villaCatalog.find((villa) => {
          const bookingVillaValues = [
            selected.villa_id,
            selected.villaId,
            selected.villaName,
            selected.villa,
            selected.room,
          ]
            .filter(Boolean)
            .map((value) => String(value).trim().toLowerCase());

          const catalogVillaValues = [
            villa.id,
            villa.title,
            villa.landingTitle,
          ]
            .filter(Boolean)
            .map((value) => String(value).trim().toLowerCase());

          return bookingVillaValues.some((bookingValue) =>
            catalogVillaValues.some(
              (catalogValue) =>
                catalogValue === bookingValue ||
                catalogValue.includes(bookingValue) ||
                bookingValue.includes(catalogValue)
            )
          );
        })
      : null;

    const villaNumber = selected
      ? selected.villaNumber ||
        selected.villa_number ||
        selected.villaNo ||
        selected.villa_no ||
        selected.roomNumber ||
        selected.room_number ||
        selected.villaName ||
        "Villa"
      : "—";

    const villaImage = selected
      ? selected.villaImageUrl ||
        selected.villa_image_url ||
        selected.villaImage ||
        selected.villa_image ||
        selected.imageUrl ||
        selected.image_url ||
        selectedVillaCatalog?.imageUrl ||
        "/image1.jpg"
      : "/image1.jpg";

    const stayStatus = selected?.stayStatus || "Not Checked In";
    const normalizedStayStatus = String(stayStatus).trim().toLowerCase();
    const isCheckedIn = normalizedStayStatus === "checked in";
    const isCheckedOut =
      normalizedStayStatus === "checked out" ||
      normalizedStayStatus === "completed";

    const selectedTiming =
      settlementForm.paymentTiming ||
      selected?.balancePaymentTiming ||
      selected?.front_desk_balance_timing ||
      "";

    const paymentTimingLabel =
      selectedTiming === "check_out"
        ? "Pay at Check-out"
        : selectedTiming === "check_in"
        ? "Pay at Check-in"
        : "Not selected";

    const checkInDateRestriction = selected
      ? getBookingLifecycleDateRestriction(selected, "check_in")
      : "";
    const checkOutDateRestriction = selected
      ? getBookingLifecycleDateRestriction(selected, "check_out")
      : "";

    const flowDateRestriction =
      !selectedTiming
        ? ""
        : selectedTiming === "check_in"
        ? checkInDateRestriction
        : !isCheckedIn
        ? checkInDateRestriction
        : checkOutDateRestriction;

    const selectSearchResult = (booking) => {
      openSettlement(booking);
      setSettlementCustomerSearch("");
    };

    const choosePaymentTiming = (timing) => {
      if (frontDeskFlowSubmitting || isCheckedOut) return;
      setSettlementForm((current) => ({
        ...current,
        paymentTiming: timing,
        cashTendered: "",
      }));
      setSettlementError("");
      resetQrPhPayment();
    };

    const saveTimingChoice = async () => {
      if (!selected) {
        throw new Error("Select a booking first.");
      }
      if (!["check_in", "check_out"].includes(selectedTiming)) {
        throw new Error(
          "Ask the guest whether the remaining balance will be paid at check-in or check-out."
        );
      }

      if (
        selected.balancePaymentTiming === selectedTiming ||
        selected.front_desk_balance_timing === selectedTiming
      ) {
        return {
          data: {
            booking: selected,
            paymentTiming: selectedTiming,
          },
        };
      }

      const payload = await apiRequest(
        `/front-desk/bookings/${encodeURIComponent(
          selected.id
        )}/payment-timing`,
        {
          method: "PUT",
          body: JSON.stringify({
            payment_timing: selectedTiming,
          }),
        }
      );

      const serverBooking = payload?.data?.booking;
      if (serverBooking) {
        mergeServerBooking({
          ...serverBooking,
          front_desk_balance_timing: selectedTiming,
        });
      }

      return payload;
    };

    const handleSummaryAction = async () => {
      if (!selected || frontDeskFlowSubmitting || isCheckedOut) return;

      if (flowDateRestriction) {
        setSettlementError(flowDateRestriction);
        showToast(flowDateRestriction, "error");
        return;
      }

      setFrontDeskFlowSubmitting(true);
      setSettlementError("");
      beginAdminRequestLoading(
        selectedTiming === "check_out" && !isCheckedIn
          ? "Checking in the guest and saving the checkout payment choice..."
          : "Saving the guest payment choice..."
      );

      try {
        await saveTimingChoice();

        if (selectedTiming === "check_out" && !isCheckedIn) {
          const payload = await apiRequest(
            `/admin/bookings/${encodeURIComponent(selected.id)}/check-in`,
            {
              method: "POST",
              body: JSON.stringify({
                notes:
                  "Guest checked in with remaining balance deferred to checkout.",
              }),
            }
          );

          if (payload?.data) {
            mergeServerBooking({
              ...payload.data,
              front_desk_balance_timing: "check_out",
            });
          }

          setSettlementForm((current) => ({
            ...current,
            paymentTiming: "check_out",
          }));

          await loadAdminData({ silent: true });
          showToast(
            "Guest checked in. The remaining balance is scheduled for checkout."
          );
          return;
        }

        setFrontDeskPaymentStep("payment");
        window.requestAnimationFrame(() => {
          document
            .getElementById("frontdesk-payment-checkout")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "The front desk workflow could not be updated.";
        setSettlementError(message);
        showToast(message);
      } finally {
        endAdminRequestLoading();
        setFrontDeskFlowSubmitting(false);
      }
    };

    const returnToSummary = () => {
      setSettlementError("");
      resetQrPhPayment();
      setFrontDeskPaymentStep("summary");
      window.requestAnimationFrame(() => {
        document
          .getElementById("frontdesk-booking-summary")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    };

    const summaryActionLabel =
      !selectedTiming
        ? "Choose Payment Timing"
        : selectedTiming === "check_in"
        ? isCheckedIn
          ? "Continue to Payment"
          : "Continue to Check-in Payment"
        : isCheckedIn
        ? "Proceed to Checkout Payment"
        : "Confirm & Check In Guest";

    return (
      <div className="admin-page admin-payments-page admin-fdx-page admin-fd-flow-v2">
        <section className="admin-panel admin-fdx-shell">
          <div className="admin-fdx-progress" aria-label="Front desk progress">
            <div
              className={
                frontDeskPaymentStep === "summary"
                  ? "admin-fdx-progress-item active"
                  : "admin-fdx-progress-item complete"
              }
            >
              <span>
                {frontDeskPaymentStep === "payment" ? (
                  <Check size={13} />
                ) : (
                  "1"
                )}
              </span>
              <div>
                <strong>Booking</strong>
                <small>Guest choice & stay status</small>
              </div>
            </div>

            <div className="admin-fdx-progress-line" />

            <div
              className={
                frontDeskPaymentStep === "payment"
                  ? "admin-fdx-progress-item active"
                  : "admin-fdx-progress-item"
              }
            >
              <span>2</span>
              <div>
                <strong>Payment</strong>
                <small>Collect remaining balance</small>
              </div>
            </div>
          </div>

          {frontDeskPaymentStep === "summary" ? (
            <div
              className="admin-fdx-summary-screen"
              id="frontdesk-booking-summary"
            >
              <header className="admin-fdx-screen-header admin-fd-v2-heading">
                <div>
                  <h2>Booking Summary</h2>
                  <p>
                    Search the reservation, verify the stay, then ask when the
                    guest wants to settle the remaining balance.
                  </p>
                </div>
              </header>

              <div className="admin-fdx-search-wrap">
                <label className="admin-fdx-search">
                  <Search size={17} />
                  <input
                    type="search"
                    autoComplete="off"
                    aria-label="Search booking by full code, last code part, or guest name"
                    placeholder="Search full code, last code, or guest name..."
                    value={settlementCustomerSearch}
                    onChange={(event) => {
                      setSettlementCustomerSearch(event.target.value);
                      setSettlementError("");
                      if (selected) {
                        setSettlementBookingId("");
                        resetSettlementForm();
                      }
                    }}
                  />
                  {settlementCustomerSearch && (
                    <button
                      type="button"
                      aria-label="Clear booking search"
                      onClick={() => {
                        setSettlementCustomerSearch("");
                        setSettlementError("");
                      }}
                    >
                      <X size={14} />
                    </button>
                  )}
                </label>

                {settlementCustomerSearch.trim() && (
                  <div className="admin-fdx-search-dropdown">
                    {filteredFrontDeskQueue.length ? (
                      filteredFrontDeskQueue.map((booking) => (
                        <button
                          type="button"
                          key={booking.id}
                          className="admin-fdx-search-result"
                          onClick={() => selectSearchResult(booking)}
                        >
                          <span className="admin-fdx-result-icon">
                            <UserRound size={16} />
                          </span>
                          <span className="admin-fdx-result-main">
                            <strong>{booking.guestName}</strong>
                            <small>{booking.bookingCode}</small>
                          </span>
                          <span className="admin-fdx-result-villa">
                            {booking.villaName}
                          </span>
                          <span className="admin-fdx-result-action">
                            Select
                            <ChevronRight size={14} />
                          </span>
                        </button>
                      ))
                    ) : (
                      <div className="admin-fdx-no-search-result">
                        <Search size={16} />
                        <span>
                          No eligible booking matches this code or guest name.
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {settlementError && (
                <div className="admin-fdx-error" role="alert">
                  <AlertCircle size={16} />
                  <span>{settlementError}</span>
                </div>
              )}

              {selected ? (
                <div className="admin-fd-v2-summary-grid">
                  <article className="admin-fd-v2-booking-card">
                    <div className="admin-fd-v2-villa">
                      <img
                        src={villaImage}
                        alt={selected.villaName || "Villa"}
                        onError={(event) => {
                          event.currentTarget.onerror = null;
                          event.currentTarget.src = "/image1.jpg";
                        }}
                      />
                      <div className="admin-fd-v2-villa-shade" />
                      <div className="admin-fd-v2-villa-copy">
                        <span>Reserved Villa</span>
                        <h3>{selected.villaName}</h3>
                        <p>{villaNumber}</p>
                      </div>
                      <StatusPill status={selected.bookingStatus} />
                    </div>

                    <div className="admin-fd-v2-booking-body">
                      <div className="admin-fd-v2-guest">
                        <span className="admin-fd-v2-avatar">
                          <UserRound size={20} />
                        </span>
                        <div>
                          <small>Primary Guest</small>
                          <strong>{selected.guestName}</strong>
                          <span>{selected.bookingCode}</span>
                        </div>
                        <span
                          className={`admin-fd-v2-stay ${slug(stayStatus)}`}
                        >
                          {stayStatus}
                        </span>
                      </div>

                      <div className="admin-fd-v2-details">
                        <div>
                          <span>Villa / Number</span>
                          <strong>{villaNumber}</strong>
                        </div>
                        <div>
                          <span>Guests</span>
                          <strong>
                            {selected.guestCount
                              ? `${selected.guestCount} guest${
                                  selected.guestCount === 1 ? "" : "s"
                                }`
                              : "Not specified"}
                          </strong>
                        </div>
                        <div>
                          <span>Check In</span>
                          <strong>{formatDate(selected.checkIn)}</strong>
                          <small>{selected.checkInTime || "3:00 PM"}</small>
                        </div>
                        <div>
                          <span>Check Out</span>
                          <strong>{formatDate(selected.checkOut)}</strong>
                          <small>{selected.checkOutTime || "11:00 AM"}</small>
                        </div>
                        <div>
                          <span>Contact</span>
                          <strong>{selected.phone || "No contact number"}</strong>
                        </div>
                        <div>
                          <span>Email</span>
                          <strong>{selected.email || "No email address"}</strong>
                        </div>
                      </div>
                    </div>
                  </article>

                  <aside className="admin-fd-v2-side">
                    <section className="admin-fd-v2-finance">
                      <header>
                        <ReceiptText size={18} />
                        <div>
                          <strong>Balance Summary</strong>
                          <small>Verified booking payment</small>
                        </div>
                      </header>

                      <div className="admin-fd-v2-finance-lines">
                        <div>
                          <span>Booking Total</span>
                          <strong>{formatPeso(selected.totalAmount)}</strong>
                        </div>
                        <div>
                          <span>Already Paid</span>
                          <strong>{formatPeso(selected.amountPaid)}</strong>
                        </div>
                        <div>
                          <span>Payment Status</span>
                          <strong>{selected.paymentStatus}</strong>
                        </div>
                      </div>

                      <div className="admin-fd-v2-remaining">
                        <span>Remaining Balance</span>
                        <strong>{formatPeso(selected.balanceAmount)}</strong>
                      </div>
                    </section>

                    <section className="admin-fd-v2-timing-card">
                      <div className="admin-fd-v2-timing-heading">
                        <div>
                          <span>Guest Decision</span>
                          <h3>When will the balance be paid?</h3>
                          <p>
                            Ask the guest before continuing. This choice is
                            saved with the booking.
                          </p>
                        </div>
                      </div>

                      <div
                        className="admin-fd-v2-timing-options"
                        role="radiogroup"
                        aria-label="Guest balance payment timing"
                      >
                        <button
                          type="button"
                          role="radio"
                          aria-checked={selectedTiming === "check_in"}
                          className={
                            selectedTiming === "check_in" ? "active" : ""
                          }
                          onClick={() => choosePaymentTiming("check_in")}
                          disabled={frontDeskFlowSubmitting || isCheckedOut}
                        >
                          <span>
                            <CalendarDays size={20} />
                          </span>
                          <div>
                            <strong>Pay at Check-in</strong>
                            <small>
                              Collect the remaining balance now, then mark the
                              guest as checked in.
                            </small>
                          </div>
                          <i>
                            {selectedTiming === "check_in" && (
                              <Check size={13} />
                            )}
                          </i>
                        </button>

                        <button
                          type="button"
                          role="radio"
                          aria-checked={selectedTiming === "check_out"}
                          className={
                            selectedTiming === "check_out" ? "active" : ""
                          }
                          onClick={() => choosePaymentTiming("check_out")}
                          disabled={frontDeskFlowSubmitting || isCheckedOut}
                        >
                          <span>
                            <LogOut size={20} />
                          </span>
                          <div>
                            <strong>Pay at Check-out</strong>
                            <small>
                              Check the guest in first. Collect the remaining
                              balance when the guest returns to check out.
                            </small>
                          </div>
                          <i>
                            {selectedTiming === "check_out" && (
                              <Check size={13} />
                            )}
                          </i>
                        </button>
                      </div>

                      {selectedTiming === "check_out" && (
                        <div
                          className={
                            isCheckedIn
                              ? "admin-fd-v2-flow-note ready"
                              : "admin-fd-v2-flow-note"
                          }
                        >
                          {isCheckedIn ? (
                            <CheckCircle2 size={17} />
                          ) : (
                            <UserCheck size={17} />
                          )}
                          <div>
                            <strong>
                              {isCheckedIn
                                ? "Guest is checked in"
                                : "Check-in comes first"}
                            </strong>
                            <span>
                              {isCheckedIn
                                ? `The balance is ready to be collected during checkout on ${formatDate(
                                    selected.checkOut
                                  )}.`
                                : "No balance will be collected now. The guest will be checked in and the payment remains due for checkout."}
                            </span>
                          </div>
                        </div>
                      )}

                      {selectedTiming === "check_in" && (
                        <div className="admin-fd-v2-flow-note ready">
                          <WalletCards size={17} />
                          <div>
                            <strong>Payment first, then check-in</strong>
                            <span>
                              After the balance is successfully paid, the system
                              will complete the guest check-in.
                            </span>
                          </div>
                        </div>
                      )}

                      {flowDateRestriction && (
                        <div className="admin-fd-v2-flow-note blocked">
                          <AlertCircle size={17} />
                          <div>
                            <strong>Transaction date restricted</strong>
                            <span>{flowDateRestriction}</span>
                          </div>
                        </div>
                      )}

                      <button
                        type="button"
                        className="admin-fd-v2-primary-action"
                        onClick={handleSummaryAction}
                        disabled={
                          !selectedTiming ||
                          frontDeskFlowSubmitting ||
                          isCheckedOut
                        }
                      >
                        {frontDeskFlowSubmitting ? (
                          <LoaderCircle size={17} className="admin-spin" />
                        ) : selectedTiming === "check_out" && !isCheckedIn ? (
                          <UserCheck size={17} />
                        ) : (
                          <ChevronRight size={17} />
                        )}
                        {summaryActionLabel}
                      </button>
                    </section>
                  </aside>
                </div>
              ) : (
                <div className="admin-fdx-empty-state">
                  <div className="admin-fdx-empty-icon">
                    <Search size={27} />
                  </div>
                  <h3>Find a booking to begin</h3>
                  <p>
                    Search using the full booking code, only the last part of
                    the code, or the guest name.
                  </p>
                  <div className="admin-fdx-search-examples">
                    <span>TV-2026-E6527B</span>
                    <span>E6527B</span>
                    <span>Guest Name</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div
              className="admin-fdx-payment-screen admin-fd-v2-payment-screen"
              id="frontdesk-payment-checkout"
            >
              <header className="admin-fdx-payment-header">
                <button
                  type="button"
                  className="admin-fdx-back"
                  onClick={returnToSummary}
                >
                  <ChevronLeft size={16} />
                  Booking Summary
                </button>

                <div className="admin-fdx-payment-context">
                  <span className="admin-fdx-payment-context-icon">
                    <UserRound size={16} />
                  </span>
                  <div>
                    <strong>{selected?.guestName}</strong>
                    <small>
                      {selected?.bookingCode} · {selected?.villaName}
                    </small>
                  </div>
                </div>

                <span className="admin-fd-v2-stage-pill">
                  {paymentTimingLabel}
                </span>
              </header>

              {settlementError && (
                <div className="admin-fdx-error" role="alert">
                  <AlertCircle size={16} />
                  <span>{settlementError}</span>
                </div>
              )}

              <form
                onSubmit={completeSettlement}
                className="admin-fdx-checkout-layout"
              >
                <main className="admin-fdx-payment-controls">
                  <section className="admin-fdx-card">
                    <header className="admin-fdx-card-header">
                      <span className="admin-fdx-card-icon">
                        <WalletCards size={18} />
                      </span>
                      <div>
                        <strong>Payment Option</strong>
                        <small>Select Cash or QRPh</small>
                      </div>
                    </header>

                    <div className="admin-fdx-method-grid">
                      {FRONT_DESK_PAYMENT_METHODS.map(
                        ({ id, label, description, icon: Icon }) => (
                          <button
                            type="button"
                            key={id}
                            className={
                              settlementMethod === id
                                ? "admin-fdx-method active"
                                : "admin-fdx-method"
                            }
                            onClick={() => {
                              setSettlementMethod(id);
                              setSettlementForm((current) => ({
                                ...current,
                                cashTendered:
                                  id === "Cash"
                                    ? current.cashTendered
                                    : "",
                              }));
                              setSettlementError("");
                              resetQrPhPayment();
                            }}
                          >
                            <span className="admin-fdx-method-icon">
                              <Icon size={22} />
                            </span>
                            <span className="admin-fdx-method-copy">
                              <strong>{label}</strong>
                              <small>{description}</small>
                            </span>
                            <span className="admin-fdx-method-check">
                              {settlementMethod === id && (
                                <Check size={13} />
                              )}
                            </span>
                          </button>
                        )
                      )}
                    </div>

                    <div className="admin-fdx-payer">
                      <label htmlFor="frontdesk-payer-name">
                        Payer Name
                      </label>
                      <input
                        id="frontdesk-payer-name"
                        type="text"
                        autoComplete="name"
                        placeholder="Name of person making the payment"
                        value={settlementForm.payerName}
                        onChange={(event) =>
                          setSettlementForm((current) => ({
                            ...current,
                            payerName: event.target.value,
                          }))
                        }
                      />
                    </div>

                    {settlementMethod === "Cash" && (
                      <div className="admin-fdx-cash">
                        <div className="admin-fdx-cash-input-group">
                          <label htmlFor="frontdesk-cash-received">
                            Cash Received
                          </label>
                          <div className="admin-fdx-money-input">
                            <span>₱</span>
                            <input
                              id="frontdesk-cash-received"
                              type="number"
                              min="0"
                              step="0.01"
                              inputMode="decimal"
                              placeholder="0.00"
                              value={settlementForm.cashTendered}
                              onChange={(event) =>
                                setSettlementForm((current) => ({
                                  ...current,
                                  cashTendered: event.target.value,
                                }))
                              }
                            />
                          </div>
                        </div>

                        <div
                          className={`admin-fdx-cash-change ${
                            cashShortage > 0
                              ? "short"
                              : hasCashTendered
                              ? "change"
                              : ""
                          }`}
                        >
                          <span>
                            {cashShortage > 0 ? "Cash Short" : "Change"}
                          </span>
                          <strong>
                            {cashShortage > 0
                              ? formatPeso(cashShortage)
                              : formatPeso(settlementChange)}
                          </strong>
                        </div>
                      </div>
                    )}

                    {settlementMethod === "QRPh" && (
                      <div className="admin-fdx-qrph">
                        {!qrphPayment.qrImage ? (
                          <div className="admin-fdx-qrph-ready">
                            <span className="admin-fdx-qrph-icon">
                              <QrCode size={28} />
                            </span>
                            <div>
                              <strong>Generate QRPh payment</strong>
                              <p>
                                A single-use PayMongo QRPh code will be
                                generated for the exact total due.
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={startQrPhSettlement}
                              disabled={
                                !selected ||
                                settlementSubmitting ||
                                settlementChargesLocked
                              }
                            >
                              {settlementSubmitting ? (
                                <LoaderCircle
                                  size={16}
                                  className="admin-spin"
                                />
                              ) : (
                                <QrCode size={16} />
                              )}
                              Generate QRPh
                            </button>
                          </div>
                        ) : (
                          <div className="admin-fdx-qrph-generated">
                            <img
                              src={qrphPayment.qrImage}
                              alt="PayMongo QRPh code"
                            />
                            <div>
                              <span
                                className={`admin-fdx-qr-status ${slug(
                                  qrphPayment.status
                                )}`}
                              >
                                {String(qrphPayment.status || "")
                                  .replace(/_/g, " ")}
                              </span>
                              <strong>
                                Scan to pay{" "}
                                {formatPeso(settlementAmountValue)}
                              </strong>
                              <small>
                                {qrphPayment.expiresAt
                                  ? `Expires ${formatDateTime(
                                      qrphPayment.expiresAt
                                    )}`
                                  : "Waiting for PayMongo confirmation"}
                              </small>
                              <button
                                type="button"
                                onClick={() =>
                                  checkQrPhSettlementStatus(
                                    qrphPayment.paymentIntentId,
                                    false
                                  )
                                }
                                disabled={
                                  !qrphPayment.paymentIntentId ||
                                  settlementSubmitting
                                }
                              >
                                <RefreshCw size={14} />
                                Check Status
                              </button>
                            </div>
                          </div>
                        )}

                        {qrphPayment.error && (
                          <div className="admin-fdx-inline-error">
                            <AlertCircle size={14} />
                            <span>{qrphPayment.error}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </section>

                  <section className="admin-fdx-card">
                    <header className="admin-fdx-card-header">
                      <span className="admin-fdx-card-icon">
                        <ReceiptText size={18} />
                      </span>
                      <div>
                        <strong>Other Charges</strong>
                        <small>
                          Add confirmed additional charges to this payment.
                        </small>
                      </div>
                    </header>

                    <div className="admin-fdx-charge-entry">
                      <input
                        type="text"
                        placeholder="Charge description"
                        value={chargeDraft.description}
                        disabled={settlementChargesLocked}
                        onChange={(event) =>
                          setChargeDraft((current) => ({
                            ...current,
                            description: event.target.value,
                          }))
                        }
                      />

                      <div className="admin-fdx-charge-money">
                        <span>₱</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          inputMode="decimal"
                          placeholder="0.00"
                          value={chargeDraft.amount}
                          disabled={settlementChargesLocked}
                          onChange={(event) =>
                            setChargeDraft((current) => ({
                              ...current,
                              amount: event.target.value,
                            }))
                          }
                        />
                      </div>

                      <button
                        type="button"
                        onClick={addSettlementCharge}
                        disabled={settlementChargesLocked}
                      >
                        <Plus size={15} />
                        Add Charge
                      </button>
                    </div>

                    {settlementCharges.length ? (
                      <div className="admin-fdx-charge-list">
                        {settlementCharges.map((charge) => (
                          <div key={charge.id}>
                            <span>{charge.description}</span>
                            <strong>{formatPeso(charge.amount)}</strong>
                            <button
                              type="button"
                              aria-label={`Remove ${charge.description}`}
                              onClick={() =>
                                removeSettlementCharge(charge.id)
                              }
                              disabled={settlementChargesLocked}
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="admin-fdx-no-charges">
                        No other charges added.
                      </div>
                    )}
                  </section>
                </main>

                <aside className="admin-fdx-checkout-card">
                  <div className="admin-fdx-mini-booking">
                    <img
                      src={villaImage}
                      alt={selected?.villaName || "Villa"}
                      onError={(event) => {
                        event.currentTarget.onerror = null;
                        event.currentTarget.src = "/image1.jpg";
                      }}
                    />
                    <div>
                      <span>{selected?.villaName}</span>
                      <strong>{selected?.guestName}</strong>
                      <small>{selected?.bookingCode}</small>
                      <span
                        className={`admin-fdx-mini-stay ${slug(stayStatus)}`}
                      >
                        {stayStatus}
                      </span>
                    </div>
                  </div>

                  <div className="admin-fdx-checkout-breakdown">
                    <div>
                      <span>Booking Total</span>
                      <strong>
                        {formatPeso(selected?.totalAmount || 0)}
                      </strong>
                    </div>
                    <div>
                      <span>Already Paid</span>
                      <strong>
                        − {formatPeso(selected?.amountPaid || 0)}
                      </strong>
                    </div>
                    <div>
                      <span>Remaining Balance</span>
                      <strong>{formatPeso(roomBalanceValue)}</strong>
                    </div>
                    <div>
                      <span>Other Charges</span>
                      <strong>+ {formatPeso(otherChargesTotal)}</strong>
                    </div>
                    <div>
                      <span>Payment Stage</span>
                      <strong>{paymentTimingLabel}</strong>
                    </div>
                  </div>

                  <div className="admin-fdx-total-due">
                    <span>Total Need To Pay</span>
                    <strong>{formatPeso(settlementAmountValue)}</strong>
                    <small>{settlementMethod} payment</small>
                  </div>

                  <label className="admin-fdx-notes">
                    <span>Payment Notes</span>
                    <textarea
                      placeholder="Optional transaction notes..."
                      value={settlementForm.notes}
                      onChange={(event) =>
                        setSettlementForm((current) => ({
                          ...current,
                          notes: event.target.value,
                        }))
                      }
                    />
                  </label>

                  {settlementMethod === "Cash" ? (
                    <button
                      type="submit"
                      className="admin-fdx-complete"
                      disabled={
                        !selected ||
                        settlementSubmitting ||
                        !cashIsSufficient ||
                        !selectedTiming
                      }
                    >
                      {settlementSubmitting ? (
                        <LoaderCircle
                          size={17}
                          className="admin-spin"
                        />
                      ) : (
                        <Banknote size={17} />
                      )}
                      {selectedTiming === "check_out"
                        ? "Pay & Complete Checkout"
                        : "Pay & Complete Check-in"}
                    </button>
                  ) : (
                    <div className="admin-fdx-qr-message">
                      <QrCode size={16} />
                      <span>
                        Generate the QRPh code on the left. After PayMongo
                        confirms payment, the{" "}
                        {selectedTiming === "check_out"
                          ? "checkout"
                          : "check-in"}{" "}
                        status will be completed automatically.
                      </span>
                    </div>
                  )}
                </aside>
              </form>
            </div>
          )}
        </section>
      </div>
    );
  }

  function renderNotifications() {
    return (
      <div className="admin-page admin-notifications-page">
        <section className="admin-panel">
          <header className="admin-panel-header">
            <h3>
              <Bell size={17} /> All Notifications
            </h3>
            {unreadNotificationCount > 0 && (
              <button onClick={markAllNotificationsRead}>Mark all read</button>
            )}
          </header>
          <div className="admin-notification-list">
            {notifications.map((notification) => (
              <button
                key={notification.id}
                className={notification.unread ? "unread" : ""}
                onClick={() => handleNotificationClick(notification)}
              >
                <span className="admin-notification-icon">
                  <Bell size={17} />
                </span>
                <span>
                  <strong>{notification.title}</strong>
                  <p>{notification.message}</p>
                  <time>{formatRelative(notification.timestamp)}</time>
                </span>
                {notification.unread && <i />}
              </button>
            ))}
            {!notifications.length && (
              <EmptyState
                icon={Bell}
                title="No notifications"
                message="New booking assignments and approval alerts will appear here."
              />
            )}
          </div>
        </section>
      </div>
    );
  }

  function openProfileEditor() {
    setProfileEditForm({
      name: String(profile.name || ""),
      email: String(profile.email || ""),
      nickname: String(profile.nickname || ""),
      phone: String(profile.phone || ""),
      avatarUrl: profile.avatar_url || profile.avatarUrl || profile.photo_url || profile.photoUrl || "",
    });
    setProfileEditError("");
    setProfileEditOpen(true);
  }

  async function chooseProfilePicture(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setProfileEditError("Choose a JPG, PNG, or WebP image smaller than 5 MB.");
      return;
    }
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 256;
      const size = Math.min(image.width, image.height);
      canvas.getContext("2d").drawImage(image, (image.width - size) / 2, (image.height - size) / 2, size, size, 0, 0, 256, 256);
      const avatarUrl = canvas.toDataURL("image/jpeg", 0.85);
      setProfileEditForm((current) => ({ ...current, avatarUrl }));
      setProfileEditError("");
    } catch {
      setProfileEditError("This image could not be opened. Please choose another picture.");
    } finally { URL.revokeObjectURL(url); }
  }

  async function saveAdminProfile(event) {
    event.preventDefault();
    const name = profileEditForm.name.trim();
    const email = profileEditForm.email.trim();
    const nickname = profileEditForm.nickname.trim();
    const phone = profileEditForm.phone.trim();
    if (name.length < 3 || !email.includes("@")) {
      setProfileEditError("Enter a full name and valid email address.");
      return;
    }
    if (!profile.id || profile.id === DEFAULT_ADMIN.id) {
      setProfileEditError("The administrator account must be loaded before saving changes.");
      return;
    }
    setProfileEditSaving(true);
    setProfileEditError("");
    try {
      const result = await apiRequest(`/admin/staff/${encodeURIComponent(profile.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ fullName: name, email, nickname, phone, avatarUrl: profileEditForm.avatarUrl || "" }),
      });
      const saved = await apiRequest("/admin/profile");
      const updated = saved?.data || result?.data || {};
      if ((updated.nickname || "") !== nickname || (updated.avatarUrl || "") !== (profileEditForm.avatarUrl || "")) {
        throw new Error("Your profile changes could not be confirmed. Please save again.");
      }
      setProfile((current) => ({ ...current, ...updated }));
      setProfileEditOpen(false);
      showToast("Your administrator profile has been updated.", "success");
      loadAdminData({ silent: true });
    } catch (error) {
      setProfileEditError(error instanceof Error ? error.message : "Unable to save your profile.");
    } finally {
      setProfileEditSaving(false);
    }
  }

  function renderProfile() {
    const isActive = profile.accountStatus !== "Disabled" && profile.isActive !== false;
    const adminName = profile.fullName || profile.name || "Villa Administrator";
    return (
      <div className="admin-page admin-profile-page">
        <div className="modern-admin-profile">
          <section className="modern-profile-hero">
            <div className="modern-profile-cover">
              <span className="modern-profile-cover-label"><ShieldCheck size={14} /> Administrator account</span>
              <span className="modern-profile-cover-orbit" />
              <span className="modern-profile-cover-orbit orbit-two" />
            </div>
            <div className="modern-profile-identity">
              <div className="modern-profile-avatar"><Avatar name={adminName} online={isActive} size={76} src={profile.avatar_url || profile.avatarUrl || profile.photo_url || profile.photoUrl} /></div>
              <div className="modern-profile-intro">
                <div className="modern-profile-name-row">
                  <h2>{adminName}</h2>
                  <span className={`modern-profile-status${isActive ? " is-active" : ""}`}><span />{isActive ? "Active" : "Disabled"}</span>
                </div>
                <p>Administrator <span>·</span> Villa Operations</p>
                <div className="modern-profile-tags"><span><Mail size={14} />{profile.email || "Email not provided"}</span></div>
              </div>
              <button type="button" className="admin-btn-primary modern-profile-edit" onClick={openProfileEditor}>
                <Pencil size={15} /> Edit profile
              </button>
            </div>
          </section>
          <section className="modern-profile-details admin-panel">
            <div className="modern-profile-section-heading"><span className="modern-profile-section-icon"><UserRound size={18} /></span><div><h3>Profile details</h3><p>Update the contact information used for your administrator account.</p></div></div>
            <dl className="modern-profile-fields">
              <div><dt>Full name</dt><dd>{adminName}</dd></div>
              <div><dt>Email address</dt><dd>{profile.email || "Not provided"}</dd></div>
              <div><dt>Username</dt><dd>{profile.username || "Not provided"}</dd></div>
              <div><dt>Phone number</dt><dd>{profile.phone || "Not provided"}</dd></div>
            </dl>
          </section>
        </div>
      </div>
    );
  }

  async function openVillaEditor(
    villa
  ) {
    clearVillaImagePreviews();
    setVillaImageFiles([]);
    setVillaImagePreview(null);
    setVillaEditorLoading(true);
    setVillaEditorOpen(false);
    setVillaEditorError("");

    try {
      const adminPayload = await apiRequest("/villa-catalog/admin", { cache: "no-store" });
      const rows = Array.isArray(adminPayload?.data)
        ? adminPayload.data.map(normalizeVillaCatalogRow)
        : [];
      const currentVilla = rows.find((row) => row.id === villa.id);

      if (!currentVilla) {
        throw new Error("The saved Villa could not be found in the catalog.");
      }

      setVillaCatalog(rows);
      setVillaEditorForm(createVillaEditForm(currentVilla));
      setVillaEditorImageIndex(0);
      setVillaEditorOpen(true);
    } catch (error) {
      setVillaEditorForm(createVillaEditForm(villa));
      setVillaEditorError(
        error instanceof Error
          ? `Could not refresh saved photos. ${error.message}`
          : "Could not refresh saved photos. Showing the last loaded Villa data."
      );
      setVillaEditorOpen(true);
    } finally {
      setVillaEditorLoading(false);
    }
  }

  function clearVillaImagePreviews() {
    villaImagePreviewUrls.current.forEach((previewUrl) => URL.revokeObjectURL(previewUrl));
    villaImagePreviewUrls.current.clear();
  }

  function removeVillaImageFile(index) {
    const selected = villaImageFiles[index];
    if (selected) {
      URL.revokeObjectURL(selected.preview);
      villaImagePreviewUrls.current.delete(selected.preview);
      setVillaImageFiles((current) => current.filter((_, imageIndex) => imageIndex !== index));
    }
  }

  function closeVillaEditor() {
    if (villaEditorSaving) return;
    clearVillaImagePreviews();
    setVillaImageFiles([]);
    setVillaImagePreview(null);
    setVillaEditorOpen(false);
  }

  function appendVillaImageFiles(files) {
    if (!files.length) return;

    const imageCount = villaEditorForm.imageUrls.length + villaImageFiles.length;
    if (imageCount + files.length > 30) {
      setVillaEditorError("A Villa can have up to 30 photos.");
      return;
    }

    const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
    const invalidFile = files.find(
      (file) => !allowedTypes.has(file.type) || file.size > 8 * 1024 * 1024
    );
    if (invalidFile) {
      setVillaEditorError("Choose JPG, PNG, or WebP images smaller than 8 MB each.");
      return;
    }

    const previews = files.map((file) => {
      const preview = URL.createObjectURL(file);
      villaImagePreviewUrls.current.add(preview);
      return { file, preview };
    });
    setVillaEditorImageIndex(imageCount + previews.length - 1);
    setVillaImageFiles((current) => [...current, ...previews]);
    setVillaEditorError("");
  }

  function addVillaImageFiles(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    appendVillaImageFiles(files);
  }

  function handleVillaImageDrop(event) {
    event.preventDefault();
    setVillaImageDragging(false);
    appendVillaImageFiles(Array.from(event.dataTransfer.files || []));
  }

  async function saveVillaCatalogItem(
    event
  ) {
    event.preventDefault();

    if (
      !villaEditorForm.id
    ) {
      setVillaEditorError(
        "The Villa ID is missing."
      );
      return;
    }

    const price =
      Number(
        villaEditorForm.price
      );

    const capacity =
      Number(
        villaEditorForm.capacity
      );

    if (
      !Number.isFinite(price) ||
      price < 0
    ) {
      setVillaEditorError(
        "Enter a valid Villa price."
      );
      return;
    }

    if (
      !Number.isInteger(
        capacity
      ) ||
      capacity < 1 ||
      capacity > 8
    ) {
      setVillaEditorError(
        "Capacity must be a whole number from 1 to 8."
      );
      return;
    }

    setVillaEditorSaving(
      true
    );
    setVillaEditorError(
      ""
    );

    let uploadedImageUrls = [];
    let catalogSaved = false;
    try {
      if (villaImageFiles.length) {
        const formData = new FormData();
        villaImageFiles.forEach(({ file }) => formData.append("files", file));
        const uploadPayload = await apiRequest(
          `/villa-catalog/${encodeURIComponent(villaEditorForm.id)}/images`,
          { method: "POST", body: formData }
        );
        uploadedImageUrls = uploadPayload?.data?.image_urls;
        if (!Array.isArray(uploadedImageUrls) || uploadedImageUrls.length !== villaImageFiles.length) {
          throw new Error("The image upload response was incomplete. Try again.");
        }
      }

      const imageUrls = [...villaEditorForm.imageUrls, ...uploadedImageUrls];
      const payload =
        await apiRequest(
          `/villa-catalog/${encodeURIComponent(
            villaEditorForm.id
          )}`,
          {
            method: "PUT",
            body:
              JSON.stringify({
                title:
                  villaEditorForm.title,
                landing_title:
                  villaEditorForm.landingTitle,
                price,
                capacity,
                guest_label:
                  villaEditorForm.guestLabel,
                beds:
                  villaEditorForm.beds,
                duration:
                  villaEditorForm.duration,
                stay_hours:
                  villaEditorForm.stayHours,
                image_url:
                  imageUrls[0] || "",
                image_urls: imageUrls,
                details:
                  villaEditorForm.details,
                amenities:
                  parseVillaAmenitiesText(
                    villaEditorForm.amenitiesText
                  ),
              }),
          }
        );

      const saved =
        normalizeVillaCatalogRow({
          ...payload?.data,
          image_url: imageUrls[0] || "",
          image_urls: imageUrls,
        });
      catalogSaved = true;

      setVillaCatalog(
        (current) =>
          current.map((villa) =>
            villa.id === saved.id ? saved : villa
          )
      );
      try {
        localStorage.setItem("theVillaCatalogUpdatedAt", String(Date.now()));
      } catch {
        // The landing page still refreshes its public catalog periodically.
      }
      setVillaEditorForm((current) => ({
        ...current,
        imageUrl: saved.imageUrl,
        imageUrls: saved.imageUrls,
      }));
      clearVillaImagePreviews();
      setVillaImageFiles([]);

      const previousImageUrls =
        villaCatalog.find((villa) => villa.id === saved.id)?.imageUrls || [];
      const removedImageUrls = previousImageUrls.filter(
        (imageUrl) => !saved.imageUrls.includes(imageUrl)
      );
      if (removedImageUrls.length) {
        try {
          await apiRequest(
            `/villa-catalog/${encodeURIComponent(saved.id)}/images`,
            {
              method: "DELETE",
              body: JSON.stringify({ image_urls: removedImageUrls }),
            }
          );
        } catch (error) {
          setVillaEditorError(
            `${saved.title} was saved, but some removed image files could not be deleted. ${error instanceof Error ? error.message : ""}`.trim()
          );
          return;
        }
      }

      setVillaImagePreview(null);
      setVillaEditorOpen(false);

      showToast(
        `${saved.title} was updated. The landing page and guest Villa details will refresh automatically.`
      );
    } catch (error) {
      let cleanupMessage = "";
      if (!catalogSaved && uploadedImageUrls.length) {
        try {
          await apiRequest(
            `/villa-catalog/${encodeURIComponent(villaEditorForm.id)}/images`,
            {
              method: "DELETE",
              body: JSON.stringify({ image_urls: uploadedImageUrls }),
            }
          );
        } catch {
          cleanupMessage = " Some uploaded files may need cleanup.";
        }
      }
      setVillaEditorError(
        `${error instanceof Error ? error.message : "The Villa could not be updated."}${cleanupMessage}`
      );
    } finally {
      setVillaEditorSaving(
        false
      );
    }
  }

  async function refreshVillaOperations() {
    await Promise.all([loadVillaCatalog({ silent: true }), loadAdminData({ silent: true })]);
  }

  function showVillaOperations(villaId) {
    if (villaId) setVillaMaintenanceTarget(villaId);
  }

  function renderVillas() {
    const maintenanceVilla = villaCatalog.find(item => item.id === villaMaintenanceTarget);
    const affectedReservations = normalizedBookings.filter(booking => booking.villaName === villaEditorForm.title
      && booking.checkOut >= todayStr() && !['Cancelled', 'Expired', 'Completed'].includes(booking.bookingStatus || booking.status));
    const editorImages = [
      ...villaEditorForm.imageUrls.map((src, index) => ({
        src,
        name: villaImageDisplayName(src, index),
        saved: true,
        key: src,
      })),
      ...villaImageFiles.map((image, index) => ({
        src: image.preview,
        name: image.file.name,
        saved: false,
        key: `${image.file.name}-${image.file.lastModified}-${index}`,
      })),
    ];
    const activeEditorImage =
      editorImages[
        Math.min(villaEditorImageIndex, Math.max(0, editorImages.length - 1))
      ];

    return (
      <div className="admin-page admin-villa-catalog-page">
        <div className="admin-villa-catalog-toolbar">
          <span>{villaCatalog.length} {villaCatalog.length === 1 ? "villa" : "villas"} in catalog</span>
          <span className="admin-villa-maintenance-summary">
            {villaCatalog.filter((villa) => villa.status === "Under Maintenance").length} under maintenance
          </span>
          <button
            type="button"
            className="admin-btn-secondary"
            onClick={() =>
              loadVillaCatalog()
            }
            disabled={
              villaCatalogLoading
            }
          >
            <RefreshCw
              size={16}
              className={
                villaCatalogLoading
                  ? "admin-spin"
                  : ""
              }
            />
            Refresh
          </button>
        </div>

        {villaCatalogError && (
          <div className="admin-villa-catalog-error">
            <AlertCircle
              size={18}
            />
            <span>
              {villaCatalogError}
            </span>
          </div>
        )}

        {villaCatalogLoading &&
        !villaCatalog.length ? (
          <section className="admin-panel">
            <EmptyState
              icon={LoaderCircle}
              title="Loading Villa catalog"
              message="Reading the latest Villa prices and details from Supabase."
            />
          </section>
        ) : (
          <section className="admin-villa-catalog-grid">
            {villaCatalog.map(
              (villa) => (
                <article
                  className="admin-villa-catalog-card"
                  key={villa.id}
                >
                  <div className="admin-villa-catalog-image">
                    <img
                      src={villa.imageUrls[0] || villa.imageUrl || "/image1.jpg"}
                      alt={
                        villa.title
                      }
                    />

                    <span
                      className={`admin-villa-live-status ${
                        villa.status === "Under Maintenance"
                          ? "status-under-maintenance"
                          : "status-calendar-managed"
                      }`}
                    >
                      {villa.status === "Under Maintenance"
                        ? "Under Maintenance"
                        : "Calendar managed"}
                    </span>
                    <span className="admin-villa-image-count-badge">
                      <ImagePlus size={13} />
                      {villa.imageUrls.length} {villa.imageUrls.length === 1 ? "photo" : "photos"}
                    </span>
                  </div>

                  <div className="admin-villa-catalog-body">
                    <div className="admin-villa-catalog-title">
                      <div>
                        <span>
                          {
                            villa.landingTitle
                          }
                        </span>
                        <h3>
                          {
                            villa.title
                          }
                        </h3>
                      </div>

                      <strong>
                        {formatPeso(
                          villa.price
                        )}
                      </strong>
                    </div>

                    <dl>
                      <div>
                        <dt>
                          Capacity
                        </dt>
                        <dd>
                          {
                            villa.capacity
                          }{" "}
                          guests
                        </dd>
                      </div>

                      <div>
                        <dt>
                          Amenities
                        </dt>
                        <dd>
                          {
                            villa.amenities.reduce(
                              (
                                total,
                                group
                              ) =>
                                total +
                                (
                                  Array.isArray(
                                    group?.items
                                  )
                                    ? group.items.length
                                    : 0
                                ),
                              0
                            )
                          }{" "}
                          items
                        </dd>
                      </div>
                    </dl>

                    <div className="admin-villa-card-actions">
                      <button type="button" className="admin-btn-primary" onClick={() => openVillaEditor(villa)} disabled={villaEditorLoading}>
                        {villaEditorLoading ? <LoaderCircle size={15} className="admin-spin" /> : <Pencil size={15} />}
                        {villaEditorLoading ? "Loading saved photos..." : "Edit villa & pricing"}
                      </button>
                      <button type="button" className="admin-btn-secondary" onClick={() => showVillaOperations(villa.id)}><Wrench size={15}/>{villa.operations?.hasHistory || villa.operations?.open ? 'View Villa' : 'Request Maintenance'}</button>
                    </div>
                  </div>
                </article>
              )
            )}
          </section>
        )}

        {villaEditorOpen && (
          <div
            className="admin-villa-editor-backdrop"
            role="presentation"
            onMouseDown={(
              event
            ) => {
              if (
                event.target ===
                event.currentTarget &&
                !villaEditorSaving
              ) {
                closeVillaEditor();
              }
            }}
          >
            <form
              className="admin-villa-editor-modal"
              onSubmit={
                saveVillaCatalogItem
              }
            >
              <section
                className={`admin-villa-editor-gallery ${villaImageDragging ? "is-dragging" : ""}`}
                aria-label={`${villaEditorForm.title} photo gallery`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setVillaImageDragging(true);
                }}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget)) {
                    setVillaImageDragging(false);
                  }
                }}
                onDrop={handleVillaImageDrop}
              >
                {activeEditorImage ? (
                  <>
                    <img
                      className="admin-villa-editor-gallery-image"
                      src={activeEditorImage.src}
                      alt={activeEditorImage.name}
                    />
                    <div className="admin-villa-editor-gallery-shade" />
                    <span className="admin-villa-editor-gallery-count">
                      {Math.min(villaEditorImageIndex + 1, editorImages.length)} / {editorImages.length}
                    </span>
                    <span className="admin-villa-editor-gallery-name">
                      {activeEditorImage.name}
                    </span>
                    <button
                      type="button"
                      className="admin-villa-editor-gallery-remove"
                      aria-label={`Delete ${activeEditorImage.name}`}
                      title="Delete this photo"
                      disabled={villaEditorSaving}
                      onClick={() => {
                        if (activeEditorImage.saved) {
                          setVillaEditorForm((current) => {
                            const imageUrls = current.imageUrls.filter(
                              (url) => url !== activeEditorImage.src
                            );
                            return {
                              ...current,
                              imageUrls,
                              imageUrl: imageUrls[0] || "",
                            };
                          });
                        } else {
                          const pendingIndex = villaImageFiles.findIndex(
                            (image) => image.preview === activeEditorImage.src
                          );
                          if (pendingIndex !== -1) removeVillaImageFile(pendingIndex);
                        }
                        setVillaEditorImageIndex((current) =>
                          Math.max(0, Math.min(current, editorImages.length - 2))
                        );
                      }}
                    >
                      <Trash2 size={17} />
                    </button>
                    {editorImages.length > 1 && (
                      <>
                        <button
                          type="button"
                          className="admin-villa-editor-gallery-arrow is-previous"
                          aria-label="Previous photo"
                          onClick={() =>
                            setVillaEditorImageIndex((current) =>
                              (current - 1 + editorImages.length) % editorImages.length
                            )
                          }
                        >
                          <ChevronLeft size={24} />
                        </button>
                        <button
                          type="button"
                          className="admin-villa-editor-gallery-arrow is-next"
                          aria-label="Next photo"
                          onClick={() =>
                            setVillaEditorImageIndex((current) =>
                              (current + 1) % editorImages.length
                            )
                          }
                        >
                          <ChevronRight size={24} />
                        </button>
                      </>
                    )}
                  </>
                ) : (
                  <div className="admin-villa-editor-gallery-empty">
                    <ImagePlus size={38} />
                    <strong>No photos added yet</strong>
                    <span>Add photos to preview the Villa gallery.</span>
                  </div>
                )}
                {editorImages.length < 30 && (
                  <label className="admin-villa-editor-gallery-add">
                    <input
                      id={`villa-images-${villaEditorForm.id}`}
                      className="sr-only"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      onChange={addVillaImageFiles}
                      disabled={villaEditorSaving}
                    />
                    <ImagePlus size={16} />
                    {editorImages.length ? "Add photos" : "Add photo"}
                  </label>
                )}
                {villaEditorForm.imageUrls.length + villaImageFiles.length > 0 && (
                  <span className="admin-villa-editor-gallery-total">
                    {villaEditorForm.imageUrls.length + villaImageFiles.length} / 30 photos
                  </span>
                )}
              </section>

              <div className="admin-villa-editor-panel">
                <header className="admin-villa-editor-header">
                  <div>
                    <span>Villa content editor</span>
                    <h2>{villaEditorForm.title}</h2>
                  </div>
                  <div className="admin-villa-editor-header-actions">
                    {(villaEditorForm.imageUrls.length > 0 || villaImageFiles.length > 0) && (
                      <button
                        type="button"
                        className="admin-btn-ghost"
                        onClick={() => {
                          setVillaEditorForm((current) => ({
                            ...current,
                            imageUrl: "",
                            imageUrls: [],
                          }));
                          clearVillaImagePreviews();
                          setVillaImageFiles([]);
                          setVillaEditorImageIndex(0);
                        }}
                        disabled={villaEditorSaving}
                      >
                        <Trash2 size={14} /> Remove all photos
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={closeVillaEditor}
                      disabled={villaEditorSaving}
                      aria-label="Close Villa editor"
                    >
                      <X size={19} />
                    </button>
                  </div>
                </header>

                <div className="admin-villa-editor-scroll">
                {villaEditorError && (
                  <div className="admin-villa-editor-error">
                    <AlertCircle
                      size={17}
                    />
                    {
                      villaEditorError
                    }
                  </div>
                )}

                <div className="admin-villa-editor-grid">
                  <label>
                    <span>
                      Guest-side title
                    </span>
                    <input
                      value={
                        villaEditorForm.title
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            title:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      required
                    />
                  </label>

                  <label>
                    <span>
                      Landing-page title
                    </span>
                    <input
                      value={
                        villaEditorForm.landingTitle
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            landingTitle:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      required
                    />
                  </label>

                  <label>
                    <span>
                      Price (PHP)
                    </span>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={
                        villaEditorForm.price
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            price:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      required
                    />
                  </label>

                  <label>
                    <span>
                      Guest capacity
                    </span>
                    <input
                      type="number"
                      min="1"
                      max="8"
                      step="1"
                      value={
                        villaEditorForm.capacity
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            capacity:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      required
                    />
                  </label>

                  <label>
                    <span>
                      Guest label
                    </span>
                    <input
                      value={
                        villaEditorForm.guestLabel
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            guestLabel:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      placeholder="Up to 8 guests"
                    />
                  </label>

                  <label>
                    <span>
                      Beds
                    </span>
                    <input
                      value={
                        villaEditorForm.beds
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            beds:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                    />
                  </label>

                  <label>
                    <span>
                      Stay hours
                    </span>
                    <input
                      value={
                        villaEditorForm.stayHours
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            stayHours:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                    />
                  </label>

                  <label className="admin-villa-editor-full">
                    <span>
                      Full Villa details
                    </span>
                    <textarea
                      rows="5"
                      value={
                        villaEditorForm.details
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            details:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      required
                    />
                  </label>

                  <label className="admin-villa-editor-full">
                    <span>
                      Amenities
                    </span>
                    <small>
                      Enter one amenity per line using:
                      Category | Amenity
                    </small>
                    <textarea
                      rows="11"
                      value={
                        villaEditorForm.amenitiesText
                      }
                      onChange={(
                        event
                      ) =>
                        setVillaEditorForm(
                          (
                            current
                          ) => ({
                            ...current,
                            amenitiesText:
                              event
                                .target
                                .value,
                          })
                        )
                      }
                      placeholder={"Kitchen | Microwave\nKitchen | Refrigerator\nPool | Heated pool"}
                      required
                    />
                  </label>
                </div>
                <section className="admin-villa-availability-control" aria-labelledby="villa-availability-title">
                  <div>
                    <span className="admin-villa-editor-section-label">Booking availability</span>
                    <h3 id="villa-availability-title">
                      {villaEditorForm.underMaintenance ? "Under maintenance" : "Available for booking"}
                    </h3>
                    <p>
                      {villaEditorForm.underMaintenance
                        ? "Guests cannot book this Villa while it is under maintenance."
                        : "Booking availability follows the reservation calendar."}
                      {villaEditorForm.operations?.blocking ? ` ${villaEditorForm.operations.blocking} open request(s) are keeping bookings paused. Verify the work before reopening.` : ' Availability updates automatically when maintenance is requested and verified.'}
                    </p>
                    {villaEditorForm.underMaintenance && affectedReservations.length > 0 && <p className="admin-villa-reservation-impact">{affectedReservations.length} existing reservation(s) need review while this villa is under maintenance. <button type="button" className="admin-btn-ghost" onClick={() => { closeVillaEditor(); navigate('bookings'); setGlobalSearch(villaEditorForm.title); }}>Review reservations</button></p>}
                  </div>
                </section>

              </div>

              <footer>
                <button
                  type="button"
                  className="admin-btn-ghost"
                  onClick={closeVillaEditor}
                  disabled={
                    villaEditorSaving
                  }
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="admin-btn-primary"
                  disabled={
                    villaEditorSaving
                  }
                >
                  {villaEditorSaving ? (
                    <>
                      <LoaderCircle
                        size={16}
                        className="admin-spin"
                      />
                      Saving changes...
                    </>
                  ) : (
                    <>
                      <Check
                        size={16}
                      />
                      Save and publish
                    </>
                  )}
                </button>
              </footer>
              </div>
            </form>
          </div>
        )}

        {villaImagePreview && (
          <div
            className="admin-villa-image-preview-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setVillaImagePreview(null);
              }
            }}
          >
            <section
              className="admin-villa-image-preview-modal"
              role="dialog"
              aria-modal="true"
              aria-label={`Image preview: ${villaImagePreview.name}`}
            >
              <header>
                <div>
                  <span>Photo preview</span>
                  <h2 title={villaImagePreview.name}>{villaImagePreview.name}</h2>
                </div>
                <button
                  type="button"
                  aria-label="Close photo preview"
                  onClick={() => setVillaImagePreview(null)}
                >
                  <X size={18} />
                </button>
              </header>
              <img src={villaImagePreview.src} alt={villaImagePreview.name} />
            </section>
          </div>
        )}

        {maintenanceVilla && (
          <VillaMaintenance
            key={maintenanceVilla.id}
            villa={maintenanceVilla}
            apiRequest={apiRequest}
            staffDirectory={staffDirectory}
            modal
            onBack={() => setVillaMaintenanceTarget(null)}
            onChanged={refreshVillaOperations}
          />
        )}

      </div>
    );
  }

  function renderContent() {
    switch (view) {
      case "maintenance": return renderVillas();
      case "guestFeedback": return <AdminGuestFeedback apiRequest={apiRequest} />;
      case "dashboard":
        return renderDashboard();
      case "bookings":
        return renderBookings();
      case "manualBooking":
        return <ManualBooking apiRequest={apiRequest} onViewBookings={() => { navigate("bookings"); window.location.reload(); }} />;
      case "history":
        return renderHistory();
      case "villas":
        return renderVillas();
      case "assignmentMonitor":
        return renderAssignmentMonitor();
      case "calendar":
        return renderAssignmentMonitor();
      case "staff":
        return renderStaff();
      case "notifications":
        return renderNotifications();
      case "profile":
        return renderProfile();
      default:
        return renderDashboard();
    }
  }

  const meta = VIEW_META[view] || VIEW_META.dashboard;
  const profileRole = profile.portalRole === "admin" ? "Admin" : profile.role || "Administrator";

  return (
    <div className="admin-dashboard-shell" data-live-status={liveStatus}>
      <aside className="admin-sidebar">
        <div className="admin-sidebar-inner">
          <div className="admin-sidebar-brand">
            <span className="admin-brand-logo">
              <img src="/favicon.png" alt="The Villa logo" />
            </span>
            <span className="admin-brand-name">The Villa - Admin</span>
          </div>

          <nav className="admin-sidebar-nav" aria-label="Admin navigation">
            <button
              type="button"
              className={`admin-sidebar-profile-card admin-nav-profile${view === "profile" ? " active" : ""}`}
              onClick={openProfileEditor}
              title="My profile"
            >
              <Avatar name={profile.fullName || profile.name} size={80} src={profile.avatar_url || profile.avatarUrl || profile.photo_url || profile.photoUrl} />
              <span className="admin-sidebar-profile-copy">
                <strong>{profile.fullName || profile.name}{profile.nickname?.trim() && <> <span className="admin-profile-nickname">({profile.nickname.trim()})</span></>}</strong>
                <small className="admin-profile-role-label">{profileRole}</small>
              </span>
            </button>
            {SIDEBAR_ITEMS.map((item) => {
              const Icon = item.icon;
              let badge = null;
              if (item.id === "assignmentMonitor" && assignmentStats.total)
                badge = assignmentStats.total;
              if (item.id === "checkInOut")
                badge = normalizedBookings.filter((booking) =>
                  hasAdminCheckedIn(booking) && Boolean(getBookingOperation(booking))
                ).length;

              return (
                <React.Fragment key={item.id}>
                  <button
                    className={`admin-sidebar-nav-btn${
                      (item.id === "checkInOut" ? operationsModalOpen : view === item.id) ? " active" : ""
                    }`}
                    onClick={() => {
                      if (item.id === "checkInOut") {
                        setOperationsMode("queue");
                        setOperationsQuery("");
                        setOperationsFilter("All");
                        setOperationsModalOpen(true);
                      } else {
                        navigate(item.id);
                      }
                    }}
                    title={item.label}
                  >
                    <Icon size={18} />
                    <span className="admin-nav-label">{item.label}</span>
                    {badge ? <b className="admin-nav-badge">{badge}</b> : null}
                  </button>
                </React.Fragment>
              );
            })}
          </nav>

          <div className="admin-sidebar-footer">
            <button
              type="button"
              className="admin-logout-btn"
              onClick={() => setSignOutConfirmOpen(true)}
              aria-label="Sign Out"
            >
              <LogOut size={16} />
              <span className="admin-nav-label">Sign Out</span>
            </button>
          </div>
        </div>
      </aside>

      <div className="admin-main-area">
        <main className="admin-page-content" aria-label={meta.title}>
          <div className="dashboard-page-heading"><span>Workspace</span><h1>{view === "bookings" ? "Booking Records" : meta.title}</h1></div>
          {renderContent()}
        </main>
      </div>

      {operationsModalOpen && renderOperationsModal()}

      {selectedBooking && (
        <div
          className="admin-modal-backdrop admin-booking-modal-backdrop"
          onClick={closeBookingDetails}
        >
          <section
            className="admin-booking-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-booking-modal-title"
          >
            <header className="admin-modal-header admin-booking-modal-header">
              <div>
                <span className="admin-eyebrow">Booking overview</span>
                <h2 id="admin-booking-modal-title">
                  {selectedBooking.bookingCode}
                </h2>
              </div>
              <button
                type="button"
                onClick={closeBookingDetails}
                aria-label="Close booking details"
              >
                <X size={18} />
              </button>
            </header>

            <div className="admin-booking-modal-body">
              <section className="admin-booking-modal-hero">
                <div className="admin-booking-modal-identity">
                  <Avatar name={selectedBooking.guestName} size={52} />
                  <div>
                    <div className="admin-booking-profile-meta">
                      <span className="admin-booking-modal-label">
                        Primary guest
                      </span>

                      {isNewBooking(selectedBooking) && (
                        <span
                          className="admin-new-booking-mark admin-booking-new-mark"
                          title="This booking was created within the last 3 days"
                        >
                          NEW
                        </span>
                      )}
                    </div>

                    <h3>{selectedBooking.guestName}</h3>
                    <p>{selectedBooking.villaName}</p>
                  </div>
                </div>

                <div className="admin-booking-modal-statuses">
                  <StatusPill status={selectedBooking.bookingStatus} />
                  <StatusPill status={selectedBooking.paymentStatus} />
                </div>
              </section>

              <section
                className="admin-booking-modal-summary"
                aria-label="Booking summary"
              >
                <article>
                  <span className="admin-booking-summary-icon">
                    <CalendarDays size={17} />
                  </span>
                  <div>
                    <small>Check-in</small>
                    <strong>{formatDate(selectedBooking.checkIn)}</strong>
                    <span>{selectedBooking.checkInTime}</span>
                  </div>
                </article>
                <article>
                  <span className="admin-booking-summary-icon">
                    <CalendarDays size={17} />
                  </span>
                  <div>
                    <small>Check-out</small>
                    <strong>{formatDate(selectedBooking.checkOut)}</strong>
                    <span>{selectedBooking.checkOutTime}</span>
                  </div>
                </article>
                <article>
                  <span className="admin-booking-summary-icon">
                    <Users size={17} />
                  </span>
                  <div>
                    <small>Guests</small>
                    <strong>
                      {selectedBooking.guestCount || "Not specified"}
                    </strong>
                    <span>Registered guests</span>
                  </div>
                </article>
                <article>
                  <span className="admin-booking-summary-icon">
                    <WalletCards size={17} />
                  </span>
                  <div>
                    <small>Booking total</small>
                    <strong>{formatPeso(selectedBooking.totalAmount)}</strong>
                    <span>{selectedBooking.paymentStatus}</span>
                  </div>
                </article>
              </section>

              <section className="admin-booking-modal-section">
                <div className="admin-booking-section-heading">
                  <div>
                    <span className="admin-booking-section-icon">
                      <ClipboardList size={17} />
                    </span>
                    <div>
                      <h3>Booking information</h3>
                      <p>Guest, stay, and payment information for this reservation.</p>
                    </div>
                  </div>
                </div>

                <dl className="admin-booking-detail-grid">
                  <div>
                    <dt>Booking code</dt>
                    <dd>{selectedBooking.bookingCode}</dd>
                  </div>
                  <div>
                    <dt>Villa</dt>
                    <dd>{selectedBooking.villaName}</dd>
                  </div>
                  <div>
                    <dt>Contact number</dt>
                    <dd>{selectedBooking.phone}</dd>
                  </div>
                  <div>
                    <dt>Email address</dt>
                    <dd>{selectedBooking.email}</dd>
                  </div>
                  <div>
                    <dt>Payment method</dt>
                    <dd>{selectedBooking.paymentMethod}</dd>
                  </div>
                  <div>
                    <dt>Payment reference</dt>
                    <dd>{selectedBooking.paymentReference || "Not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Amount paid</dt>
                    <dd>{formatPeso(selectedBooking.amountPaid)}</dd>
                  </div>
                  <div>
                    <dt>Remaining balance</dt>
                    <dd className={selectedBooking.balanceAmount > 0 ? "balance-due" : "balance-paid"}>
                      {formatPeso(selectedBooking.balanceAmount)}
                    </dd>
                  </div>
                </dl>
              </section>

              <section className="admin-booking-modal-section">
                <div className="admin-booking-section-heading">
                  <div>
                    <span className="admin-booking-section-icon">
                      <ClipboardCheck size={17} />
                    </span>
                    <div>
                      <h3>Special requests & notes</h3>
                      <p>Guest-facing or internal notes saved with the booking.</p>
                    </div>
                  </div>
                </div>
                <div className="admin-booking-notes">
                  <p>{selectedBooking.notes || "No special request."}</p>
                </div>
              </section>

              <section className="admin-booking-modal-section">
                <div className="admin-booking-section-heading">
                  <div>
                    <span className="admin-booking-section-icon">
                      <UserCheck size={17} />
                    </span>
                    <div>
                      <h3>Assigned staff</h3>
                      <p>
                        {selectedBookingAssignedStaff.length
                          ? `${selectedBookingAssignedStaff.length} staff member${
                              selectedBookingAssignedStaff.length === 1 ? "" : "s"
                            } assigned across ${selectedBookingAssignments.length} task${
                              selectedBookingAssignments.length === 1 ? "" : "s"
                            }.`
                          : "Housekeeping is assigned automatically after booking confirmation when a suitable shift is available."}
                      </p>
                    </div>
                  </div>
                  {selectedBookingAssignments.length > 0 && (
                    <span className="admin-booking-assignment-count">
                      {selectedBookingAssignments.filter(
                        (assignment) =>
                          displayAssignmentStatus(assignment) !== "Completed"
                      ).length} active
                    </span>
                  )}
                </div>

                {selectedBookingAssignedStaff.length ? (
                  <div className="admin-booking-staff-list">
                    {selectedBookingAssignedStaff.map((staff) => (
                      <article className="admin-booking-staff-card" key={staff.id}>
                        <div className="admin-booking-staff-profile">
                          <div className="admin-avatar-wrap">
                            <ProfilePhoto name={staff.name} src={staff.avatarUrl} size={54} />
                            <span
                              className={`admin-booking-online-dot${
                                staff.online ? " online" : ""
                              }`}
                              aria-label={staff.online ? "Online" : "Offline"}
                            />
                          </div>
                          <div className="admin-booking-staff-copy">
                            <strong>{staff.name}</strong>
                            <span>{staff.role}</span>
                            <small>
                              {staff.department} · {staff.shift}
                            </small>
                          </div>
                          <span className="admin-booking-task-count">
                            {staff.tasks.length} task{staff.tasks.length === 1 ? "" : "s"}
                          </span>
                        </div>

                        <div className="admin-booking-task-stack">
                          {staff.tasks.map((assignment) => (
                            <button
                              type="button"
                              className="admin-booking-task-row"
                              key={assignment.id}
                              onClick={() => {
                                closeBookingDetails();
                                openAssignment(assignment.id);
                              }}
                            >
                              <span className="admin-booking-task-icon">
                                <ClipboardCheck size={15} />
                              </span>
                              <span className="admin-booking-task-copy">
                                <strong>{assignment.title}</strong>
                                <small>
                                  {assignment.department || assignment.category || "Operations"}
                                  {assignment.dueDate
                                    ? ` · Due ${formatDate(assignment.dueDate)}`
                                    : ""}
                                </small>
                              </span>
                              <StatusPill
                                status={displayAssignmentStatus(assignment)}
                              />
                              <ChevronRight size={15} />
                            </button>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="admin-booking-empty-staff">
                    <span>
                      <UserPlus size={20} />
                    </span>
                    <div>
                      <strong>No preparation staff assigned yet</strong>
                      <p>
                        Successful, payment-verified bookings automatically select an available Housekeeping staff member at random. If this booking remains unassigned, check administrator alerts and staff shifts; the system retries automatically.
                      </p>
                    </div>
                  </div>
                )}
              </section>
            </div>

            <footer className="admin-modal-actions admin-booking-modal-actions">
              <button
                type="button"
                className="admin-btn-ghost"
                onClick={closeBookingDetails}
              >
                Close
              </button>
            </footer>
          </section>
        </div>
      )}

      {calendarModalOpen && selectedCalendarDate && (
        <div
          className="admin-modal-backdrop"
          onClick={() => setCalendarModalOpen(false)}
        >
          <section
            className="admin-calendar-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="admin-modal-header">
              <div>
                <span className="admin-eyebrow">Assignments due</span>
                <h2>{formatDate(selectedCalendarDate, true)}</h2>
              </div>
              <button onClick={() => setCalendarModalOpen(false)}>
                <X size={18} />
              </button>
            </header>
            <div className="admin-calendar-modal-body">
              {selectedCalendarAssignments.length ? (
                selectedCalendarAssignments.map((assignment) => (
                  <button
                    key={assignment.id}
                    onClick={() => {
                      setCalendarModalOpen(false);
                      openAssignment(assignment.id);
                    }}
                  >
                    <span className="admin-assignment-icon">
                      <ClipboardCheck size={17} />
                    </span>
                    <span>
                      <strong>{assignment.title}</strong>
                      <small>
                        {assignment.bookingCode} · {assignment.assignedTo}
                      </small>
                    </span>
                    <StatusPill status={displayAssignmentStatus(assignment)} />
                    <ChevronRight size={16} />
                  </button>
                ))
              ) : (
                <EmptyState
                  icon={CalendarDays}
                  title="No assignments due"
                  message="No incomplete booking assignment is scheduled for this date."
                />
              )}
            </div>
          </section>
        </div>
      )}

      {assignmentHistoryOpen && (
        <div className="admin-modal-backdrop modern-history-backdrop" onClick={() => setAssignmentHistoryOpen(false)}>
          <section className="modern-history-modal" role="dialog" aria-modal="true" aria-labelledby="assignment-history-modal-title" onClick={(event) => event.stopPropagation()}>
            <header className="modern-history-header">
              <div className="modern-history-heading">
                <span className="modern-history-icon"><History size={23} /></span>
                <div>
                  <span className="admin-eyebrow">Operations / Assignment Monitor</span>
                  <h2 id="assignment-history-modal-title">Assignment history</h2>
                  <p>Recorded task creation, status changes, and completed work</p>
                </div>
              </div>
              <button type="button" className="modern-history-close" onClick={() => setAssignmentHistoryOpen(false)} aria-label="Close assignment history"><X size={20} /></button>
            </header>
            <div className="modern-history-toolbar">
              <label className="modern-history-search"><Search size={17} /><input type="search" placeholder="Search assignments, guests, staff, or activity" value={assignmentHistorySearch} onChange={(event) => setAssignmentHistorySearch(event.target.value)} /></label>
              <select aria-label="Filter activity status" value={assignmentHistoryStatus} onChange={(event) => setAssignmentHistoryStatus(event.target.value)}>
                <option value="All">All activity</option>
                {["Pending", "In Progress", "Pending Review", "Completed", "Cancelled"].map((status) => <option key={status} value={status}>{status}</option>)}
              </select>
            </div>
            <div className="modern-history-results">
              <div className="modern-history-count">{filteredAssignmentHistory.length} recorded event{filteredAssignmentHistory.length === 1 ? "" : "s"}</div>
              {filteredAssignmentHistory.length ? (
                <div className="modern-history-timeline">
                  {filteredAssignmentHistory.slice(0, 250).map((item) => (
                    <button type="button" className="modern-history-event" key={`${item.assignmentId}-${item.id}`} onClick={() => { setAssignmentHistoryOpen(false); openAssignment(item.assignmentId); }}>
                      <span className="modern-history-timeline-node"><ClipboardCheck size={16}/></span>
                      <span className="modern-history-event-detail">
                        <span className="modern-history-event-heading"><strong>{item.title}</strong><span className={`admin-status-pill status-${slug(item.status)}`}>{item.status}</span></span>
                        <span className="modern-history-event-note">{item.note}</span>
                        <span className="modern-history-event-meta">{item.actor}{item.bookingCode ? ` · ${item.bookingCode}` : ""}{item.assignedTo ? ` · ${item.assignedTo}` : ""}</span>
                      </span>
                      <span className="modern-history-event-time">{item.timestamp ? formatDateTime(item.timestamp) : "Date unavailable"}</span>
                      <ChevronRight size={17} className="modern-history-event-arrow" />
                    </button>
                  ))}
                </div>
              ) : <EmptyState icon={History} title="No assignment history found" message="Historical assignment activity will appear here when tasks are recorded." />}
            </div>
            <footer className="modern-history-footer"><span>Showing up to 250 most recent matching events</span><button type="button" className="admin-btn-secondary" onClick={() => setAssignmentHistoryOpen(false)}>Close</button></footer>
          </section>
        </div>
      )}

      {profileEditOpen && (
        <div className="admin-modal-backdrop" onClick={() => !profileEditSaving && setProfileEditOpen(false)}>
          <section className="modern-profile-editor" role="dialog" aria-modal="true" aria-labelledby="modern-profile-edit-title" onClick={(event) => event.stopPropagation()}>
            <header className="admin-modal-header"><div><span className="admin-eyebrow">My account</span><h2 id="modern-profile-edit-title">Edit profile</h2></div><button type="button" aria-label="Close edit profile" onClick={() => setProfileEditOpen(false)} disabled={profileEditSaving}><X size={18}/></button></header>
            <form onSubmit={saveAdminProfile} className="modern-profile-edit-form">
              <div className="admin-profile-photo-editor">
                <Avatar name={profileEditForm.name} size={80} src={profileEditForm.avatarUrl} />
                <label className="admin-profile-photo-upload">Change photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseProfilePicture} disabled={profileEditSaving} /></label>
                {profileEditForm.avatarUrl && <button type="button" className="admin-btn-ghost" disabled={profileEditSaving} onClick={() => setProfileEditForm((current) => ({...current, avatarUrl: ""}))}>Remove photo</button>}
              </div>
              <label>Full name<input required minLength={3} maxLength={120} value={profileEditForm.name} onChange={(event) => setProfileEditForm((prev) => ({...prev, name:event.target.value}))}/></label>
              <label>Role<input value={profileRole} readOnly aria-readonly="true" className="admin-profile-role-field" /></label>
              <label>Email address<input required type="email" value={profileEditForm.email} onChange={(event) => setProfileEditForm((prev) => ({...prev, email:event.target.value}))}/></label>
              <label>Nickname<input maxLength={80} value={profileEditForm.nickname} onChange={(event) => setProfileEditForm((prev) => ({...prev, nickname:event.target.value}))}/></label>
              <label>Phone number<input type="tel" maxLength={40} value={profileEditForm.phone} onChange={(event) => setProfileEditForm((prev) => ({...prev, phone:event.target.value}))}/></label>
              {profileEditError && <p className="modern-profile-edit-error" role="alert"><AlertCircle size={15}/>{profileEditError}</p>}
              <footer className="admin-modal-actions"><button type="button" className="admin-btn-ghost" disabled={profileEditSaving} onClick={() => setProfileEditOpen(false)}>Cancel</button><button type="submit" className="admin-btn-primary" disabled={profileEditSaving}>{profileEditSaving ? <LoaderCircle size={15} className="admin-spin"/> : <Check size={15}/>} {profileEditSaving ? "Saving…" : "Save changes"}</button></footer>
            </form>
          </section>
        </div>
      )}

      {assignmentModalOpen && selectedAssignment && (
        <div
          className="admin-modal-backdrop"
          onClick={() => setAssignmentModalOpen(false)}
        >
          <section
            className="admin-assignment-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="admin-modal-header">
              <div>
                <span className="admin-eyebrow">Booking assignment</span>
                <h2>{selectedAssignment.title}</h2>
              </div>
              <button onClick={() => setAssignmentModalOpen(false)}>
                <X size={18} />
              </button>
            </header>
            <div className="admin-assignment-modal-body">
              <div className="admin-modal-pill-row">
                <StatusPill status={displayAssignmentStatus(selectedAssignment)} />
                <PriorityPill priority={selectedAssignment.priority} />
                <span>{selectedAssignment.progress || 0}% complete</span>
              </div>
              <dl className="admin-assignment-detail-grid">
                <div>
                  <dt>Booking</dt>
                  <dd>{selectedAssignment.bookingCode}</dd>
                </div>
                <div>
                  <dt>Guest</dt>
                  <dd>{selectedAssignment.guestName || selectedAssignment.guest}</dd>
                </div>
                <div>
                  <dt>Villa</dt>
                  <dd>{selectedAssignment.villaName || selectedAssignment.villa}</dd>
                </div>
                <div>
                  <dt>Department</dt>
                  <dd>{selectedAssignment.department || selectedAssignment.category}</dd>
                </div>
                <div>
                  <dt>Assigned Staff</dt>
                  <dd className="admin-assigned-staff-identity">
                    <ProfilePhoto
                      name={selectedAssignment.assignedTo || "Assigned Staff"}
                      src={selectedAssignment.assignedStaffAvatarUrl || staffDirectory.find((staff) => staff.id === selectedAssignment.assignedStaffId)?.avatarUrl}
                      size={48}
                    />
                    <span>{selectedAssignment.assignedTo || "Assigned Staff"}</span>
                  </dd>
                </div>
                <div>
                  <dt>Due</dt>
                  <dd>
                    {formatDate(selectedAssignment.dueDate)} · {selectedAssignment.dueTime}
                  </dd>
                </div>
              </dl>
              <section className="admin-detail-section">
                <h3>Instructions</h3>
                <p>{selectedAssignment.description}</p>
              </section>
              {selectedAssignment.notes && (
                <section className="admin-detail-section">
                  <h3>Booking / Guest Notes</h3>
                  <p>{selectedAssignment.notes}</p>
                </section>
              )}
              <section className="admin-detail-section">
                <h3>Checklist</h3>
                <div className="admin-detail-checklist">
                  {(selectedAssignment.checklist || []).map((item, index) => (
                    <div className={item.done ? "done" : ""} key={item.id || index}>
                      <span>{item.done ? <Check size={14} /> : index + 1}</span>
                      <p>{item.label || String(item)}</p>
                    </div>
                  ))}
                  {(!selectedAssignment.checklist || !selectedAssignment.checklist.length) && (
                    <p className="admin-panel-empty">No checklist items.</p>
                  )}
                </div>
              </section>
              <section className="admin-detail-section admin-audit-section">
                <h3>Status Activity</h3>
                <div className="admin-audit-list">
                  {(selectedAssignment.statusHistory || [
                    {
                      id: `${selectedAssignment.id}-created`,
                      status: selectedAssignment.status || "Pending",
                      actor: selectedAssignment.assignedBy || profile.name,
                      note: "Assignment record created.",
                      timestamp: selectedAssignment.createdAt,
                    },
                  ])
                    .slice()
                    .reverse()
                    .map((entry) => (
                      <div key={entry.id || entry.timestamp}>
                        <span />
                        <section>
                          <strong>{entry.status}</strong>
                          <p>{entry.note || "Status updated."}</p>
                          <small>{entry.actor || "System"} · {formatRelative(entry.timestamp)}</small>
                        </section>
                      </div>
                    ))}
                </div>
              </section>
            </div>
            <footer className="admin-modal-actions">
              {displayAssignmentStatus(selectedAssignment) !== "Completed" && <button
                className="admin-btn-ghost danger"
                onClick={() => {
                  setDeleteCandidate(selectedAssignment);
                  setAssignmentModalOpen(false);
                }}
              >
                <Trash2 size={15} /> Delete
              </button>}
              {displayAssignmentStatus(selectedAssignment) !== "Completed" && <button
                className="admin-btn-secondary"
                onClick={() => {
                  setEditingAssignment({ ...selectedAssignment });
                  setAssignmentModalOpen(false);
                }}
              >
                <Pencil size={15} /> Edit
              </button>}
              {displayAssignmentStatus(selectedAssignment) === "Pending Review" && <AssignmentReview key={selectedAssignment.id} task={selectedAssignment} update={updateAssignment} />}
            </footer>
          </section>
        </div>
      )}

      {editingAssignment && (
        <div
          className="admin-modal-backdrop"
          onClick={() => setEditingAssignment(null)}
        >
          <form
            className="admin-assignment-modal admin-task-editor-modal"
            onSubmit={saveEditedAssignment}
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="update-task-assignment-title"
          >
            <header className="admin-modal-header">
              <div>
                <span className="admin-eyebrow">Booking assignment</span>
                <h2 id="update-task-assignment-title">
                  Update Task Assignment
                </h2>
              </div>

              <button
                type="button"
                aria-label="Close update task assignment"
                onClick={() => setEditingAssignment(null)}
              >
                <X size={18} />
              </button>
            </header>

            <div className="admin-assignment-modal-body admin-task-editor-modal-body">
              <div className="admin-modal-pill-row">
                <StatusPill
                  status={displayAssignmentStatus(editingAssignment)}
                />
                <PriorityPill priority={editingAssignment.priority} />
                <span>{editingAssignment.progress || 0}% complete</span>
              </div>

              <dl className="admin-assignment-detail-grid">
                <div>
                  <dt>Booking</dt>
                  <dd>{editingAssignment.bookingCode || "No reference"}</dd>
                </div>

                <div>
                  <dt>Guest</dt>
                  <dd>
                    {editingAssignment.guestName ||
                      editingAssignment.guest ||
                      "No guest"}
                  </dd>
                </div>

                <div>
                  <dt>Villa</dt>
                  <dd>
                    {editingAssignment.villaName ||
                      editingAssignment.villa ||
                      "No villa"}
                  </dd>
                </div>

                <div>
                  <dt>Department</dt>
                  <dd>
                    {staffDirectory.find(
                      (staff) => staff.id === editingAssignment.assignedStaffId
                    )?.department ||
                      editingAssignment.department ||
                      editingAssignment.category ||
                      "Operations"}
                  </dd>
                </div>

                <div>
                  <dt>Assigned Staff</dt>
                  <dd>
                    {(() => {
                      const member = staffDirectory.find(
                        (staff) => staff.id === editingAssignment.assignedStaffId
                      );
                      const name = member?.name || editingAssignment.assignedTo || "Not selected";
                      return <span className="admin-assigned-staff-identity">
                        <ProfilePhoto
                          name={name}
                          src={member?.avatarUrl || editingAssignment.assignedStaffAvatarUrl}
                          size={48}
                        />
                        <span>{name}</span>
                      </span>;
                    })()}
                  </dd>
                </div>

                <div>
                  <dt>Due</dt>
                  <dd>
                    {editingAssignment.dueDate
                      ? `${formatDate(editingAssignment.dueDate)} · ${
                          editingAssignment.dueTime || "No time"
                        }`
                      : "Not scheduled"}
                  </dd>
                </div>
              </dl>

              <section className="admin-detail-section">
                <h3>Assignment Details</h3>

                <div className="admin-task-editor-grid">
                  <label className="admin-task-editor-field full">
                    <span>Task Title</span>
                    <input
                      value={editingAssignment.title}
                      onChange={(event) =>
                        setEditingAssignment((current) => ({
                          ...current,
                          title: event.target.value,
                        }))
                      }
                      placeholder="Enter a clear task title"
                    />
                  </label>

                  <label className="admin-task-editor-field">
                    <span>Assigned Staff</span>
                    <select
                      value={editingAssignment.assignedStaffId}
                      onChange={(event) =>
                        setEditingAssignment((current) => ({
                          ...current,
                          assignedStaffId: event.target.value,
                        }))
                      }
                    >
                      {staffDirectory
                        .filter((staff) => staff.accountStatus !== "Disabled")
                        .map((staff) => (
                          <option key={staff.id} value={staff.id}>
                            {staff.name} — {staff.department}
                          </option>
                        ))}
                    </select>
                  </label>

                  <label className="admin-task-editor-field">
                    <span>Priority</span>
                    <select
                      value={editingAssignment.priority}
                      onChange={(event) =>
                        setEditingAssignment((current) => ({
                          ...current,
                          priority: event.target.value,
                        }))
                      }
                    >
                      {PRIORITIES.map((priority) => (
                        <option key={priority} value={priority}>
                          {priority}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="admin-task-editor-field">
                    <span>Due Date</span>
                    <input
                      type="date"
                      min={today}
                      value={editingAssignment.dueDate}
                      onChange={(event) =>
                        setEditingAssignment((current) => ({
                          ...current,
                          dueDate: event.target.value,
                        }))
                      }
                    />
                  </label>

                  <label className="admin-task-editor-field">
                    <span>Due Time</span>
                    <input
                      type="time"
                      value={editingAssignment.dueTime || ""}
                      onChange={(event) =>
                        setEditingAssignment((current) => ({
                          ...current,
                          dueTime: event.target.value,
                        }))
                      }
                    />
                  </label>
                </div>
              </section>

              <section className="admin-detail-section">
                <h3>Instructions</h3>

                <label className="admin-task-editor-field full">
                  <textarea
                    rows={5}
                    value={editingAssignment.description || ""}
                    onChange={(event) =>
                      setEditingAssignment((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    placeholder="Add complete task instructions for the assigned staff member."
                  />
                </label>
              </section>

              <section className="admin-detail-section">
                <h3>Checklist</h3>

                <div className="admin-task-checklist-editor">
                  {(editingAssignment.checklist || []).map((item, index) => (
                    <div
                      className="admin-task-checklist-row"
                      key={item?.id || index}
                    >
                      <span>{index + 1}</span>

                      <input
                        value={
                          typeof item === "string"
                            ? item
                            : item?.label || ""
                        }
                        onChange={(event) =>
                          setEditingAssignment((current) => ({
                            ...current,
                            checklist: (current.checklist || []).map(
                              (task, taskIndex) =>
                                taskIndex === index
                                  ? typeof task === "string"
                                    ? {
                                        id: `${current.id}-check-${index}`,
                                        label: event.target.value,
                                        done: false,
                                      }
                                    : {
                                        ...task,
                                        label: event.target.value,
                                      }
                                  : task
                            ),
                          }))
                        }
                      />

                      <button
                        type="button"
                        className="admin-task-checklist-remove"
                        aria-label={`Remove checklist item ${index + 1}`}
                        onClick={() =>
                          setEditingAssignment((current) => ({
                            ...current,
                            checklist: (current.checklist || []).filter(
                              (_, taskIndex) => taskIndex !== index
                            ),
                          }))
                        }
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}

                  {(!editingAssignment.checklist ||
                    !editingAssignment.checklist.length) && (
                    <p className="admin-panel-empty">
                      No checklist items. Add one below.
                    </p>
                  )}

                  <button
                    type="button"
                    className="admin-btn-secondary admin-task-add-checklist"
                    onClick={() =>
                      setEditingAssignment((current) => ({
                        ...current,
                        checklist: [
                          ...(current.checklist || []),
                          {
                            id: `${current.id}-check-${Date.now()}`,
                            label: "",
                            done: false,
                          },
                        ],
                      }))
                    }
                  >
                    <Plus size={14} /> Add Checklist Item
                  </button>
                </div>
              </section>
            </div>

            <footer className="admin-modal-actions admin-task-editor-actions">
              <button
                type="button"
                className="admin-btn-ghost"
                onClick={() => setEditingAssignment(null)}
              >
                Cancel
              </button>

              <button
                className="admin-btn-primary"
                type="submit"
              >
                <Check size={15} /> Save Changes
              </button>
            </footer>
          </form>
        </div>
      )}

      {deleteCandidate && (
        <div
          className="admin-modal-backdrop"
          onClick={() => setDeleteCandidate(null)}
        >
          <section
            className="admin-confirm-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-assignment-title"
          >
            <span className="admin-confirm-icon danger"><Trash2 size={22} /></span>
            <h2 id="delete-assignment-title">Delete assignment?</h2>
            <p>
              “{deleteCandidate.title}” will be removed from the administrator monitor and the shared staff task storage. This cannot be undone.
            </p>
            <div>
              <button
                type="button"
                className="admin-btn-secondary"
                onClick={() => setDeleteCandidate(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="admin-btn-danger"
                onClick={() => deleteAssignment(deleteCandidate.id)}
              >
                <Trash2 size={16} /> Delete Assignment
              </button>
            </div>
          </section>
        </div>
      )}


      {staffAccountModalOpen && (
        <div
          className="admin-modal-backdrop"
          onClick={() => setStaffAccountModalOpen(false)}
        >
          <form
            className="admin-staff-account-modal"
            onSubmit={saveStaffAccount}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="admin-modal-header">
              <div>
                <span className="admin-eyebrow">Staff access management</span>
                <h2>
                  {staffAccountMode === "create"
                    ? "Create Staff Account"
                    : "Manage Staff Account"}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setStaffAccountModalOpen(false)}
              >
                <X size={18} />
              </button>
            </header>

            <div className="admin-staff-account-form">
              <section className="admin-account-form-intro">
                <span><UserCog size={20} /></span>
                <div>
                  <strong>Profile and login access</strong>
                  <p>
                    Changes here update the shared staff directory used by staff
                    assignments and operations.
                  </p>
                </div>
              </section>

              <label>
                <span>Complete name *</span>
                <input
                  value={staffAccountForm.name}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                  placeholder="Staff complete name"
                />
              </label>
              <label>
                <span>Username *</span>
                <input
                  value={staffAccountForm.username}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      username: event.target.value,
                    }))
                  }
                  placeholder="staff.username"
                />
              </label>
              <label>
                <span>Email address *</span>
                <input
                  type="email"
                  value={staffAccountForm.email}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      email: event.target.value,
                    }))
                  }
                  placeholder="staff@thevilla.ph"
                />
              </label>
              <label>
                <span>Department *</span>
                <select
                  value={staffAccountForm.department}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      department: event.target.value,
                    }))
                  }
                >
                  {DEPARTMENTS.map((department) => (
                    <option key={department}>{department}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Role *</span>
                <input
                  value={staffAccountForm.role}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      role: event.target.value,
                    }))
                  }
                  placeholder="Example: Housekeeping Staff"
                />
              </label>
              <label>
                <span>Shift</span>
                <input
                  value={staffAccountForm.shift}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      shift: event.target.value,
                    }))
                  }
                  placeholder="8:00 AM – 5:00 PM"
                />
              </label>
              <label>
                <span>Account status</span>
                <select
                  value={staffAccountForm.accountStatus}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      accountStatus: event.target.value,
                    }))
                  }
                >
                  <option>Active</option>
                  <option>Disabled</option>
                </select>
              </label>

              <label className="admin-account-checkbox full">
                <input
                  type="checkbox"
                  checked={!!staffAccountForm.mustChangePassword}
                  onChange={(event) =>
                    setStaffAccountForm((current) => ({
                      ...current,
                      mustChangePassword: event.target.checked,
                    }))
                  }
                />
                <span>
                  <strong>Require password change</strong>
                  <small>
                    The staff member must create a new password during the next
                    successful sign-in.
                  </small>
                </span>
              </label>

              {staffAccountError && (
                <div className="admin-form-error full" role="alert">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Account could not be saved</strong>
                    <p>{staffAccountError}</p>
                  </div>
                </div>
              )}
            </div>

            <footer className="admin-staff-account-modal-actions">
              <div>
                {staffAccountMode === "edit" && (
                  <button
                    type="button"
                    className="admin-btn-secondary"
                    onClick={() => resetStaffPassword(staffAccountForm.id)}
                  >
                    <KeyRound size={16} /> Reset Password
                  </button>
                )}
              </div>
              <div>
                <button
                  type="button"
                  className="admin-btn-ghost"
                  onClick={() => setStaffAccountModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="admin-btn-primary">
                  <Check size={16} />
                  {staffAccountMode === "create"
                    ? "Create Account"
                    : "Save Account"}
                </button>
              </div>
            </footer>
          </form>
        </div>
      )}


      {receiptModalOpen && receiptTransaction && (
        <div
          className="admin-modal-backdrop admin-receipt-backdrop"
          onClick={() => setReceiptModalOpen(false)}
        >
          <section
            className="admin-receipt-modal admin-receipt-print-area"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="admin-receipt-brand">
              <span className="admin-receipt-logo">
                <img src="/favicon.png" alt="The Villa logo" />
              </span>
              <div>
                <h2>The Villa - Batangas</h2>
                <p>Front Desk Official Payment Receipt</p>
              </div>
              <StatusPill status="Paid" />
            </header>

            <div className="admin-receipt-number-row">
              <span>
                <small>Receipt Number</small>
                <strong>{receiptTransaction.receiptNumber}</strong>
              </span>
              <span>
                <small>Date and Time</small>
                <strong>
                  {formatDateTime(receiptTransaction.processedAt)}
                </strong>
              </span>
            </div>

            <div className="admin-receipt-body">
              <section className="admin-receipt-party">
                <div>
                  <small>Received from</small>
                  <strong>
                    {receiptTransaction.payerName ||
                      receiptTransaction.guestName}
                  </strong>
                  <span>{receiptTransaction.guestName}</span>
                </div>
                <div>
                  <small>Booking</small>
                  <strong>{receiptTransaction.bookingCode}</strong>
                  <span>{receiptTransaction.villaName}</span>
                </div>
              </section>

              <section className="admin-receipt-breakdown">
                <div>
                  <span>Previous booking payment</span>
                  <strong>
                    {formatPeso(receiptTransaction.previousAmountPaid)}
                  </strong>
                </div>
                <div>
                  <span>Room balance received</span>
                  <strong>
                    {formatPeso(
                      receiptTransaction.roomBalance ||
                        receiptTransaction.previousBalance
                    )}
                  </strong>
                </div>
                <div>
                  <span>Other charges</span>
                  <strong>
                    {formatPeso(receiptTransaction.otherChargesTotal)}
                  </strong>
                </div>
                <div className="received">
                  <span>Total received now</span>
                  <strong>{formatPeso(receiptTransaction.amount)}</strong>
                </div>
                <div>
                  <span>Total booking amount paid</span>
                  <strong>
                    {formatPeso(receiptTransaction.newAmountPaid)}
                  </strong>
                </div>
                <div className="balance">
                  <span>Remaining room balance</span>
                  <strong>{formatPeso(receiptTransaction.newBalance)}</strong>
                </div>
              </section>

              {Array.isArray(receiptTransaction.otherCharges) &&
                receiptTransaction.otherCharges.length > 0 && (
                  <section className="admin-receipt-charge-list">
                    <small>Other charge details</small>
                    {receiptTransaction.otherCharges.map((charge, index) => (
                      <div key={charge.id || `${charge.description}-${index}`}>
                        <span>{charge.description}</span>
                        <strong>{formatPeso(charge.amount)}</strong>
                      </div>
                    ))}
                  </section>
                )}

              <dl className="admin-receipt-meta">
                <div>
                  <dt>Payment Method</dt>
                  <dd>{receiptTransaction.method}</dd>
                </div>
                <div>
                  <dt>Payment Stage</dt>
                  <dd>{receiptTransaction.stage}</dd>
                </div>
                <div>
                  <dt>Reference</dt>
                  <dd>{receiptTransaction.reference}</dd>
                </div>
                <div>
                  <dt>Cashier</dt>
                  <dd>{receiptTransaction.cashierName}</dd>
                </div>
                {receiptTransaction.method === "Cash" && (
                  <>
                    <div>
                      <dt>Total Cash Given</dt>
                      <dd>
                        {formatPeso(receiptTransaction.cashTendered)}
                      </dd>
                    </div>
                    <div>
                      <dt>Change Returned</dt>
                      <dd>{formatPeso(receiptTransaction.changeGiven)}</dd>
                    </div>
                  </>
                )}
              </dl>

              {receiptTransaction.notes && (
                <section className="admin-receipt-notes">
                  <small>Front desk notes</small>
                  <p>{receiptTransaction.notes}</p>
                </section>
              )}

              <div className="admin-receipt-verification">
                <ShieldCheck size={18} />
                <p>
                  This receipt confirms the room balance and any listed other
                  charges collected by the front desk. Keep the receipt number
                  for payment verification.
                </p>
              </div>
            </div>

            <footer className="admin-receipt-actions">
              <button
                type="button"
                className="admin-btn-secondary"
                onClick={() => setReceiptModalOpen(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="admin-btn-primary"
                onClick={printReceipt}
              >
                <Printer size={16} /> Print Receipt
              </button>
            </footer>
          </section>
        </div>
      )}

      <ConfirmSignOut open={signOutConfirmOpen} busy={signingOut} cancel={()=>setSignOutConfirmOpen(false)} confirm={signOut}/>
      {dataLoading && <LoadingScreen message="Loading your admin workspace…"/>}
      {dataError && <div className="fixed bottom-4 left-4 right-4 z-[20000] mx-auto max-w-lg"><AlertMessage message={dataError}/></div>}
      {systemAlert.open && (systemAlert.type === "loading"
        ? <LoadingScreen message={systemAlert.message}/>
        : <div className="fixed bottom-4 left-4 right-4 z-[25000] mx-auto max-w-lg"><AlertMessage message={systemAlert.message} type={systemAlert.type} dismiss={closeSystemAlert}/></div>)}
    </div>
  );
}
