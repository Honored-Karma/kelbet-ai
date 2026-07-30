# ADR-005: DB-backed model catalog

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Prices and capabilities must change without frontend deploys; frontend must not invent prices.

## Decision

`catalog_models` in Postgres; API quote endpoint; feature flags and deprecation fields.

## Consequences

Ops can disable models quickly; all clients share one pricing source.
