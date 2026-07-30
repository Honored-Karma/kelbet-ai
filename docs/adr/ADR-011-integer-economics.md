# ADR-011: Integer economics

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Floating point is unsafe for credits and cost accounting.

## Decision

User prices in integer credit units. Provider costs in integer subunits (`provider_cost_units`). Pricing multipliers use integer arithmetic with explicit rounding (ceil to user).

## Consequences

No `float`/`Numeric` on money paths; DB CHECKs enforce non-negative balances.
