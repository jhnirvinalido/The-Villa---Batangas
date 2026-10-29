import test from 'node:test';
import assert from 'node:assert/strict';
import { createSSEParser, coalescedRefresh, singleFlightRefresh } from '../src/liveTransport.mjs';

test('chunked staff event stream delivers task and notification changes after health frames', () => {
  const events = [];
  const parse = createSSEParser((event, data) => events.push({ event, data }));
  const wire = 'event: ready\ndata: {"databaseLive":true}\n\n'
    + 'event: change\ndata: {"domains":["tasks","notifications"]}\n\n'
    + 'event: health\ndata: {"databaseLive":false}\n\n'
    + 'event: change\ndata: {"domains":["staff"]}\n\n';
  for (let i = 0; i < wire.length; i += 7) parse(wire.slice(i, i + 7));
  assert.deepEqual(events.map(entry => entry.event), ['ready', 'change', 'health', 'change']);
  assert.deepEqual(events[1].data.domains, ['tasks', 'notifications']);
  assert.equal(events[2].data.databaseLive, false);
});

test('event arriving during a workspace refresh triggers a trailing snapshot', async () => {
  let finishFirst;
  let started;
  let finishSecond;
  const firstStarted = new Promise(resolve => { started = resolve; });
  const secondFinished = new Promise(resolve => { finishSecond = resolve; });
  let calls = 0;
  const refresh = coalescedRefresh(async () => {
    calls++;
    if (calls === 1) {
      started();
      await new Promise(resolve => { finishFirst = resolve; });
    } else finishSecond();
  }, 0);
  try {
    refresh();
    await firstStarted;
    refresh(); refresh();
    finishFirst();
    await secondFinished;
    assert.equal(calls, 2);
  } finally { refresh.cancel(); }
});

test('overlapping inbox event and recovery reads serialize and fetch once more', async () => {
  let finish;
  let started;
  let trailingFinished;
  const firstStarted = new Promise(resolve => { started = resolve; });
  const trailing = new Promise(resolve => { trailingFinished = resolve; });
  let active = 0, peak = 0, calls = 0;
  const refresh = singleFlightRefresh(async () => {
    active++; peak = Math.max(peak, active); calls++;
    if (calls === 1) {
      started();
      await new Promise(resolve => { finish = resolve; });
    }
    active--;
    if (calls === 2) trailingFinished();
  });
  const initial = refresh();
  await firstStarted;
  refresh(); refresh();
  finish();
  await initial; await trailing;
  assert.equal(peak, 1);
  assert.equal(calls, 2);
});
