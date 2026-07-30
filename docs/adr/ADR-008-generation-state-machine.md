# ADR-008: Generation state machine

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Long-running provider jobs need crash-safe status and wallet coupling.

## Decision

Explicit statuses with transactional transitions; webhooks + polling fallback; dead-letter only when wallet/job inconsistent. See `GENERATION_STATE_MACHINE.md`.

## Consequences

Clear test matrix; illegal transitions raise domain errors.
