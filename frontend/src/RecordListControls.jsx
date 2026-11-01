import './RecordListControls.css';

export function RecordPagination({ page, pageSize, onPageChange, onPageSizeChange, label = 'records' }) {
  return <footer className="record-pagination">
    <span role="status" aria-live="polite">
      Showing {page.start}–{page.end} of {page.total} {label}
    </span>
    <label>Rows per page
      <select aria-label={`Rows per page for ${label}`} value={pageSize} onChange={event => onPageSizeChange(Number(event.target.value))}>
        {[10, 20, 50].map(size => <option key={size} value={size}>{size}</option>)}
      </select>
    </label>
    <nav aria-label={`${label} pages`}>
      <button type="button" disabled={page.page === 0} onClick={() => onPageChange(page.page - 1)}>Previous</button>
      <span>Page {page.page + 1} of {page.pageCount}</span>
      <button type="button" disabled={page.page + 1 >= page.pageCount} onClick={() => onPageChange(page.page + 1)}>Next</button>
    </nav>
  </footer>;
}
