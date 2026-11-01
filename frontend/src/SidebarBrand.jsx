import { PanelLeftClose } from 'lucide-react';

export default function SidebarBrand({ label, collapsed, onToggle }) {
  return <>
    <button type="button" className="admin-brand-toggle" onClick={onToggle}
      title={collapsed ? 'Open navigation' : 'Close navigation'}
      aria-label={collapsed ? 'Open navigation' : 'Close navigation'} aria-expanded={!collapsed}>
      <span className="admin-brand-logo"><img src="/favicon.png" alt="" /></span>
    </button>
    <span className="admin-brand-name">The Villa<small>{label}</small></span>
    {!collapsed && <button type="button" className="admin-sidebar-collapse-control" onClick={onToggle}
      title="Collapse navigation" aria-label="Collapse navigation"><PanelLeftClose className="h-[18px] w-[18px] shrink-0" size={18}/></button>}
  </>;
}
