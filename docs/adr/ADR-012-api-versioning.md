# ADR-012: API versioning

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Mini App and future clients need a stable HTTP contract.

## Decision

Business routes under `/api/v1`; OpenAPI from FastAPI; liveness `/health` retained; readiness `/api/v1/ready`.

## Consequences

Breaking changes require `/api/v2`; v1 remains until clients migrate.
