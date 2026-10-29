const PREFIX = "theVillaGuestBooking:";
const MAX_AGE = 24 * 60 * 60 * 1000;

export function saveBookingToken(bookingId, token) {
  let saved = false;
  try {
    window.sessionStorage.setItem(`${PREFIX}${bookingId}`, token);
    saved = true;
  } catch { /* A second storage option may still work. */ }
  try {
    window.localStorage.setItem(`${PREFIX}${bookingId}`, JSON.stringify({
      token, expiresAt: Date.now() + MAX_AGE,
    }));
    saved = true;
  } catch { /* Private browsing may disable persistent storage. */ }
  if (!saved) throw new Error("Please allow browser storage before starting secure checkout.");
}

export function readBookingToken(bookingId) {
  try {
    const token = window.sessionStorage.getItem(`${PREFIX}${bookingId}`);
    if (token) return token;
  } catch { /* Try the expiring cross-tab copy. */ }
  try {
    const key = `${PREFIX}${bookingId}`;
    const saved = JSON.parse(window.localStorage.getItem(key) || "null");
    if (saved?.token && saved.expiresAt > Date.now()) return saved.token;
    window.localStorage.removeItem(key);
  } catch { /* Missing or invalid storage must never bypass authorization. */ }
  return null;
}
