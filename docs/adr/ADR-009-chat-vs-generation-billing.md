# ADR-009: Sync chat vs async generation billing

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Bot AI chat is sync and already debit-after-success; generations are async and must hold funds first.

## Decision

Keep `ChatService` post-success debit. Generations use reserve → capture/release. Unify later only with an explicit migration plan.

## Consequences

Two billing paths on one wallet; shared primitives only (`WalletService`).
