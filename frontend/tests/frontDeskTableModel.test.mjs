import test from 'node:test';
import assert from 'node:assert/strict';
import { deskTableRows, deskTablePage } from '../src/frontDeskTableModel.mjs';

const rows = [
  { id: 'a', guest: 'Ana Santos', villa: 'Villa 10', amount: 1000 },
  { id: 'b', guest: 'Ben Cruz', villa: 'Villa 2', amount: 200 },
  { id: 'c', guest: 'ANA Reyes', villa: 'Villa 2', amount: 50 },
];
const searchText = row => `${row.guest} ${row.villa}`;

test('search matches multiple words across fields before records are paginated', () => {
  const result = deskTableRows(rows, { query: '  ana  villa 2 ', searchText, sortValue: row => row.amount });
  assert.deepEqual(result.map(row => row.id), ['c']);
  assert.equal(deskTablePage(result, 9, 10).total, 1);
});

test('amount sorting is numeric and villa names sort naturally without mutating records', () => {
  assert.deepEqual(deskTableRows(rows, { sortValue: row => row.amount }).map(row => row.id), ['c', 'b', 'a']);
  assert.deepEqual(deskTableRows(rows, { sortValue: row => row.amount, direction: 'desc' }).map(row => row.id), ['a', 'b', 'c']);
  assert.deepEqual(deskTableRows(rows, { sortValue: row => row.villa }).map(row => row.id), ['b', 'c', 'a']);
  assert.deepEqual(rows.map(row => row.id), ['a', 'b', 'c']);
});

test('missing values sort after known values in both directions', () => {
  const incomplete = [{ id: 'missing' }, { id: 'invalid', amount: NaN }, { id: 'zero', amount: 0 }, { id: 'paid', amount: 50 }];
  for (const direction of ['asc', 'desc']) {
    assert.deepEqual(deskTableRows(incomplete, { sortValue: row => row.amount, direction }).slice(-2).map(row => row.id), ['missing', 'invalid']);
  }
});

test('all available receipts remain reachable beyond the former 50-record cutoff', () => {
  const history = Array.from({ length: 57 }, (_, index) => ({ id: index }));
  const result = deskTablePage(history, 5, 10);
  assert.equal(result.pageCount, 6);
  assert.equal(result.total, 57);
  assert.equal(result.start, 51);
  assert.equal(result.end, 57);
  assert.equal(result.rows.at(-1).id, 56);
});

test('pagination clamps safely after live records shrink or filters find no matches', () => {
  assert.deepEqual(deskTablePage(rows, 99, 2), { rows: [rows[2]], page: 1, pageCount: 2, total: 3, start: 3, end: 3 });
  assert.deepEqual(deskTablePage([], 99, 10), { rows: [], page: 0, pageCount: 1, total: 0, start: 0, end: 0 });
  assert.equal(deskTablePage(rows, -5, 0).rows.length, 3);
});
