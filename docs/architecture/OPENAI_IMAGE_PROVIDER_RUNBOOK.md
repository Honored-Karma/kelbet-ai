# OpenAI GPT Image 2: controlled rollout runbook

## Scope and safe default

The `openai` adapter supports synchronous `image` generation and `image_edit` through
GPT Image 2. The catalog exposes two **generation-only** candidates: `Fast` (`low` quality)
and `Quality` (`medium` quality). Both are behind the database feature flag
`openai_image=false` by default, so neither can be quoted nor submitted before an operator
explicitly enables the route.

No image-edit SKU is exposed yet. Editing can include high-fidelity input-image token costs,
so a public price must not be enabled until those costs have been measured and reconciled.

## Configuration

Set these only in the secret store or deployment environment; never commit a key:

```text
OPENAI_IMAGE_API_KEY=...
OPENAI_IMAGE_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_TIMEOUT_SECONDS=120
OPENAI_IMAGE_MAX_OUTPUT_BYTES=20971520
```

The adapter sends a per-generation `Idempotency-Key`, accepts only PNG/JPEG/WebP reference
images, limits request references to ten, validates output bytes as PNG, and stores only safe
status metadata. It never stores a raw upstream response, prompt revision, API key, or provider
error body.

## Pricing guardrail

`provider_cost_units` is a conservative output-cost ceiling in USD micros for the published
square 1k presets: `Fast=600` and `Quality=5300`. These are not user prices. The server quote
remains authoritative. The route must not enable a different quality, source-image operation, or
region until its observed invoices and output characteristics have a separate approved ceiling.

## Canary procedure

1. Keep `openai_image=false` and both catalog candidates disabled for general users.
2. Configure the key in staging, then run generation and malformed-response contract checks with
   a dedicated test account. Confirm no prompt, reference, key, or raw error reaches logs.
3. Compare recorded `provider_usage` against the provider invoice and inspect latency, error
   classes, output dimensions, moderation decisions, and quote/ledger reconciliation.
4. Enable the flag and one catalog candidate for a small operator-managed allowlist only. Keep a
   fixed spend ceiling and an on-call owner.
5. Promote gradually only after the agreed quality/cost threshold and support review are met.

## Rollback

Set `openai_image=false` first, then disable the catalog candidates. Do not alter historic
quotes or jobs: their immutable routing snapshot preserves the price and route selected at
creation. Investigate any in-flight item through its safe attempt/usage records, then rotate the
key if compromise is suspected.
