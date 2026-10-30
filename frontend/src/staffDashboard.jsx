import { AlertMessage, ConfirmSignOut, LoadingScreen } from "./SystemFeedback";
import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import { formatUserFacingMessage, getApiErrorMessage, getUserFacingError } from "./errorMessages.mjs";
import { singleFlightRefresh } from "./liveTransport.mjs";
import useLiveUpdates from "./useLiveUpdates";
import { snapshotRows } from "./dashboardSnapshot.mjs";
import React from "react";
import {
  CalendarDays,
  Check,
  ClipboardList,
  History,
  LockKeyhole,
  LogOut,
  Wrench,
} from "lucide-react";
import "./staffDashboard.css";
import StaffSchedule from "./StaffSchedule";
import StaffVillaOperations from "./StaffVillaOperations";
import StaffNotifications from "./StaffNotifications";
import StaffTaskBoard, { StaffOverview } from "./StaffTaskBoard";
import StaffTaskWorkspace from "./StaffTaskWorkspace";
import "./StaffFlow.css";
import { isLate, needsAvailabilityResponse } from "./taskFlow.mjs";



const ADMIN_CONTACT = {
  id: "ADMIN-001",
  name: "Villa Administrator",
  role: "Operations Administrator",
  department: "Villa Operations",
  email: "admin@thevilla.ph",
  phone: "+63 917 555 0100",
  online: true,
};

const SIDEBAR_ITEMS = [
  { id: "overview", label: "My workspace", icon: ClipboardList },
  { id: "calendar", label: "My Schedule", icon: CalendarDays },
  { id: "todo", label: "My assignments", icon: ClipboardList, preset: { tab: "My work", focus: "To do" }, count: "todo" },
  { id: "inProgress", label: "In progress", icon: ClipboardList, preset: { tab: "My work", focus: "In progress" }, count: "inProgress" },
  { id: "review", label: "Awaiting approval", icon: Check, preset: { tab: "In review", focus: "All work" }, count: "review" },
  { id: "history", label: "History", icon: History },
];

const API_BASE_URL = (
  (typeof window !== "undefined" && window.__THE_VILLA_API_BASE__) ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const PORTAL_AUTH_KEYS = [
  "theVillaPortalAuth",
  "theVillaStaffAuth",
];

const PORTAL_ACCESS_TOKEN_KEYS = [
  "theVillaAuthToken",
  "theVillaApiToken",
];

const PORTAL_REFRESH_TOKEN_KEY =
  "theVillaRefreshToken";

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

  const normalized = value.trim();

  if (
    INVALID_PORTAL_TOKEN_VALUES.has(
      normalized.toLowerCase()
    )
  ) {
    return "";
  }

  return normalized;
}


function readCookie(name) {
  if (
    typeof document === "undefined" ||
    !name
  ) {
    return "";
  }

  const prefix =
    `${encodeURIComponent(name)}=`;

  const parts =
    document.cookie
      .split(";")
      .map((part) => part.trim());

  const match =
    parts.find((part) =>
      part.startsWith(prefix)
    );

  return match
    ? match.slice(prefix.length)
    : "";
}

function cleanString(value) {
  return typeof value === "string"
    ? value.trim()
    : "";
}

function readPortalStorageValue(key) {
  return (
    sessionStorage.getItem(key) ||
    localStorage.getItem(key) ||
    ""
  );
}

function getPortalAuth() {
  for (const key of PORTAL_AUTH_KEYS) {
    const raw = readPortalStorageValue(key);

    if (!raw) {
      continue;
    }

    try {
      const parsed = JSON.parse(raw);

      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    }
  }

  return {};
}

function clearPortalAuth({
  redirect = true,
} = {}) {
  PORTAL_AUTH_KEYS.forEach((key) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });

  PORTAL_ACCESS_TOKEN_KEYS.forEach((key) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });

  localStorage.removeItem(
    PORTAL_REFRESH_TOKEN_KEY
  );

  sessionStorage.removeItem(
    PORTAL_REFRESH_TOKEN_KEY
  );

  if (
    redirect &&
    typeof window !== "undefined" &&
    window.location.pathname !== "/admin-login"
  ) {
    window.location.replace(
      "/admin-login"
    );
  }
}

function getPortalAccessToken() {
  const auth = getPortalAuth();

  const sessionToken =
    normalizePortalToken(
      auth.access_token ||
      auth.accessToken ||
      auth.token
    );

  if (sessionToken) {
    return sessionToken;
  }

  for (
    const key
    of PORTAL_ACCESS_TOKEN_KEYS
  ) {
    const token =
      normalizePortalToken(
        readPortalStorageValue(
          key
        )
      );

    if (token) {
      return token;
    }
  }

  return "";
}

function getPortalRefreshToken() {
  const auth = getPortalAuth();

  return normalizePortalToken(
    auth.refresh_token ||
    auth.refreshToken ||
    readPortalStorageValue(
      PORTAL_REFRESH_TOKEN_KEY
    )
  );
}

function savePortalAuth(payload) {
  const existing = getPortalAuth();

  const accessToken =
    normalizePortalToken(
      payload?.access_token ||
      payload?.accessToken ||
      payload?.token ||
      existing?.access_token ||
      existing?.accessToken ||
      existing?.token
    );

  const refreshToken =
    normalizePortalToken(
      payload?.refresh_token ||
      payload?.refreshToken ||
      existing?.refresh_token ||
      existing?.refreshToken
    );

  const user = {
    ...(existing?.user || {}),
    ...(payload?.user || {}),
  };

  const role = cleanString(
    user?.portalRole ||
    user?.role ||
    payload?.portalRole ||
    payload?.role ||
    existing?.portalRole ||
    existing?.role
  ).toLowerCase();

  const nextAuth = {
    ...existing,
    ...payload,

    authenticated: true,

    user: {
      ...user,
      role:
        user?.role ||
        role,
      portalRole:
        user?.portalRole ||
        role,
    },

    role,
    portalRole:
      role,

    access_token:
      accessToken,

    refresh_token:
      refreshToken,

    accessToken,
    refreshToken,
  };

  clearPortalAuth({
    redirect: false,
  });

  sessionStorage.setItem(
    "theVillaPortalAuth",
    JSON.stringify(nextAuth)
  );

  return nextAuth;
}

function syncPortalProfile(profile) {
  const normalized =
    normalizeStaffAccount(
      profile || {}
    );

  if (!normalized.id) {
    return;
  }

  const existing =
    getPortalAuth();

  const nextUser = {
    ...(existing?.user || {}),
    ...(profile || {}),

    id:
      normalized.id,

    staffId:
      normalized.id,

    staff_account_id:
      normalized.id,

    auth_user_id:
      normalized.authUserId,

    authUserId:
      normalized.authUserId,

    name:
      normalized.name,

    full_name:
      normalized.name,

    fullName:
      normalized.name,

    email:
      normalized.email,

    username:
      normalized.username,

    department:
      normalized.department,

    position:
      normalized.position,

    displayRole:
      normalized.role,

    role:
      normalized.portalRole,

    portalRole:
      normalized.portalRole,
  };

  savePortalAuth({
    ...existing,
    user:
      nextUser,

    id:
      normalized.id,

    staffId:
      normalized.id,

    authUserId:
      normalized.authUserId,

    name:
      normalized.name,

    full_name:
      normalized.name,

    fullName:
      normalized.name,

    email:
      normalized.email,

    role:
      normalized.portalRole,

    portalRole:
      normalized.portalRole,

    department:
      normalized.department,

    position:
      normalized.position,
  });
}

let portalRefreshPromise = null;

async function refreshPortalSession() {
  if (portalRefreshPromise) {
    return portalRefreshPromise;
  }

  portalRefreshPromise = (async () => {
    const refreshToken =
      getPortalRefreshToken();

    if (!refreshToken) {
      clearPortalAuth();

      throw new Error(
        "Your login session has expired. Please sign in again."
      );
    }

    const response = await fetch(
      `${API_BASE_URL}/staff-auth/refresh`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type":
            "application/json",
        },
        body: JSON.stringify({
          refresh_token: refreshToken,
        }),
      }
    );

    const payload = await response
      .json()
      .catch(() => ({}));

    const accessToken =
      normalizePortalToken(
        payload?.access_token
      );

    const rotatedRefreshToken =
      normalizePortalToken(
        payload?.refresh_token
      );

    if (
      !response.ok ||
      !accessToken ||
      !rotatedRefreshToken
    ) {
      clearPortalAuth();

      throw new Error(
        payload?.detail ||
          payload?.message ||
          "Your login session has expired. Please sign in again."
      );
    }

    return savePortalAuth({
      ...payload,
      access_token: accessToken,
      refresh_token:
        rotatedRefreshToken,
    });
  })();

  try {
    return await portalRefreshPromise;
  } finally {
    portalRefreshPromise = null;
  }
}

async function staffApiRequest(
  path,
  options = {},
  allowRefresh = true
) {
  const performRequest = async () => {
    const token = getPortalAccessToken();
    const refreshToken =
      getPortalRefreshToken();

    if (!token) {
      clearPortalAuth();

      throw new Error(
        "Your saved portal session is invalid. Please sign in again."
      );
    }

    const xsrf = decodeURIComponent(
      readCookie("XSRF-TOKEN") || ""
    );

    const headers = {
      Accept: "application/json",
      ...(options.body
        ? {
            "Content-Type":
              "application/json",
          }
        : {}),
      ...(token
        ? {
            Authorization:
              `Bearer ${token}`,
          }
        : {}),
      ...(refreshToken
        ? {
            "X-Refresh-Token":
              refreshToken,
          }
        : {}),
      ...(xsrf
        ? {
            "X-XSRF-TOKEN": xsrf,
          }
        : {}),
      ...(options.headers || {}),
    };

    try {
      return await fetch(
        `${API_BASE_URL}${path}`,
        {
          credentials: "include",
          ...options,
          headers,
        }
      );
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new Error(getUserFacingError(error, "We couldn't connect to The Villa. Please try again."));
    }
  };

  let response = await performRequest();

  if (
    response.status === 401 &&
    allowRefresh
  ) {
    const refreshToken =
      getPortalRefreshToken();

    if (!refreshToken) {
      clearPortalAuth();
    } else {
      await refreshPortalSession();
      response = await performRequest();
    }
  }

  const payload = await response
    .json()
    .catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, response.status)
    );
  }

  return payload;
}


// ============================================================
// STORAGE / NORMALIZATION HELPERS
// ============================================================
function normalizeStaffAccount(
  staff,
  index = 0
) {
  const email =
    cleanString(
      staff?.email
    ).toLowerCase();

  const accountId =
    cleanString(
      staff?.id ||
      staff?.staffId ||
      staff?.staff_id ||
      staff?.staffAccountId ||
      staff?.staff_account_id
    );

  const authUserId =
    cleanString(
      staff?.authUserId ||
      staff?.auth_user_id
    );

  const fullName =
    cleanString(
      staff?.name ||
      staff?.fullName ||
      staff?.full_name ||
      staff?.displayName ||
      staff?.display_name
    ) ||
    (
      [
        cleanString(
          staff?.firstName ||
          staff?.first_name
        ),
        cleanString(
          staff?.lastName ||
          staff?.last_name
        ),
      ]
        .filter(Boolean)
        .join(" ")
        .trim()
    ) ||
    "Villa Staff";

  const username =
    (
      cleanString(
        staff?.username
      ) ||
      email.split("@")[0] ||
      `staff${index + 1}`
    )
      .toLowerCase()
      .replace(
        /[^a-z0-9._-]/g,
        ""
      ) ||
    `staff${index + 1}`;

  const portalRole =
    cleanString(
      staff?.portalRole ||
      staff?.portal_role ||
      staff?.accountRole ||
      staff?.account_role ||
      (
        ["admin", "staff"].includes(
          cleanString(
            staff?.role
          ).toLowerCase()
        )
          ? staff?.role
          : ""
      )
    ).toLowerCase() ||
    "staff";

  const position =
    cleanString(
      staff?.position ||
      staff?.displayRole ||
      staff?.display_role ||
      (
        !["admin", "staff"].includes(
          cleanString(
            staff?.role
          ).toLowerCase()
        )
          ? staff?.role
          : ""
      )
    ) ||
    (
      portalRole === "admin"
        ? "Administrator"
        : "Staff Member"
    );

  const rawStatus =
    cleanString(
      staff?.accountStatus ||
      staff?.account_status
    ).toLowerCase();

  const isActive =
    staff?.isActive ??
    staff?.is_active ??
    (
      rawStatus
        ? rawStatus !==
          "disabled"
        : true
    );

  return {
    ...staff,

    id:
      accountId,

    staffId:
      accountId,

    staff_account_id:
      accountId,

    authUserId,

    auth_user_id:
      authUserId,

    name:
      fullName,

    fullName:
      fullName,

    full_name:
      fullName,

    username,

    role:
      position,

    position,

    portalRole,

    department:
      cleanString(
        staff?.department
      ) ||
      "Administration",

    shift:
      cleanString(
        staff?.shift
      ) ||
      "8:00 AM – 5:00 PM",

    personalEmail: cleanString(staff?.personalEmail || staff?.personal_email),
    email:
      email ||
      "",

    online:
      Boolean(
        staff?.online
      ),

    isActive:
      Boolean(isActive),

    accountStatus:
      isActive
        ? "Active"
        : "Disabled",

    mustChangePassword:
      staff?.mustChangePassword ??
      staff?.must_change_password ??
      false,

    lastLogin:
      staff?.lastLogin ||
      staff?.last_login ||
      staff?.last_login_at ||
      "",

    createdAt:
      staff?.createdAt ||
      staff?.created_at ||
      "",

    updatedAt:
      staff?.updatedAt ||
      staff?.updated_at ||
      "",
  };
}

function formatDate(dateString, long = false) {
  if (!dateString) return "Not scheduled";
  const date = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(dateString);
  return date.toLocaleDateString("en-PH", {
    weekday: long ? "short" : undefined,
    month: long ? "long" : "short",
    day: "numeric",
    year: "numeric",
  });
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

function normalizeChecklist(task) {
  const checklist = Array.isArray(task?.checklist) ? task.checklist : [];
  return checklist.map((item, index) => ({
    id: item.id || `${task.id}-check-${index}`,
    label: item.label || item.text || `Checklist item ${index + 1}`,
    done: !!item.done,
  }));
}

function normalizeTask(task) {
  const assignedStaffId =
    cleanString(
      task?.assignedStaffId ||
      task?.assigned_staff_id ||
      task?.staffId ||
      task?.staff_id
    );

  return {
    ...task,

    id:
      cleanString(
        task?.id
      ) ||
      `ASSIGN-${Date.now()}`,

    title:
      cleanString(
        task?.title
      ) ||
      "Villa assignment",

    category:
      cleanString(
        task?.category ||
        task?.department
      ) ||
      "Administration",

    department:
      cleanString(
        task?.department ||
        task?.category
      ) ||
      "Administration",

    bookingId:
      cleanString(
        task?.bookingId ||
        task?.booking_id
      ),

    bookingCode:
      cleanString(
        task?.bookingCode ||
        task?.booking_code ||
        task?.bookingId ||
        task?.booking_id
      ),

    villaName:
      cleanString(
        task?.villaName ||
        task?.villa_name ||
        task?.villa
      ) ||
      "Villa",

    guestName:
      cleanString(
        task?.guestName ||
        task?.guest_name ||
        task?.guest
      ) ||
      "Villa Guest",

    assignedStaffId,

    assigned_staff_id:
      assignedStaffId,

    assignedTo:
      cleanString(
        task?.assignedTo ||
        task?.assigned_to
      ),

    assignedBy:
      cleanString(
        task?.assignedBy ||
        task?.assigned_by
      ) ||
      (task?.source === "automatic-booking-preparation" ? "System" : "Operations"),

    priority:
      cleanString(
        task?.priority
      ) ||
      "Medium",

    status:
      cleanString(
        task?.status
      ) ||
      "Pending",

    maintenanceOnCall: task?.maintenanceOnCall || null,

    dueDate:
      task?.dueDate ||
      task?.due_date ||
      "",

    dueTime:
      task?.dueTime ||
      task?.due_time ||
      "",

    description:
      cleanString(
        task?.description
      ) ||
      "No instructions were provided.",

    notes:
      task?.notes ||
      "",

    checklist:
      normalizeChecklist(
        task
      ),

    progress:
      Number(
        task?.progress ||
        0
      ),

    createdAt:
      task?.createdAt ||
      task?.created_at ||
      new Date().toISOString(),

    updatedAt:
      task?.updatedAt ||
      task?.updated_at ||
      "",

    statusHistory:
      Array.isArray(
        task?.statusHistory
      )
        ? task.statusHistory
        : Array.isArray(
            task?.status_history
          )
        ? task.status_history
        : [],
  };
}

// ============================================================
// SMALL COMPONENTS
// ============================================================
function Avatar({ name, online = false, size = 40, src }) {
  const [imageFailed, setImageFailed] = React.useState(false);
  React.useEffect(() => setImageFailed(false), [src]);
  return (
    <span
      className="staff-avatar-wrap"
      style={{ width: size, height: size, minWidth: size }}
    >
      <span
        className="staff-avatar"
        style={{ width: size, height: size, fontSize: size * 0.36 }}
      >
        {src && !imageFailed ? <img src={src} alt={`${name || "Staff"} profile`} onError={() => setImageFailed(true)} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "50%" }} /> : initials(name)}
      </span>
      {online && <i className="staff-online-dot" />}
    </span>
  );
}

function StatusPill({ status }) {
  return (
    <span className={`staff-status-pill status-${slug(status)}`}>
      {status}
    </span>
  );
}

function EmptyState({ icon: Icon, title, message, action, onAction }) {
  return (
    <div className="staff-empty-state">
      {Icon && <Icon size={46} strokeWidth={1.3} />}
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action && (
        <button type="button" className="staff-btn-primary" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

// ============================================================
// MAIN COMPONENT
// ============================================================
export default function StaffDashboard() {
  const [view, setView] = React.useState("overview");
  const [villaFocus, setVillaFocus] = React.useState('');
  const initialViewChosen = React.useRef(false);
  const [taskBoardPreset,setTaskBoardPreset] = React.useState({tab:"My work",focus:"To do"});
  const [toast, setToast] = React.useState("");
  const [profileOpen, setProfileOpen] = React.useState(false);
  const [profileForm, setProfileForm] = React.useState({ name: "", nickname: "", avatarUrl: "", personalEmail: "" });
  const [profileError, setProfileError] = React.useState("");
  const [profileSaving, setProfileSaving] = React.useState(false);
  const profileDialog = React.useRef(null);
  React.useEffect(() => {
    if (profileOpen) profileDialog.current?.showModal();
    else profileDialog.current?.close();
  }, [profileOpen]);


  const [, setStaffDirectory] = React.useState([]);
  const [currentStaff, setCurrentStaff] = React.useState(
    normalizeStaffAccount({
      id: "",
      name: "Villa Staff",
      role: "Staff Member",
      department: "Administration",
      accountStatus: "Active",
    })
  );
  const [, setAdminContact] = React.useState(ADMIN_CONTACT);
  const [allTasks, setAllTasks] = React.useState([]);
  const [staffNotifications, setStaffNotifications] = React.useState([]);
  const [notificationPopupsEnabled, setNotificationPopupsEnabled] = React.useState(true);
  const linkedTaskOpened = React.useRef(false);
  const [dataLoading, setDataLoading] = React.useState(true);
  const [signOutConfirmOpen, setSignOutConfirmOpen] = React.useState(false);
  const [signingOut, setSigningOut] = React.useState(false);
  const signingOutLock = React.useRef(false);
  const [taskSavingId, setTaskSavingId] = React.useState("");
  const taskUpdateLock = React.useRef(false);
  const [dataError, setDataError] = React.useState("");

  const [selectedTaskId, setSelectedTaskId] = React.useState("");
  const [taskModalOpen, setTaskModalOpen] = React.useState(false);

  const toastTimerRef = React.useRef(null);

  const tasks = React.useMemo(
    () =>
      allTasks.map(
        normalizeTask
      ),
    [allTasks]
  );
  const isMaintenanceStaff = currentStaff.department?.toLowerCase() === "maintenance";
  const workspaceTasks = React.useMemo(
    () => isMaintenanceStaff
      ? tasks.filter(task => task.source === "manual-maintenance-request" && !needsAvailabilityResponse(task))
      : tasks,
    [isMaintenanceStaff, tasks]
  );
  const sidebarItems = isMaintenanceStaff
    ? [
      { id: "villas", label: "New request", icon: Wrench },
      { id: "calendar", label: "My schedule", icon: CalendarDays },
      { id: "todo", label: "My tasks", icon: ClipboardList, preset: { tab: "My work", focus: "All work" } },
      { id: "history", label: "Completed", icon: Check },
    ]
    : SIDEBAR_ITEMS;

  const selectedTask = React.useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || null,
    [tasks, selectedTaskId]
  );

  const showToast = React.useCallback((message) => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    setToast(message);
    toastTimerRef.current = window.setTimeout(() => setToast(""), 2800);
  }, []);

  const fetchStaffData = React.useCallback(async ({ silent = false } = {}) => {
    if (silent && taskUpdateLock.current) return;
    if (!silent) {
      setDataLoading(true);
      setDataError("");
    }

    try {
      const payload = await staffApiRequest("/staff/bootstrap");
      if (silent && taskUpdateLock.current) return;
      const data = payload?.data || {};

      const databaseProfile =
        normalizeStaffAccount(
          data.profile ||
          getPortalAuth()?.user ||
          {}
        );

      if (!databaseProfile.id) {
        throw new Error(
          "The logged-in staff profile was not returned by the database."
        );
      }

      setCurrentStaff(
        databaseProfile
      );
      if (!initialViewChosen.current) {
        initialViewChosen.current = true;
        if (databaseProfile.department?.toLowerCase() === 'maintenance' && !new URLSearchParams(window.location.search).get('task')) setView('villas');
      }


      syncPortalProfile(
        data.profile ||
        databaseProfile
      );

      setStaffDirectory(current => snapshotRows(current,
        Array.isArray(data.staff) ? data.staff.map(normalizeStaffAccount) : null));
      if (data.administrator) {
        setAdminContact((current) => ({
          ...current,
          ...data.administrator,
          name:
            data.administrator.name ||
            data.administrator.fullName ||
            current.name,
          role:
            data.administrator.position ||
            data.administrator.role ||
            current.role,
        }));
      }
      setAllTasks(current => snapshotRows(current, data.tasks));
      setStaffNotifications(current => snapshotRows(current, data.notifications));
      setNotificationPopupsEnabled(data.settings?.pushNotifications !== false);
      setDataError("");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to load staff data from the database.";
      setDataError(message);
      if (!silent) setToast(message);
    } finally {
      if (!silent) setDataLoading(false);
    }
  }, []);
  const loadStaffData = React.useMemo(() => singleFlightRefresh(fetchStaffData), [fetchStaffData]);

  const loadStaffNotifications = React.useMemo(() => singleFlightRefresh(async () => {
    const payload = await staffApiRequest("/staff/notifications");
    setStaffNotifications(current => snapshotRows(current, payload?.data));
  }), []);

  // Inbox delivery must not wait for a checklist save or the full workspace
  // snapshot. Both subscriptions share one authenticated streaming connection.
  useLiveUpdates({
    domains: ["notifications", "tasks", "messages"],
    refreshAuth: refreshPortalSession,
    safetyRefreshMs: 3000,
    onChange: loadStaffNotifications,
  });

  const liveStatus = useLiveUpdates({
    domains: ["accounts", "staff", "tasks", "notifications", "messages"],
    refreshAuth: refreshPortalSession,
    safetyRefreshMs: 5000,
    onChange: async () => {
      if (taskUpdateLock.current) return;
      if (document.visibilityState !== "hidden") await loadStaffData({ silent: true });
    },
  });
  React.useEffect(() => {
    const initialLoad = window.setTimeout(() => loadStaffData(), 0);
    return () => window.clearTimeout(initialLoad);
  }, [loadStaffData]);


  React.useEffect(() => {
    if (dataLoading || !currentStaff.id || linkedTaskOpened.current) return;
    const linkedId = new URLSearchParams(window.location.search).get("task");
    if (!linkedId) return;
    linkedTaskOpened.current = true;
    const linkedTask = tasks.find(task => task.id === linkedId);
    if (linkedTask) {
      const villaId = needsAvailabilityResponse(linkedTask)
        ? linkedTask.maintenanceOnCall?.villaId
        : null;
      if (villaId) { setVillaFocus(villaId); setView('villas'); }
      else { setSelectedTaskId(linkedId); setTaskModalOpen(true); }
    } else showToast("This assignment is no longer available in your account.");
  }, [dataLoading, currentStaff.id, tasks, showToast]);

  function navigate(nextView, preset = {tab:"My work",focus:"All work"}) {
    if (nextView === 'villas') setVillaFocus('');
    if (["todo","inProgress","review"].includes(nextView)) setTaskBoardPreset(preset);
    setView(nextView);
  }

async function commitTaskUpdate(
    taskId,
    patch,
    activityTitle,
    activityMessage
  ) {
    if (taskUpdateLock.current) throw new Error("An update is already saving. Please wait.");
    taskUpdateLock.current = true;
    setTaskSavingId(taskId);
    try {
      const payload = await staffApiRequest(
        `/staff/tasks/${encodeURIComponent(taskId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ ...patch, expectedUpdatedAt: allTasks.find(task => task.id === taskId)?.updatedAt || allTasks.find(task => task.id === taskId)?.updated_at || null }),
        }
      );
      const updatedTask = normalizeTask(payload?.data || {});
      if (!updatedTask.id) {
        throw new Error("The updated task was not returned.");
      }

      setAllTasks((current) =>
        current.map((task) =>
          task.id === taskId ? {...task, ...updatedTask,
            assignedBy: payload?.data?.assignedBy || task.assignedBy,
            assignedByAvatarUrl: payload?.data?.assignedByAvatarUrl ?? task.assignedByAvatarUrl,
            assignedByNickname: payload?.data?.assignedByNickname ?? task.assignedByNickname,
          } : task
        )
      );
      if (activityTitle) {
        showToast(activityMessage || activityTitle);
      }
      return updatedTask;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "The task could not be updated.";
      showToast(message);
      throw error;
    } finally {
      taskUpdateLock.current = false;
      setTaskSavingId("");
      loadStaffData({ silent: true });
    }
  }

  function openTask(taskId, snapshot = tasks) {
    const task = snapshot.find(item => item.id === taskId);
    const villaId = task && needsAvailabilityResponse(task)
      ? task.maintenanceOnCall?.villaId
      : null;
    if (villaId) { setVillaFocus(villaId); setView('villas'); setTaskModalOpen(false); return; }
    setSelectedTaskId(taskId);
    setTaskModalOpen(true);
  }

  async function openNotificationTask(taskId) {
    if (tasks.some(task => task.id === taskId)) { openTask(taskId); return; }
    // The lightweight inbox can arrive before the workspace snapshot.
    try {
      const payload = await staffApiRequest("/staff/tasks");
      const latest = Array.isArray(payload?.data) ? payload.data : [];
      setAllTasks(latest);
      if (latest.some(task => task.id === taskId)) openTask(taskId, latest);
      else showToast("This assignment is no longer available in your account.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Unable to open this assignment.");
    }
  }

async function signOut() {
    if (signingOutLock.current) return;
    signingOutLock.current = true;
    setSigningOut(true);
    try {
      await staffApiRequest("/staff/session", { method: "DELETE" });
    } catch {
      // Clear browser credentials even when the backend is unavailable.
    }

    [
      "theVillaPortalAuth",
      "theVillaAdminAuth",
      "theVillaStaffAuth",
      "theVillaAuthToken",
      "theVillaRefreshToken",
      "theVillaApiToken",
      "theVillaCurrentStaff",
    ].forEach((key) => {
      localStorage.removeItem(
        key
      );

      sessionStorage.removeItem(
        key
      );
    });

    window.location.replace("/admin-login");
  }

  const stats = React.useMemo(() => {
    return {
      todo: workspaceTasks.filter((task) => task.status === "Pending" && !isLate(task)).length,
      inProgress: workspaceTasks.filter((task) => task.status === "In Progress" && !isLate(task)).length,
      review: workspaceTasks.filter((task) => task.status === "Pending Review").length,
    };
  }, [workspaceTasks]);

  function renderTasks() {
    return <StaffTaskBoard key={`${taskBoardPreset.tab}-${taskBoardPreset.focus}-${taskBoardPreset.dueDate || ""}`} initialView={taskBoardPreset.tab} initialFocus={taskBoardPreset.focus} initialDueDate={taskBoardPreset.dueDate || ""} tasks={workspaceTasks} openTask={openTask} />;
  }

  function renderHistory() {
    const history = workspaceTasks
      .filter((task) => isMaintenanceStaff
        ? task.status === "Completed"
        : ["Completed", "Cancelled"].includes(task.status) || isLate(task))
      .sort((a, b) => String(b.updatedAt || b.dueDate || "").localeCompare(String(a.updatedAt || a.dueDate || "")));
    return (
      <div className="staff-page staff-page-history">
        <section className="staff-history-table-wrap">
          <table className="staff-history-table">
            <thead>
              <tr>
                <th>Assignment</th>
                <th>Booking</th>
                <th>Due Date</th>
                <th>Completed at</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {history.map((task) => (
                <tr key={task.id} onClick={() => openTask(task.id)}>
                  <td>
                    <strong className="staff-history-title">{task.title}</strong>
                    <small>{task.villaName} · {task.guestName}</small>
                  </td>
                  <td>{task.bookingCode || task.bookingId || "—"}</td>
                  <td>{formatDate(task.dueDate)}</td>
                  <td>{task.status === "Completed" ? formatDateTime(task.completedAt || task.updatedAt) : "—"}</td>
                  <td><StatusPill status={task.status === "Completed" ? "Completed" : task.status === "Cancelled" ? "Cancelled" : "Overdue"} /></td>
                </tr>
              ))}
              {!history.length && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      icon={History}
                      title={isMaintenanceStaff ? "No completed maintenance yet" : "No task history yet"}
                      message={isMaintenanceStaff ? "Verified maintenance work will appear here." : "Approved, cancelled and overdue assignments appear here. Ask your administrator to review missed preparation deadlines."}
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      </div>
    );
  }

  function openProfileEditor() {
    setProfileForm({ personalEmail: currentStaff.personalEmail || "", name: currentStaff.name, nickname: currentStaff.nickname || "", avatarUrl: currentStaff.avatarUrl || currentStaff.avatar_url || "" });
    setProfileError("");
    setProfileOpen(true);
  }

  async function chooseProfilePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setProfileError("Choose a JPG, PNG, or WebP image smaller than 5 MB."); return;
    }
    const url = URL.createObjectURL(file);
    try {
      const image = new Image(); image.src = url; await image.decode();
      const canvas = document.createElement("canvas"); canvas.width = canvas.height = 256;
      const size = Math.min(image.width, image.height);
      canvas.getContext("2d").drawImage(image, (image.width-size)/2, (image.height-size)/2, size, size, 0, 0, 256, 256);
      setProfileForm((current) => ({ ...current, avatarUrl: canvas.toDataURL("image/jpeg", .85) }));
      setProfileError("");
    } catch { setProfileError("This image could not be opened. Please choose another picture."); }
    finally { URL.revokeObjectURL(url); }
  }

  async function saveProfile(event) {
    event.preventDefault();
    setProfileSaving(true); setProfileError("");
    try {
      const result = await staffApiRequest("/staff/profile", { method: "PATCH", body: JSON.stringify({ fullName: profileForm.name.trim(), personalEmail: profileForm.personalEmail.trim(), nickname: profileForm.nickname.trim(), avatarUrl: profileForm.avatarUrl }) });
      if (!result?.data?.id) throw new Error("Your profile could not be saved.");
      setCurrentStaff(normalizeStaffAccount(result.data)); syncPortalProfile(result.data);
      setProfileOpen(false); showToast("Your profile has been updated.");
    } catch (error) { setProfileError(error instanceof Error ? error.message : "Unable to save your profile."); }
    finally { setProfileSaving(false); }
  }

  function renderProfile() {
    return <section className="work-account"><div className="work-account-identity"><Avatar name={currentStaff.name} online={currentStaff.online} size={64} src={currentStaff.avatarUrl || currentStaff.avatar_url}/><div><h2>{currentStaff.name}</h2><p>{currentStaff.role} · {currentStaff.department}</p></div><StatusPill status={currentStaff.accountStatus}/></div><dl>{[["Username",currentStaff.username],["Shift",currentStaff.shift],["Personal email",currentStaff.personalEmail],["Department",currentStaff.department],["Last sign-in",formatDateTime(currentStaff.lastLogin)]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value || "Not provided"}</dd></div>)}</dl></section>;
  }

  function renderCurrentView() {
    switch (view) {
      case "villas": return <StaffVillaOperations key={villaFocus || 'villas'} apiRequest={staffApiRequest} initialVillaId={villaFocus} onChanged={() => loadStaffData({ silent: true })} />;
      case "overview": return <StaffOverview tasks={tasks} name={currentStaff.name} shift={currentStaff.shift} openTask={openTask} viewCalendar={()=>navigate("calendar")} viewHistory={()=>navigate("history")} viewTasks={(tab,focus)=>navigate(tab==='In review'?'review':'todo',{tab,focus})} />;
      case "todo":
      case "inProgress":
      case "review": return renderTasks();
      case "history": return renderHistory();
      case "calendar": return <StaffSchedule tasks={workspaceTasks} shift={currentStaff.shift} openTask={openTask} onViewTodos={(dueDate)=>navigate("todo",{tab:"Schedule",focus:"All work",dueDate})} />;
      case "profile": return renderProfile();
      default: return renderTasks();
    }
  }

  if (!currentStaff || currentStaff.accountStatus === "Disabled") {
    return (
      <main className="staff-access-lock">
        <section>
          <span><LockKeyhole size={34} /></span>
          <small>The Villa Staff Account</small>
          <h1>Account access is disabled</h1>
          <p>
            This staff account was disabled from the Admin Dashboard. Contact the administrator before trying to access assignments or task updates.
          </p>
          <dl>
            <div><dt>Staff</dt><dd>{currentStaff?.name || "Unknown account"}</dd></div>
            <div><dt>Staff ID</dt><dd>{currentStaff?.id || "Not available"}</dd></div>
            <div><dt>Status</dt><dd>Disabled</dd></div>
          </dl>
          <button type="button" onClick={()=>setSignOutConfirmOpen(true)}><LogOut size={16} /> Return to Sign In</button><ConfirmSignOut open={signOutConfirmOpen} busy={signingOut} cancel={()=>setSignOutConfirmOpen(false)} confirm={signOut}/>
        </section>
      </main>
    );
  }

  const shellClass = [
    "staff-dashboard-shell",
  ].filter(Boolean).join(" ");

  return (
    <div className={shellClass} data-live-status={liveStatus}>
      <aside className="staff-sidebar">
        <div className="staff-sidebar-inner">
          <header className="staff-sidebar-brand">
            <span className="staff-brand-logo"><img src="/favicon.png" alt="The Villa logo" /></span>
            <strong className="staff-brand-name">The Villa - Staff</strong>
          </header>

          <nav className="staff-sidebar-nav">
            <button type="button" className={`staff-sidebar-profile-card staff-nav-profile${view === "profile" ? " active" : ""}`} onClick={openProfileEditor} title="My profile">
              <Avatar name={currentStaff.name} size={80} src={currentStaff.avatarUrl || currentStaff.avatar_url} />
              <span className="staff-sidebar-profile-copy">
                <strong>{currentStaff.name}{currentStaff.nickname?.trim() && <> <span className="staff-profile-nickname">({currentStaff.nickname.trim()})</span></>}</strong>
                <small>{currentStaff.role}</small>
              </span>
            </button>
            {sidebarItems.map((item) => {
              const Icon = item.icon;
              const badge = item.count ? stats[item.count] : 0;
              return (
                <button
                  type="button"
                  key={item.id}
                  className={`staff-sidebar-nav-btn${view === item.id ? " active" : ""}`}
                  onClick={() => navigate(item.id, item.preset)}
                >
                  <Icon size={18} />
                  <span className="staff-nav-label">{item.label}</span>
                  {badge > 0 && <b className="staff-nav-badge">{badge}</b>}
                </button>
              );
            })}
          </nav>

          <footer className="staff-sidebar-footer">
            <button type="button" className="staff-logout-btn" onClick={()=>setSignOutConfirmOpen(true)}>
              <LogOut size={17} />
              <span className="staff-nav-label">Sign Out</span>
            </button>
          </footer>
        </div>
      </aside>

      <main className="staff-main-area">
        <section className="staff-page-content">
          <div className="staff-workspace-heading"><div className="staff-compact-page-heading"><span>{isMaintenanceStaff ? "Maintenance" : "My workspace"}</span><h1>{sidebarItems.find(item => item.id === view)?.label || "My Profile"}</h1></div>
            <StaffNotifications key={currentStaff.id} staffId={currentStaff.id} notifications={staffNotifications} setNotifications={setStaffNotifications} popupsEnabled={notificationPopupsEnabled} apiRequest={staffApiRequest} openTask={openNotificationTask} refresh={() => loadStaffData({ silent: true })} />
          </div>
          {dataLoading && <LoadingScreen message="Loading your staff workspace…"/>}
          {dataError && <div className="grid gap-3"><AlertMessage message={dataError}/><button className="staff-btn-ghost" onClick={()=>loadStaffData()}>Retry</button></div>}
          {renderCurrentView()}
        </section>
      </main>

      {taskModalOpen && selectedTask && <StaffTaskWorkspace key={selectedTask.id} task={selectedTask} busy={!!taskSavingId} update={commitTaskUpdate} close={() => setTaskModalOpen(false)} />}

      <dialog ref={profileDialog} className="staff-profile-dialog" aria-labelledby="staff-profile-title" onCancel={(event) => { if (profileSaving) event.preventDefault(); else setProfileOpen(false); }}>
        <header><span>My account</span><h2 id="staff-profile-title">Edit profile</h2></header>
        <form onSubmit={saveProfile}>
          <fieldset disabled={profileSaving}>
            <div className="staff-profile-photo-editor">
              <Avatar name={profileForm.name} size={80} src={profileForm.avatarUrl} />
              <label className="staff-profile-photo-picker">Change photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseProfilePhoto} /></label>
              {profileForm.avatarUrl && <button type="button" onClick={() => setProfileForm((current) => ({...current, avatarUrl: ""}))}>Remove photo</button>}
            </div>
            <label>Full name<input required minLength={3} maxLength={120} value={profileForm.name} onChange={(event) => setProfileForm((current) => ({...current, name: event.target.value}))} /></label>
            <label>Role<input readOnly value={currentStaff.role} /></label>
            <label>Personal email<input required type="email" autoComplete="email" maxLength={254} value={profileForm.personalEmail} onChange={event => setProfileForm(current => ({...current, personalEmail: event.target.value}))} /></label>
            <label>Nickname<input maxLength={80} value={profileForm.nickname} onChange={(event) => setProfileForm((current) => ({...current, nickname: event.target.value}))} /></label>
          </fieldset>
          {profileError && <p className="staff-profile-error" role="alert">{formatUserFacingMessage(profileError)}</p>}
          <footer><button type="button" disabled={profileSaving} onClick={() => setProfileOpen(false)}>Cancel</button><button type="submit" disabled={profileSaving}>{profileSaving ? "Saving…" : "Save changes"}</button></footer>
        </form>
      </dialog>

      <ConfirmSignOut open={signOutConfirmOpen} busy={signingOut} cancel={()=>setSignOutConfirmOpen(false)} confirm={signOut}/>
      {toast && <div className="fixed bottom-4 left-4 right-4 z-[25000] mx-auto max-w-lg"><AlertMessage message={toast} type={/unable|cannot|could not|failed|error|not available|already|no longer|please wait/i.test(toast) ? 'error' : 'success'} dismiss={()=>setToast("")}/></div>}


    </div>
  );
}
