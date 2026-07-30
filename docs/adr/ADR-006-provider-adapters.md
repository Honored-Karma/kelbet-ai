# ADR-006: Provider adapter ports

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Multiple upstream AI vendors; need testability and vendor swap.

## Decision

`GenerationProvider` Protocol with Mock, OpenRouter (text), Runway (image/video). Existing `ChatProvider` remains for bot sync chat. Future OpenAI/Google adapters implement the same port.

## Consequences

Handlers never call vendors directly; contract tests per adapter.
