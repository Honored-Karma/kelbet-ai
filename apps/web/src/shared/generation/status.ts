/**
 * Statuses a generation passes through before it reaches a terminal state.
 *
 * Shared so that every surface counting "work in progress" — the history
 * gallery, the profile wallet — agrees on what counts as active. Divergent
 * copies of this set are how a reserved-credits badge starts disagreeing with
 * the list it is supposed to summarise.
 */
export const ACTIVE_GENERATION_STATUSES: ReadonlySet<string> = new Set([
  "created",
  "queued",
  "submitting",
  "running",
  "finalizing",
]);

export function isActiveGeneration(status: string): boolean {
  return ACTIVE_GENERATION_STATUSES.has(status);
}
