import test from 'node:test';
import assert from 'node:assert/strict';
import { newUnreadNotifications, staffLoginReturnPath, staffNotificationTime } from '../src/staffNotificationFeed.mjs';

test('login catch-up returns newest unread notifications and excludes read items', () => {
  const notices = [{id:'old',unread:true,timestamp:'2026-10-24T00:00:00Z'},
    {id:'read',unread:false}, {id:'new',unread:true,timestamp:'2026-10-25T00:00:00Z'}];
  assert.deepEqual(newUnreadNotifications(notices,new Set()).map(n=>n.id), ['new','old']);
});
test('seen IDs do not trigger repeated popups after polling or reopening the tab', () => {
  const notices = [{id:'a',unread:true},{id:'b',unread:true}];
  assert.deepEqual(newUnreadNotifications(notices,new Set(['a'])).map(n=>n.id), ['b']);
  assert.deepEqual(newUnreadNotifications(notices,new Set(['a','b'])), []);
});
test('malformed or duplicate records never inflate the alert feed', () => {
  assert.deepEqual(newUnreadNotifications([null,{}, {id:'a',unread:true},{id:'a',unread:true},{id:'b',unread:false}],new Set()).map(n=>n.id), ['a']);
});
test('timestamps are shown in Manila time and missing dates fail gracefully', () => {
  assert.match(staffNotificationTime('2026-10-25T00:00:00Z'), /8:00/);
  assert.equal(staffNotificationTime('not-a-date'), 'Recently');
});
test('assignment email link survives login without permitting arbitrary redirects', () => {
  const task='11111111-1111-4111-8111-111111111111';
  assert.equal(staffLoginReturnPath({pathname:'/staff',search:`?task=${task}`}),`/staff?task=${task}`);
  assert.equal(staffLoginReturnPath({pathname:'https://evil.example',search:`?task=${task}`}),'/staff');
  assert.equal(staffLoginReturnPath({pathname:'//evil.example'}),'/staff');
  assert.equal(staffLoginReturnPath({pathname:'/staff',search:'?task=javascript:alert(1)'}),'/staff');
  assert.equal(staffLoginReturnPath(null),'/staff');
});
