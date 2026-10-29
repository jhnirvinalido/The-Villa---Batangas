import { staffLoginReturnPath } from './staffNotificationFeed.mjs';

export async function playStaffNotificationSound() {
  if (typeof window === 'undefined') return false;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return false;

  let context;
  try {
    context = new AudioContextClass();
    await context.resume();
    const oscillator = context.createOscillator();
    const volume = context.createGain();
    const start = context.currentTime;
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(880, start);
    oscillator.frequency.setValueAtTime(1174.66, start + 0.12);
    volume.gain.setValueAtTime(0.0001, start);
    volume.gain.exponentialRampToValueAtTime(0.12, start + 0.025);
    volume.gain.setValueAtTime(0.12, start + 0.12);
    volume.gain.exponentialRampToValueAtTime(0.0001, start + 0.32);
    oscillator.connect(volume);
    volume.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.33);
    oscillator.addEventListener('ended', () => context.close(), { once: true });
    return true;
  } catch {
    try { await context?.close(); } catch { /* Audio is an optional alert enhancement. */ }
    return false;
  }
}

export function notificationTarget(item) {
  return staffLoginReturnPath({ pathname: '/staff', search: `?${new URLSearchParams({ task: item?.taskId || '' })}` });
}

export async function showStaffBrowserNotification(item, staffId, total = 1) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return false;
  const title = total > 1 ? `The Villa · ${total} new updates` : `The Villa · ${item.title || 'Staff update'}`;
  const options = {
    body: item.message || 'Open your staff portal to review your latest update.',
    icon: '/favicon.png', badge: '/favicon.png',
    tag: `villa-staff-${staffId}-${item.id}`,
    data: { path: notificationTarget(item) },
  };
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.register('/staff-notifications-sw.js', { scope: '/staff' });
      // Registration may initially be installing; wait for activation before display.
      const worker = registration.installing || registration.waiting;
      if (!registration.active && worker) {
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => { worker.removeEventListener('statechange', change); reject(new Error('Notification worker not ready')); }, 10000);
          const change = () => {
            if (worker.state === 'activated' || worker.state === 'redundant') {
              clearTimeout(timer); worker.removeEventListener('statechange', change);
              worker.state === 'activated' ? resolve() : reject(new Error('Notification worker unavailable'));
            }
          };
          worker.addEventListener('statechange', change); change();
        });
      }
      await registration.showNotification(title, options);
      return true;
    } catch { /* Desktop browsers can fall back to Notification directly. */ }
  }
  try {
    const notice = new Notification(title, options);
    notice.onclick = () => { notice.close(); window.focus(); window.location.assign(notificationTarget(item)); };
    return true;
  } catch { return false; }
}
