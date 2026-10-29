import React from "react";
import { Navigate, useLocation } from "react-router-dom";

const PORTAL_AUTH_KEY = "theVillaPortalAuth";
const VALID_ROLES = new Set(["admin", "staff"]);

function safeParse(value) {
  if (!value) return null;

  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function normalizeRole(value) {
  const role = String(value || "").trim().toLowerCase();

  if (role === "administrator") return "admin";
  if (role === "employee") return "staff";

  return VALID_ROLES.has(role) ? role : "";
}

function readPortalSession() {
  const values = [
    sessionStorage.getItem(PORTAL_AUTH_KEY),
    localStorage.getItem(PORTAL_AUTH_KEY),
  ];

  for (const raw of values) {
    const auth = safeParse(raw);
    if (!auth) continue;

    const accessToken = String(
      auth.access_token || auth.accessToken || auth.token || ""
    ).trim();

    const refreshToken = String(
      auth.refresh_token || auth.refreshToken || ""
    ).trim();

    const role = normalizeRole(
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

function portalHome(role) {
  return role === "admin" ? "/admin-dashboard" : "/staff";
}

function ProtectedRoute({ children, allowedRoles = [] }) {
  const location = useLocation();
  const session = readPortalSession();
  const normalizedRoles = allowedRoles
    .map(normalizeRole)
    .filter(Boolean);

  if (!session) {
    return <Navigate to="/admin-login" state={{ from: { pathname: location.pathname, search: location.search } }} replace />;
  }

  if (
    normalizedRoles.length > 0 &&
    !normalizedRoles.includes(session.role)
  ) {
    return <Navigate to={portalHome(session.role)} replace />;
  }

  return children;
}

export default ProtectedRoute;