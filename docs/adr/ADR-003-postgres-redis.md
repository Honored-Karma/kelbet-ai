# ADR-003: Postgres SoT, Redis for queue/FSM/replay

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Need queues and short-lived auth replay protection without a second source of truth for money/jobs.

## Decision

PostgreSQL owns users, wallet, generations, catalog. Redis: aiogram FSM, ARQ queues, initData replay keys.

## Consequences

Crash recovery reconciles from Postgres; Redis loss may re-enqueue or re-auth but not corrupt balances.
