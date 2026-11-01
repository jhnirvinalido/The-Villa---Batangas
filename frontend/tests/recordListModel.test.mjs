import test from 'node:test';
import assert from 'node:assert/strict';
import { paginateRecords } from '../src/recordListModel.mjs';

test('pagination returns the requested page and range', () => {
  const records = Array.from({ length: 25 }, (_, id) => ({ id }));
  const page = paginateRecords(records, 1, 10);
  assert.deepEqual(page.rows.map(record => record.id), Array.from({ length: 10 }, (_, index) => index + 10));
  assert.equal(page.start, 11);
  assert.equal(page.end, 20);
  assert.equal(page.pageCount, 3);
});

test('pagination clamps invalid pages and handles empty results', () => {
  assert.equal(paginateRecords([{ id: 1 }], 8, 10).page, 0);
  assert.deepEqual(paginateRecords([], 3, 10), {
    rows: [],
    page: 0,
    pageCount: 1,
    total: 0,
    start: 0,
    end: 0,
  });
});
