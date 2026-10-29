/* Browser notification clicks only: no caching, data interception or Web Push. */
self.addEventListener('notificationclick', event => {
  event.notification.close();
  let path = '/staff';
  try {
    const url = new URL(event.notification.data?.path || '/staff', self.location.origin);
    const task = url.searchParams.get('task');
    if (url.origin === self.location.origin && url.pathname === '/staff' && task
        && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(task)) {
      path = `/staff?${new URLSearchParams({ task })}`;
    }
  } catch { /* Always open the same-origin, authenticated staff route. */ }
  const target = new URL(path, self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async clients => {
    const current = clients.find(client => {
      try { const url = new URL(client.url); return url.origin === self.location.origin && url.pathname === '/staff'; }
      catch { return false; }
    });
    if (current && 'navigate' in current) { await current.navigate(target); return current.focus(); }
    return self.clients.openWindow(target);
  }));
});
