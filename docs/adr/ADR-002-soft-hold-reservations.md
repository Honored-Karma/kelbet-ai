# ADR-002: Soft-hold credit reservations

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Async generations need funds locked before provider work, without charging until success.

## Decision

`wallets.balance` = owned credits; `wallets.reserved` = held. `available = balance - reserved`.  
Reserve increases `reserved`; capture debits ledger and decreases both; release decreases `reserved` only. Refund credits ledger after capture.

## Consequences

No negative balance via CHECKs. Reservation rows provide idempotency for reserve/release/capture.
