import { getApiErrorMessage } from './errorMessages.mjs';

const pending = new Map();
let sequence = 0;
const failures = new Map();
const emit = detail => {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('villa:feedback', { detail }));
};
export function tracksAction(url, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  return !['GET', 'HEAD'].includes(method)
    && !/\/(refresh|sync-payment|verify-payment|session)(?:\?|$)/.test(String(url))
    && !/\/staff-auth\/(login|forgot-password)(?:\?|$)/.test(String(url));
}
export function activeRequests() { return pending.size; }
export function reportFeedback(message, type = 'error') { emit({ kind: 'alert', message, type }); }
export async function feedbackFetch(url, options = {}) {
  const tracked = tracksAction(url, options);
  const id = ++sequence;
  if (tracked) { pending.set(id, true); emit({ kind: 'pending', count: pending.size }); }
  try {
    const response = await globalThis.fetch(url, options);
    // Session refresh and background reads own their retry/error behavior.
    if (tracked && !response.ok && response.status !== 401) {
      const data = await response.clone().json().catch(() => ({}));
      const message = getApiErrorMessage(data, response.status);
      if (Date.now() - (failures.get(message) || 0) > 30000) {
        failures.set(message, Date.now()); reportFeedback(message);
      }
    }
    return response;
  } catch (error) {
    if (tracked && error?.name !== 'AbortError') reportFeedback('Unable to reach the server. Check your connection and try again.');
    throw error;
  } finally {
    if (tracked) { pending.delete(id); emit({ kind: 'pending', count: pending.size }); }
  }
}
