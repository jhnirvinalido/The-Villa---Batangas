import { useId, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, Search, SlidersHorizontal } from 'lucide-react';
import { deskTablePage, deskTableRows } from './frontDeskTableModel.mjs';
import { RecordPagination } from './RecordListControls';

export default function FrontDeskTable({ title, description, rows, columns, searchText, filters, filterKey = '', actions, initialSort, initialDirection = 'asc', loading, emptyMessage = 'No records match your search and filters.' }) {
  const [query, setQuery] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(() => !window.matchMedia('(max-width: 680px)').matches);
  const [sort, setSort] = useState({ key: initialSort, direction: initialDirection });
  const [pageSize, setPageSize] = useState(10);
  const [position, setPosition] = useState({ signature: '', page: 0 });
  const id = useId();
  const signature = JSON.stringify([query, sort.key, sort.direction, pageSize, filterKey]);
  const sortColumn = columns.find(column => column.key === sort.key);
  const result = deskTableRows(rows, { query, searchText, sortValue: sortColumn?.value, direction: sort.direction });
  const page = deskTablePage(result, position.signature === signature ? position.page : 0, pageSize);
  const changePage = value => setPosition({ signature, page: value });
  function sortBy(key) {
    setSort(current => ({ key, direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc' }));
  }
  return <section className="fd-panel fd-table-panel fd-data-table villa-table-frame" aria-labelledby={id}>
    <header><div><h2 id={id}>{title}</h2><p>{description}</p></div>{actions}</header>
    <div className="fd-table-controls">
      <label className="fd-search"><Search size={17}/><input type="search" aria-label={`Search ${title}`} placeholder="Search records…" value={query} onChange={event => setQuery(event.target.value)}/></label>
      {query && <button type="button" className="fd-button" onClick={() => setQuery('')}>Clear search</button>}
      {filters && <button type="button" className="fd-button fd-filter-toggle" aria-expanded={filtersOpen} aria-controls={`${id}-filters`} onClick={() => setFiltersOpen(value => !value)}><SlidersHorizontal size={15}/>Filters</button>}
      {filters && <div id={`${id}-filters`} className="fd-table-filter-fields" hidden={!filtersOpen}>{filters}</div>}
    </div>
    <div className="fd-table-wrap" role="region" aria-label={`${title} table`} tabIndex={0}>
      <table aria-busy={loading || undefined}>
        <caption className="visually-hidden">{title}</caption>
        <thead><tr>{columns.map(column => <th key={column.key} scope="col" aria-sort={column.value ? sort.key === column.key ? sort.direction === 'asc' ? 'ascending' : 'descending' : 'none' : undefined}>
          {column.value ? <button type="button" className="fd-sort-heading" onClick={() => sortBy(column.key)} aria-label={`Sort by ${column.label}`}>{column.label}{sort.key === column.key ? sort.direction === 'asc' ? <ArrowUp size={14}/> : <ArrowDown size={14}/> : <ArrowUpDown size={14}/>}</button> : column.label}
        </th>)}</tr></thead>
        <tbody>{page.rows.map(row => <tr key={row.id}>{columns.map(column => <td key={column.key}>{column.render ? column.render(row) : column.value(row)}</td>)}</tr>)}{!page.total && <tr><td colSpan={columns.length} className="fd-empty">{loading ? 'Loading records…' : emptyMessage}</td></tr>}</tbody>
      </table>
    </div>
    <RecordPagination page={page} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={setPageSize} label="records"/>
  </section>;
}
