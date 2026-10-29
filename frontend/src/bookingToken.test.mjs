import test from "node:test";
import assert from "node:assert/strict";
import { readBookingToken, saveBookingToken } from "./bookingToken.mjs";

function storage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
}

test("checkout survives a new tab but does not grant access to another booking", () => {
  globalThis.window = { sessionStorage: storage(), localStorage: storage() };
  saveBookingToken("booking-a", "private-token");
  window.sessionStorage = storage();
  assert.equal(readBookingToken("booking-a"), "private-token");
  assert.equal(readBookingToken("booking-b"), null);
});

test("expired persistent tokens are removed", () => {
  globalThis.window = { sessionStorage: storage(), localStorage: storage() };
  window.localStorage.setItem("theVillaGuestBooking:a", JSON.stringify({ token: "old", expiresAt: 1 }));
  assert.equal(readBookingToken("a"), null);
  assert.equal(window.localStorage.getItem("theVillaGuestBooking:a"), null);
});

test("storage being blocked prevents checkout instead of losing the credential", () => {
  const blocked = { getItem() { throw Error(); }, setItem() { throw Error(); } };
  globalThis.window = { sessionStorage: blocked, localStorage: blocked };
  assert.equal(readBookingToken("a"), null);
  assert.throws(() => saveBookingToken("a", "token"), /allow browser storage/);
});
