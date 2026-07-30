# ADR-007: R2 for assets

**Status:** Accepted  
**Date:** 2026-07-30

## Context

User uploads and generation outputs need durable private storage.

## Decision

Cloudflare R2 (S3-compatible): presigned PUT uploads, magic-byte validation, UUID object keys. No fetching of arbitrary user URLs (anti-SSRF). Temp inputs vs permanent outputs with retention.

## Consequences

Local MinIO for dev; production private buckets + short-lived GET URLs.
