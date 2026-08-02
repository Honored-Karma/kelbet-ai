import assert from "node:assert/strict";
import test from "node:test";
import { idempotencyKeyForQuote } from "../src/features/generation/submissionRecovery.ts";

test("keeps the idempotency key when a submission is retried unchanged", () => {
  const first = idempotencyKeyForQuote(null, "quote-a", "request-a", () => "key-a");
  const retry = idempotencyKeyForQuote(first, "quote-a", "request-a", () => "key-b");

  assert.deepEqual(retry, {
    quoteId: "quote-a",
    requestFingerprint: "request-a",
    idempotencyKey: "key-a",
  });
});

test("uses a new key when a refreshed quote is issued", () => {
  const first = idempotencyKeyForQuote(null, "quote-a", "request-a", () => "key-a");
  const refreshed = idempotencyKeyForQuote(first, "quote-b", "request-a", () => "key-b");

  assert.deepEqual(refreshed, {
    quoteId: "quote-b",
    requestFingerprint: "request-a",
    idempotencyKey: "key-b",
  });
});

test("uses a new key when the user changes the request before submitting again", () => {
  const first = idempotencyKeyForQuote(null, "quote-a", "request-a", () => "key-a");
  const changed = idempotencyKeyForQuote(first, "quote-a", "request-b", () => "key-b");

  assert.deepEqual(changed, {
    quoteId: "quote-a",
    requestFingerprint: "request-b",
    idempotencyKey: "key-b",
  });
});
