const roles = new Set(['admin', 'staff', 'front_desk', 'maintenance']);
export const PORTAL_SESSION_KEY = 'theVillaPortalAuth';
export const LEGACY_FRONT_DESK_SESSION_KEY = 'theVillaFrontDeskAuth';

export function normalizePortalRole(value) {
  const role = String(value || '').trim().toLowerCase();
  if (role === 'administrator') return 'admin';
  if (role === 'employee') return 'staff';
  return roles.has(role) ? role : '';
}

export function portalHome(role) {
  if (role === 'admin') return '/admin-dashboard';
  if (role === 'front_desk') return '/front-desk';
  if (role === 'maintenance') return '/maintenance';
  return '/staff';
}

export function portalLoginDestination(role, from) {
  const pathname = typeof from === 'string' ? from.split(/[?#]/)[0] : from?.pathname || '';
  const inRoute = route => pathname === route || pathname.startsWith(`${route}/`);
  const allowed = role === 'admin'
    ? inRoute('/admin-dashboard')
    : role === 'front_desk' ? inRoute('/front-desk')
      : role === 'maintenance' ? inRoute('/maintenance') : inRoute('/staff');
  if (role === 'maintenance' && inRoute('/staff')) {
    const query = new URLSearchParams(typeof from === 'string' ? from.split('?')[1]?.split('#')[0] : from?.search);
    const task = query.get('task');
    return task && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(task) ? `/maintenance?${new URLSearchParams({ task })}` : '/maintenance';
  }
  if (!allowed) return portalHome(role);
  return typeof from === 'string' ? from : `${pathname}${from.search || ''}${from.hash || ''}`;
}

// Update every stored role field together after the server confirms a role change.
export function sessionWithCurrentRole(session, user) {
  const role = normalizePortalRole(user?.role || user?.portalRole);
  if (!role) return null;
  return { ...session, role, portalRole: role, user: { ...session.user, ...user, role, portalRole: role } };
}

export function frontDeskSection(location) {
  const sections = new Set(['bookings', 'walkIns', 'newWalkIn', 'lifecycle', 'payments', 'receipts', 'staff']);
  const section = new URLSearchParams(location.search).get('section') || location.pathname?.split('/').filter(Boolean)[1];
  return sections.has(section) ? section : 'bookings';
}
