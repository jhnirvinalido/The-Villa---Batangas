const collator = new Intl.Collator('en-PH', { numeric: true, sensitivity: 'base' });

export function deskTableRows(rows, { query = '', searchText = () => '', sortValue, direction = 'asc' } = {}) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const filtered = rows.filter(row => {
    const text = String(searchText(row) || '').toLocaleLowerCase();
    return words.every(word => text.includes(word));
  });
  if (!sortValue) return filtered;
  return filtered.sort((a, b) => {
    const left = sortValue(a), right = sortValue(b);
    const missing = value => value == null || value === '' || (typeof value === 'number' && !Number.isFinite(value));
    const missingLeft = missing(left), missingRight = missing(right);
    if (missingLeft || missingRight) return Number(missingLeft) - Number(missingRight);
    const comparison = typeof left === 'number' && typeof right === 'number' ? left - right : collator.compare(String(left), String(right));
    return direction === 'desc' ? -comparison : comparison;
  });
}

export function deskTablePage(rows, requestedPage = 0, pageSize = 10) {
  const size = Math.max(1, Math.floor(Number(pageSize) || 10));
  const pageCount = Math.max(1, Math.ceil(rows.length / size));
  const page = Math.max(0, Math.min(Math.floor(Number(requestedPage) || 0), pageCount - 1));
  const offset = page * size;
  return { rows: rows.slice(offset, offset + size), page, pageCount, total: rows.length, start: rows.length ? offset + 1 : 0, end: Math.min(offset + size, rows.length) };
}
