# ADR-010: Observability redaction

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Prompts and Telegram auth material are sensitive.

## Decision

Structured JSON logs with `correlation_id`, `generation_id`, provider/model, latency, costs. Never log prompts, completions, initData, bearer tokens, or file bytes.

## Consequences

Debugging uses ids + error codes; prompt content retrieved only via authorized ops tools if stored.
