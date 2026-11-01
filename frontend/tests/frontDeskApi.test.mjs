import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createDeskQr, deskApi, deskSession, refreshDeskSession, signOutDesk } from '../src/frontDeskApi.mjs';
import { PORTAL_SESSION_KEY } from '../src/portalRouting.mjs';

const originalFetch = globalThis.fetch;
const store = () => {
  const values = new Map();
  return { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
};
function session() {
  globalThis.sessionStorage = store(); globalThis.localStorage = store();
  sessionStorage.setItem(PORTAL_SESSION_KEY, JSON.stringify({ access_token: 'old-token', refresh_token: 'refresh-token', role: 'front_desk', portalRole: 'front_desk', user: { role: 'front_desk' } }));
}
const response = (payload, status = 200) => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => { globalThis.fetch = originalFetch; });

test('Front Desk retries an expired token with the refreshed dedicated-role session', async () => {
  session();
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (url.endsWith('/staff-auth/refresh')) return response({ access_token: 'fresh-token', refresh_token: 'rotated-refresh', user: { role: 'front_desk' } });
    return options.headers.Authorization === 'Bearer fresh-token' ? response({ data: { bookings: [] } }) : response({ detail: 'Expired' }, 401);
  };
  assert.deepEqual(await deskApi('/front-desk/bootstrap'), { data: { bookings: [] } });
  assert.equal(requests.length, 3);
  assert.equal(requests[2].options.headers.Authorization, 'Bearer fresh-token');
  const saved = JSON.parse(sessionStorage.getItem(PORTAL_SESSION_KEY));
  assert.equal(saved.portalRole, 'front_desk');
  assert.equal(saved.refresh_token, 'rotated-refresh');
});

test('a QRPh attachment failure keeps the pending intent reference for verification', async () => {
  session();
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    if (url.includes('/qrph-intent')) return response({ data: { payment_intent_id: 'intent-1', public_key: 'public-test-key' } });
    return response({ errors: [{ detail: 'QRPh temporarily unavailable' }] }, 503);
  };
  await assert.rejects(createDeskQr({ id: 'booking-1' }, { payerName: 'Ana Guest', timing: 'check_in', charges: [] }), error => error.paymentIntentId === 'intent-1');
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[0].options.body).payment_timing, 'check_in');
  assert.ok(!requests.some(request => request.url.includes('/cash-settlement')));
});

test('sign-out removes the local session even when the server cannot be reached', async () => {
  session();
  globalThis.fetch = async () => { throw new Error('Offline'); };
  await assert.rejects(signOutDesk());
  assert.equal(sessionStorage.getItem(PORTAL_SESSION_KEY), null);
});

test('an Admin account session cannot substitute for a Front Desk account', () => {
  session();
  sessionStorage.setItem(PORTAL_SESSION_KEY, JSON.stringify({ access_token: 'admin-token', role: 'admin' }));
  assert.deepEqual(deskSession().value, {});
});

test('refresh cannot replace a Front Desk session with an Admin session', async () => {
  session();
  globalThis.fetch = async () => response({ access_token: 'different-account', refresh_token: 'rotated', user: { role: 'admin' } });
  await assert.rejects(refreshDeskSession(), /Front Desk/);
  assert.equal(JSON.parse(sessionStorage.getItem(PORTAL_SESSION_KEY)).access_token, 'old-token');
});
