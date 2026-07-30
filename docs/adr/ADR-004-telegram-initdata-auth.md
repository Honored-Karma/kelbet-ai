# ADR-004: Telegram initData-only Mini App auth

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Mini App must authenticate users without trusting client-side Telegram fields.

## Decision

Validate raw `initData` HMAC server-side; check `auth_date`; reject replays; ignore `initDataUnsafe`. Issue short-lived opaque session tokens (hash stored server-side).

## Consequences

Slightly more backend work; strong anti-spoofing. JWT optional later if needed for multi-service.
