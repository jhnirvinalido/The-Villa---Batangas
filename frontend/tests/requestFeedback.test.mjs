import test from 'node:test';
import assert from 'node:assert/strict';
import { activeRequests, feedbackFetch, tracksAction } from '../src/requestFeedback.mjs';

test('background live reads and reconciliation never show action loading', () => {
  assert.equal(tracksAction('/staff/bootstrap'), false);
  assert.equal(tracksAction('/live/portal'), false);
  assert.equal(tracksAction('/bookings/b1/sync-payment', {method:'POST'}), false);
  assert.equal(tracksAction('/staff-auth/refresh', {method:'POST'}), false);
  assert.equal(tracksAction('/staff-auth/login', {method:'POST'}), false);
  assert.equal(tracksAction('/staff-auth/forgot-password', {method:'POST'}), false);
  assert.equal(tracksAction('/staff/session', {method:'DELETE'}), false);
  assert.equal(tracksAction('/staff/tasks/task1', {method:'PATCH'}), true);
  assert.equal(tracksAction('/public-bookings', {method:'POST'}), true);
});

test('sign-in and password recovery never trigger global action loading', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('{}', {status:401});
  try {
    await feedbackFetch('/staff-auth/login', {method:'POST'});
    await feedbackFetch('/staff-auth/forgot-password', {method:'POST'});
    assert.equal(activeRequests(), 0);
  } finally { globalThis.fetch = original; }
});

test('concurrent user actions keep loading active until both finish', async () => {
  const original = globalThis.fetch;
  const releases = [];
  globalThis.fetch = () => new Promise(resolve => releases.push(resolve));
  try {
    const first = feedbackFetch('/staff/profile', {method:'PATCH'});
    const second = feedbackFetch('/staff/tasks/1', {method:'PATCH'});
    assert.equal(activeRequests(), 2);
    releases[0](new Response('{}'));
    await first;
    assert.equal(activeRequests(), 1);
    releases[1](new Response('{}'));
    await second;
    assert.equal(activeRequests(), 0);
  } finally { globalThis.fetch = original; }
});

test('network errors and aborted requests release loading and preserve caller errors', async () => {
  const original = globalThis.fetch;
  try {
    for (const error of [new Error('offline'), new DOMException('cancelled', 'AbortError')]) {
      globalThis.fetch = async () => { throw error; };
      await assert.rejects(feedbackFetch('/staff/profile', {method:'PATCH'}), value=>value === error);
      assert.equal(activeRequests(), 0);
    }
  } finally { globalThis.fetch = original; }
});

test('HTTP validation failures preserve the response body for field errors', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({detail:'Invalid email address'}), {status:422});
  try {
    const response = await feedbackFetch('/staff/profile', {method:'PATCH'});
    assert.deepEqual(await response.json(), {detail:'Invalid email address'});
    assert.equal(activeRequests(), 0);
  } finally { globalThis.fetch = original; }
});
