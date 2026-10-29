import { useEffect, useRef, useState } from 'react';
import { createSSEParser, coalescedRefresh } from './liveTransport.mjs';

const API = ((typeof window !== 'undefined' && window.__THE_VILLA_API_BASE__) || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const channels = new Map();
function token() {
  for (const storage of [sessionStorage, localStorage]) {
    try { const auth = JSON.parse(storage.getItem('theVillaPortalAuth') || 'null'); if (auth?.access_token) return auth.access_token; } catch { /* Missing storage is handled as unauthenticated. */ }
  }
  return '';
}

function channelFor(audience) {
  if (channels.has(audience)) return channels.get(audience);
  const channel = { listeners: new Set(), controller: null, timer: null, stopped: false, status: 'connecting', databaseLive: false, refreshAuth: null, bookingToken: '', delay: 1000 };
  channel.notify = (event, payload) => { for (const listener of channel.listeners) listener(event, payload); };
  channel.connect = async () => {
    if (channel.stopped) return;
    channel.controller = new AbortController();
    try {
      const access = audience === 'portal' ? token() : '';
      const isBooking = audience.startsWith('booking:');
      const bookingId = isBooking ? audience.slice('booking:'.length) : '';
      if (isBooking && (!bookingId || !channel.bookingToken)) throw new Error('Booking session missing');
      if (audience === 'portal' && !access) throw new Error('Portal session missing');
      const endpoint = isBooking
        ? `${API}/live/booking/${encodeURIComponent(bookingId)}`
        : `${API}/live/${audience}`;
      const response = await fetch(endpoint, {
        headers: {
          Accept: 'text/event-stream',
          ...(access ? { Authorization: `Bearer ${access}` } : {}),
          ...(isBooking ? { 'X-Booking-Token': channel.bookingToken } : {}),
        },
        signal: channel.controller.signal, cache: 'no-store',
      });
      if (response.status === 401 && channel.refreshAuth) { await channel.refreshAuth(); throw new Error('Session refreshed'); }
      if (!response.ok || !response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('Live stream unavailable');
      const reader = response.body.getReader(); const decoder = new TextDecoder();
      const parse = createSSEParser((event, payload) => {
        if (event === 'ready' || event === 'health') {
          channel.databaseLive = payload.databaseLive === true;
          channel.status = 'live'; channel.delay = 1000;
        }
        channel.notify(event, payload);
      });
      try {
        while (!channel.stopped) { const { done, value } = await reader.read(); if (done) break; parse(decoder.decode(value, { stream: true })); }
      } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    } catch (error) { if (channel.stopped || error?.name === 'AbortError') return; }
    if (!channel.stopped) {
      channel.status = 'reconnecting'; channel.notify('status', { status: channel.status });
      channel.timer = setTimeout(channel.connect, channel.delay + Math.floor(Math.random() * 300));
      channel.delay = Math.min(channel.delay * 2, 30000);
    }
  };
  channels.set(audience, channel); return channel;
}

export default function useLiveUpdates({ audience = 'portal', domains, onChange, refreshAuth, bookingToken = '', enabled = true, safetyRefreshMs = 0 }) {
  const callback = useRef(onChange); callback.current = onChange;
  const auth = useRef(refreshAuth); auth.current = refreshAuth;
  const [status, setStatus] = useState('connecting');
  const domainKey = [...domains].sort().join(',');
  useEffect(() => {
    if (!enabled) return;
    const channel = channelFor(audience);
    channel.bookingToken = bookingToken;
    channel.stopped = false;
    if (auth.current) channel.refreshAuth = () => auth.current?.();
    const refresh = coalescedRefresh(() => callback.current?.());
    const wanted = new Set(domainKey.split(','));
    const listener = (event, payload) => {
      if (event === 'ready') { setStatus('live'); refresh(); }
      else if (event === 'status') setStatus(payload.status);
      else if (event === 'change' && payload.domains?.some(domain => wanted.has(domain))) refresh();
    };
    channel.listeners.add(listener); setStatus(channel.status);
    if (channel.listeners.size === 1) channel.connect();
    else if (channel.status === 'live') refresh();
    // SSE handles immediate changes. Optional snapshot checks also recover
    // missed database events (a subscribed socket alone cannot prove that
    // every table is included in the database's realtime publication).
    const fallback = setInterval(() => {
      if (safetyRefreshMs > 0 || channel.status !== 'live' || !channel.databaseLive) refresh();
    }, safetyRefreshMs > 0 ? safetyRefreshMs : 15000);
    const focus = () => { if (document.visibilityState === 'visible') refresh(); };
    window.addEventListener('focus', focus);
    document.addEventListener('visibilitychange', focus);
    return () => {
      clearInterval(fallback); window.removeEventListener('focus', focus); refresh.cancel();
      document.removeEventListener('visibilitychange', focus);
      channel.listeners.delete(listener);
      if (!channel.listeners.size) {
        channel.stopped = true; clearTimeout(channel.timer); channel.controller?.abort(); channels.delete(audience);
      }
    };
  }, [audience, bookingToken, domainKey, enabled, safetyRefreshMs]);
  return status;
}
