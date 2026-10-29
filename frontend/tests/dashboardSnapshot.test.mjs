import test from 'node:test';
import assert from 'node:assert/strict';
import {snapshotRows} from '../src/dashboardSnapshot.mjs';

test('a failed booking refresh cannot erase previously loaded bookings',()=>{
  const saved=[{id:'booking-1',guestName:'Test guest'}];
  assert.equal(snapshotRows(saved,[],true),saved);
  assert.equal(snapshotRows(saved,undefined),saved);
  assert.equal(snapshotRows(saved,null),saved);
});
test('recovery updates data and a successful empty snapshot clears removed records',()=>{
  const saved=[{id:'booking-1'}];
  const next=[{id:'booking-2'}];
  assert.equal(snapshotRows(saved,next),next);
  assert.deepEqual(snapshotRows(saved,[]),[]);
});
test('an unchanged live snapshot keeps its existing reference',()=>{
  const saved=[{id:'task-1',status:'Pending'}];
  assert.equal(snapshotRows(saved,[{...saved[0]}]),saved);
});
