# ADR-001: Modular monolith for v0.3

**Status:** Accepted  
**Date:** 2026-07-30

## Context

KELBET needs Mini App, generation pipeline, and workers without operational complexity of microservices.

## Decision

Single domain package (`packages/kelbet`) with apps: `api`, `bot`, `worker`, `web`. No Kafka, no Kubernetes requirement.

## Consequences

Shared transactions and types stay simple; scale vertically first. Split only if proven bottlenecks appear later.
