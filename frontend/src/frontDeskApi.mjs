import { getApiErrorMessage } from './errorMessages.mjs';
import { LEGACY_FRONT_DESK_SESSION_KEY, PORTAL_SESSION_KEY, sessionWithCurrentRole } from './portalRouting.mjs';

const key = PORTAL_SESSION_KEY;
const base = ((typeof window !== 'undefined' && window.__THE_VILLA_API_BASE__) || import.meta.env?.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
let refreshing;

export function deskSession() {
  for (const storage of [sessionStorage, localStorage]) {
    try { const value = JSON.parse(storage.getItem(key)); if (value?.access_token && (value.portalRole || value.role || value.user?.role) === 'front_desk') return { value, storage }; } catch { /* Try the other Front Desk store. */ }
  }
  return { value: {}, storage: sessionStorage };
}

export async function refreshDeskSession() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const { value, storage } = deskSession();
    if (!value.refresh_token) throw new Error('Your session has expired. Sign in again.');
    const response = await fetch(`${base}/staff-auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: value.refresh_token }) });
    const payload = await response.json();
    if (!response.ok || !payload.access_token || !payload.refresh_token) throw new Error('Your session has expired. Sign in again.');
    const next = sessionWithCurrentRole({ ...value, ...payload }, payload.user);
    if (!next || next.role !== 'front_desk') throw new Error('Sign in with your Front Desk / Operations account.');
    storage.setItem(key, JSON.stringify(next));
    return next;
  })();
  try { return await refreshing; } finally { refreshing = null; }
}

export async function deskApi(path, options = {}) {
  const request = () => fetch(`${base}${path}`, { ...options, headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), Authorization: `Bearer ${deskSession().value.access_token || ''}`, ...options.headers } });
  let response = await request();
  if (response.status === 401) { await refreshDeskSession(); response = await request(); }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
  return payload;
}

export async function signOutDesk() {
  try { await deskApi('/front-desk/session', { method: 'DELETE' }); }
  finally {
    for (const storage of [sessionStorage, localStorage]) {
      storage.removeItem(key);
      storage.removeItem(LEGACY_FRONT_DESK_SESSION_KEY);
    }
  }
}

export async function createDeskQr(booking, { payerName, timing, charges }) {
  const result = await deskApi(`/front-desk/bookings/${encodeURIComponent(booking.id)}/qrph-intent`, { method: 'POST', body: JSON.stringify({ payer_name: payerName, payment_timing: timing, other_charges: charges }) });
  const session = result.data;
  try {
    const headers = { Accept: 'application/json', 'Content-Type': 'application/json', Authorization: `Basic ${btoa(`${session.public_key}:`)}` };
    const post = async (path, body) => {
      const response = await fetch(`https://api.paymongo.com/v1/${path}`, { method: 'POST', headers, body: JSON.stringify(body) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.errors?.[0]?.detail || 'The QRPh payment could not be created.');
      return payload.data.attributes;
    };
    const methodResponse = await fetch('https://api.paymongo.com/v1/payment_methods', { method: 'POST', headers, body: JSON.stringify({ data: { attributes: { type: 'qrph', expiry_seconds: 1800 } } }) });
    const method = await methodResponse.json();
    if (!methodResponse.ok) throw new Error(method.errors?.[0]?.detail || 'QRPh is unavailable.');
    const attached = await post(`payment_intents/${encodeURIComponent(session.payment_intent_id)}/attach`, { data: { attributes: { payment_method: method.data.id, client_key: session.client_key } } });
    const image = attached.next_action?.code?.image_url;
    if (!image && attached.status !== 'succeeded') throw new Error('No QRPh code was returned. Retry the payment status before creating another payment.');
    return { id: session.payment_intent_id, image, status: attached.status };
  } catch (error) {
    error.paymentIntentId = session.payment_intent_id;
    throw error;
  }
}
