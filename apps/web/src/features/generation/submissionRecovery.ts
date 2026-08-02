export type SubmissionAttempt = {
  quoteId: string;
  requestFingerprint: string;
  idempotencyKey: string;
};

/**
 * Keeps retries tied to the same server-side request. A newly issued quote is
 * intentionally a new transaction boundary and receives a fresh key.
 */
export function idempotencyKeyForQuote(
  current: SubmissionAttempt | null,
  quoteId: string,
  requestFingerprint: string,
  createKey: () => string,
): SubmissionAttempt {
  if (current?.quoteId === quoteId && current.requestFingerprint === requestFingerprint) {
    return current;
  }
  return { quoteId, requestFingerprint, idempotencyKey: createKey() };
}
