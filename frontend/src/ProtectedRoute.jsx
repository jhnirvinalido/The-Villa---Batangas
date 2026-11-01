import { useEffect, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { LoadingScreen } from "./SystemFeedback";
import { LEGACY_FRONT_DESK_SESSION_KEY, normalizePortalRole, portalHome, sessionWithCurrentRole } from "./portalRouting.mjs";
import "./ProtectedRoute.css";

const PORTAL_AUTH_KEY = "theVillaPortalAuth";
const API_URL = ((typeof window !== "undefined" && window.__THE_VILLA_API_BASE__) || import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function safeParse(value) {
  if (!value) return null;

  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function readPortalSession(sessionKey) {
  const values = [
    sessionStorage.getItem(sessionKey),
    localStorage.getItem(sessionKey),
  ];
  if (!values.some(Boolean)) {
    const previous = sessionStorage.getItem(LEGACY_FRONT_DESK_SESSION_KEY) || localStorage.getItem(LEGACY_FRONT_DESK_SESSION_KEY);
    if (previous) {
      values.push(previous);
      sessionStorage.setItem(sessionKey, previous);
      sessionStorage.removeItem(LEGACY_FRONT_DESK_SESSION_KEY);
      localStorage.removeItem(LEGACY_FRONT_DESK_SESSION_KEY);
    }
  }

  for (const raw of values) {
    const auth = safeParse(raw);
    if (!auth) continue;

    const accessToken = String(
      auth.access_token || auth.accessToken || auth.token || ""
    ).trim();

    const refreshToken = String(
      auth.refresh_token || auth.refreshToken || ""
    ).trim();

    const role = normalizePortalRole(
      auth.portalRole ||
        auth.role ||
        auth.user?.portalRole ||
        auth.user?.role
    );

    if (
      auth.authenticated === true &&
      accessToken &&
      refreshToken &&
      role
    ) {
      return {
        ...auth,
        role,
        access_token: accessToken,
        refresh_token: refreshToken,
      };
    }
  }

  return null;
}

function CheckCurrentRole({ session, sessionKey, allowedRoles, children }) {
  const location = useLocation();
  const [result, setResult] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function checkRole() {
      try {
        const response = await fetch(`${API_URL}/staff-auth/me`, {
          headers: { Accept: "application/json", Authorization: `Bearer ${session.access_token}` },
          signal: controller.signal,
        });
        if (!response.ok) {
          if (!controller.signal.aborted) setResult({ error: true, expired: response.status === 401 });
          return;
        }
        const payload = await response.json();
        const current = sessionWithCurrentRole(session, payload.user);
        if (controller.signal.aborted) return;
        if (!current) {
          setResult({ error: true });
          return;
        }
        const storage = sessionStorage.getItem(sessionKey) ? sessionStorage : localStorage;
        storage.setItem(sessionKey, JSON.stringify(current));
        setResult({ session: current });
      } catch (error) {
        if (error.name !== "AbortError") setResult({ error: true });
      }
    }
    checkRole();
    return () => controller.abort();
  }, [session, sessionKey, attempt]);

  if (!result) return <LoadingScreen message="Checking your workspace access…" />;
  if (result.session && allowedRoles.includes(result.session.role)) return children;
  return <main className="portal-access-screen">
    <section>
      <img src="/favicon.png" alt="The Villa" />
      <span>Management portal</span>
      <h1>{result.error ? "We couldn't verify your access" : "This workspace needs a different role"}</h1>
      <p>{result.error
        ? result.expired ? "Your session has expired. Sign in again to open this workspace." : "Please retry when the server is available."
        : `Your account opens the ${({ admin: 'Admin', staff: 'Staff', front_desk: 'Front Desk / Operations', maintenance: 'Maintenance' })[result.session.role]} workspace. Use My workspace to continue, or ask Admin to review your assigned role.`}</p>
      <div>
        {result.error && !result.expired && <button type="button" onClick={() => { setResult(null); setAttempt(value => value + 1); }}>Retry</button>}
        {!result.error && <Link to={portalHome(result.session.role)}>My workspace</Link>}
        <Link to="/login" state={{ from: { pathname: location.pathname, search: location.search } }}>Sign in{result.error ? " again" : " with another account"}</Link>
      </div>
    </section>
  </main>;
}

function ProtectedRoute({ children, allowedRoles = [] }) {
  const location = useLocation();
  const sessionKey = PORTAL_AUTH_KEY;
  const session = readPortalSession(sessionKey);
  const normalizedRoles = allowedRoles
    .map(normalizePortalRole)
    .filter(Boolean);

  if (!session) {
    return <Navigate to="/login" state={{ from: { pathname: location.pathname, search: location.search } }} replace />;
  }
  if (session.role === 'maintenance' && location.pathname === '/staff') return <Navigate to={`/maintenance${location.search}`} replace />;

  if (
    normalizedRoles.length > 0 &&
    !normalizedRoles.includes(session.role)
  ) {
    return <CheckCurrentRole session={session} sessionKey={sessionKey} allowedRoles={normalizedRoles}>{children}</CheckCurrentRole>;
  }

  return children;
}

export default ProtectedRoute;
