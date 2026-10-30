import test from "node:test";
import assert from "node:assert/strict";
import {
  getApiErrorMessage,
  formatUserFacingMessage,
  getUserFacingError,
} from "./errorMessages.mjs";

test("network failures use a clear connection message", () => {
  assert.match(formatUserFacingMessage("Failed to fetch"), /check your internet connection/i);
  assert.match(formatUserFacingMessage("NetworkError when attempting to fetch resource."), /check your internet connection/i);
  assert.match(getUserFacingError(new TypeError("Load failed"), "Try again"), /check your internet connection/i);
});

test("generic server failures do not expose framework wording", () => {
  assert.match(formatUserFacingMessage("Internal Server Error"), /couldn't complete that request/i);
  assert.match(formatUserFacingMessage("Method Not Allowed"), /couldn't complete that request/i);
  assert.match(getApiErrorMessage({ detail: "Method Not Allowed" }, 405), /couldn't complete that request/i);
  assert.doesNotMatch(
    getApiErrorMessage({ detail: "Database migration failed in Supabase RPC." }, 500),
    /database|migration|supabase|rpc/i,
  );
  assert.doesNotMatch(
    formatUserFacingMessage("The Villa's email service cannot send from this hosting setup."),
    /email service|hosting setup/i,
  );
  assert.doesNotMatch(
    getUserFacingError(new Error("TypeError: Cannot read properties of undefined."), "Please try again."),
    /typeerror|cannot read properties|undefined/i,
  );
});

test("specific validation details remain actionable", () => {
  assert.equal(formatUserFacingMessage("Email address is required."), "Email address is required.");
  assert.equal(
    getApiErrorMessage({
      detail: [{ loc: ["body", "first_name"], msg: "Field required" }],
    }, 422),
    "Please check the information you entered and try again.",
  );
  assert.equal(getApiErrorMessage({ detail: "Email address is required." }, 422), "Email address is required.");
  assert.match(getApiErrorMessage({}, 409), /latest information has changed/i);
});

test("empty errors receive the supplied fallback", () => {
  assert.equal(getUserFacingError(null, "Try again."), "Try again.");
});
