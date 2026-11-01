import { useEffect, useState } from 'react';

export default function usePortalSidebar() {
  const [collapsed, setCollapsed] = useState(() => window.matchMedia('(max-width: 980px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 980px)');
    const closeOnNarrowScreen = event => { if (event.matches) setCollapsed(true); };
    const closeOnEscape = event => { if (event.key === 'Escape' && media.matches) setCollapsed(true); };
    media.addEventListener('change', closeOnNarrowScreen);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      media.removeEventListener('change', closeOnNarrowScreen);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, []);
  return [collapsed, setCollapsed];
}
