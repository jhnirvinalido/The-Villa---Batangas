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
  assert.match(formatUserFacingMessage("Internal Server Error"), /server couldn't complete this request/i);
});

test("specific validation details remain actionable", () => {
  assert.equal(formatUserFacingMessage("Email address is required."), "Email address is required.");
  assert.equal(getApiErrorMessage({
    detail: [{ loc: ["body", "first_name"], msg: "Field required" }],
  }, 422), "First name is required.");
  assert.match(getApiErrorMessage({}, 409), /latest information has changed/i);
});

test("empty errors receive the supplied fallback", () => {
  assert.equal(getUserFacingError(null, "Try again."), "Try again.");
});
