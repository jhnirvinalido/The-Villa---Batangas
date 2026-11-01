export function paginateRecords(records, requestedPage = 0, pageSize = 10) {
  const size = Math.max(1, Math.floor(Number(pageSize) || 10));
  const pageCount = Math.max(1, Math.ceil(records.length / size));
  const page = Math.max(0, Math.min(Math.floor(Number(requestedPage) || 0), pageCount - 1));
  const offset = page * size;
  return {
    rows: records.slice(offset, offset + size),
    page,
    pageCount,
    total: records.length,
    start: records.length ? offset + 1 : 0,
    end: Math.min(offset + size, records.length),
  };
}
