import test from 'node:test';
import assert from 'node:assert/strict';
import { clearPortalSession, portalHome, portalLoginDestination, sessionWithCurrentRole, frontDeskSection } from '../src/portalRouting.mjs';

test('each account signs in to its own workspace', () => {
  for (const [role, path] of [['admin', '/admin-dashboard'], ['front_desk', '/front-desk'], ['staff', '/staff'], ['maintenance', '/maintenance']]) {
    assert.equal(portalLoginDestination(role), path);
    assert.equal(portalHome(role), path);
  }
  assert.equal(portalLoginDestination('admin', { pathname: '/front-desk', search: '?section=staff' }), '/admin-dashboard');
  assert.equal(portalLoginDestination('front_desk', { pathname: '/front-desk', search: '?section=staff' }), '/front-desk?section=staff');
  assert.equal(portalLoginDestination('front_desk', { pathname: '/front-desk/bookings' }), '/front-desk/bookings');
});

test('sign-in respects role boundaries and rejects external or lookalike destinations', () => {
  assert.equal(portalLoginDestination('front_desk', '/admin-dashboard'), '/front-desk');
  assert.equal(portalLoginDestination('staff', '/front-desk'), '/staff');
  assert.equal(portalLoginDestination('admin', '//example.com/front-desk'), '/admin-dashboard');
  assert.equal(portalLoginDestination('admin', '/front-desk-elsewhere'), '/admin-dashboard');
  assert.equal(portalLoginDestination('maintenance', '/front-desk'), '/maintenance');
  assert.equal(portalLoginDestination('staff', '/maintenance'), '/staff');
});

test('maintenance assignment links retain their task when opened from the shared login', () => {
  const task = '00000000-0000-0000-0000-000000000001';
  assert.equal(portalLoginDestination('maintenance', { pathname: '/staff', search: `?task=${task}` }), `/maintenance?task=${task}`);
});

test('a server-confirmed role change replaces every stale role field and keeps the tokens', () => {
  const session = { role: 'staff', portalRole: 'staff', user: { role: 'staff', portalRole: 'staff', name: 'Alex' }, access_token: 'access', refresh_token: 'refresh' };
  const updated = sessionWithCurrentRole(session, { role: 'front_desk' });
  assert.equal(updated.role, 'front_desk');
  assert.equal(updated.portalRole, 'front_desk');
  assert.equal(updated.user.portalRole, 'front_desk');
  assert.equal(updated.user.role, 'front_desk');
  assert.equal(updated.user.name, 'Alex');
  assert.equal(updated.access_token, 'access');
  assert.equal(updated.refresh_token, 'refresh');
  assert.equal(sessionWithCurrentRole(session, { role: 'guest' }), null);
});

test('refresh and browser history retain a valid Front Desk section', () => {
  assert.equal(frontDeskSection({ pathname: '/front-desk', search: '?section=payments' }), 'payments');
  assert.equal(frontDeskSection({ pathname: '/front-desk/staff', search: '' }), 'staff');
  assert.equal(frontDeskSection({ pathname: '/front-desk/receipts', search: '' }), 'receipts');
  assert.equal(frontDeskSection({ pathname: '/front-desk', search: '?section=receipts' }), 'receipts');
  assert.equal(frontDeskSection({ pathname: '/front-desk', search: '?section=unknown' }), 'bookings');
});

test('history-navigation sign-out removes current and legacy portal credentials from every storage', () => {
  const keys = ['theVillaPortalAuth', 'theVillaFrontDeskAuth', 'theVillaAdminAuth', 'theVillaStaffAuth', 'theVillaAuthToken', 'theVillaApiToken', 'theVillaRefreshToken'];
  const createStorage = () => {
    const values = new Map([...keys, 'remembered-email'].map(key => [key, 'value']));
    return {
      values,
      removeItem(key) { values.delete(key); },
    };
  };
  const sessionStorage = createStorage();
  const localStorage = createStorage();
  clearPortalSession([sessionStorage, localStorage]);
  for (const storage of [sessionStorage, localStorage]) {
    for (const key of keys) assert.equal(storage.values.has(key), false);
    assert.equal(storage.values.get('remembered-email'), 'value');
  }
});
