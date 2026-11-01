import { LayoutGrid, List } from 'lucide-react';

export default function RecordViewToggle({ value, onChange }) {
  return <div className="record-view-toggle" role="group" aria-label="Record layout">
    <button type="button" aria-pressed={value === 'table'} onClick={() => onChange('table')}><List size={16}/>Table</button>
    <button type="button" aria-pressed={value === 'cards'} onClick={() => onChange('cards')}><LayoutGrid size={16}/>Cards</button>
  </div>;
}
