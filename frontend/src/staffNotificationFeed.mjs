/** Pure feed selection: unread login catch-up and new IDs, without repeat popups. */
export function notificationId(item) { return typeof item?.id === 'string' ? item.id : ''; }
export function newUnreadNotifications(items, seen) {
  const unique = new Map();
  for (const item of items || []) {
    const id = notificationId(item);
    if (id && item.unread === true && !seen.has(id)) unique.set(id, item);
  }
  return [...unique.values()].sort((a, b) => (Date.parse(b.timestamp) || 0) - (Date.parse(a.timestamp) || 0));
}
export function staffNotificationTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Recently' : new Intl.DateTimeFormat('en-PH', {
    timeZone: 'Asia/Manila', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(date);
}

export function staffLoginReturnPath(from) {
  if (from?.pathname !== '/staff') return '/staff';
  const task = new URLSearchParams(from.search || '').get('task');
  return task && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(task)
    ? `/staff?${new URLSearchParams({ task })}` : '/staff';
}
