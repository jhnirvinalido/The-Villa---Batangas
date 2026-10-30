import test from "node:test";
import assert from "node:assert/strict";
import {
  isValidEmailAddress,
  normalizePhilippinePhone,
} from "./contactValidation.mjs";

test("Philippine phone formatting is normalized and letters are rejected", () => {
  assert.equal(normalizePhilippinePhone("0912 345 6789"), "+639123456789");
  assert.equal(normalizePhilippinePhone("+63 (912) 345-6789"), "+639123456789");
  assert.equal(normalizePhilippinePhone("0912abc3456789"), "");
  assert.equal(normalizePhilippinePhone("091234567"), "");
});

test("email syntax rejects malformed local parts and domains", () => {
  assert.equal(isValidEmailAddress("guest@example.com"), true);
  assert.equal(isValidEmailAddress("guest..name@example.com"), false);
  assert.equal(isValidEmailAddress("guest@example"), false);
  assert.equal(isValidEmailAddress("guest@-example.com"), false);
  assert.equal(isValidEmailAddress("guest@example..com"), false);
});
