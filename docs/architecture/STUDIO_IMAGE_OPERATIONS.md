# KELBET Studio: image operations contract

Status: implemented MVP contract  
Date: 30 July 2026

## Product operations

| Operation | Catalog modality | Fast | Quality | Input |
|---|---|---|---|---|
| Create | `image` | Seedream 5 Lite | Seedream 5 Pro | prompt |
| Edit | `image_edit` | Seedream 5 Lite | Seedream 5 Pro | prompt + 1–10 ordered images |
| Upscale 2× | `upscale` | — | Magnific Precision Upscaler v2 | exactly one image |

Provider names are hidden in Simple mode. They remain available in Pro controls and
in internal usage records.

## Smart selection

Smart is a catalog-driven client resolver, not a fake model:

- use Quality when the prompt contains at least 600 characters;
- use Quality when Edit contains at least four references;
- use Fast otherwise;
- always request a new server quote after the resolved SKU or parameters change.

The server remains authoritative for model availability, accepted parameters, price,
input count, ownership, MIME, file size, and balance.

## Multi-reference rules

- Reference order is stable from the Mini App through `input_asset_ids`, signed URLs,
  and the provider `referenceImages` array.
- Duplicate IDs are rejected.
- Only owned, ready, non-expired input/output assets are accepted.
- Seedream models are capped at ten references in KELBET even where a provider model
  allows more. This keeps the UI, prompt semantics, and request size predictable.
- Users may refer to inputs as Figure 1, Figure 2, and so on.

## Upscale cost guard

Runway bills Magnific image upscale at a much higher tier when the output exceeds
4096 pixels. KELBET therefore exposes only 2× in this contract and accepts sources
up to 2048×2048.

Image width and height are read from a bounded header during upload and stored on
`generation_assets`. Generated outputs receive the same metadata. Older assets are
hydrated lazily when a secure download is requested. If dimensions cannot be
verified, Upscale is rejected before credits are reserved.

## Provider endpoints

- Create/Edit: `POST /v1/text_to_image`
- Upscale: `POST /v1/image_upscale`
- Poll: `GET /v1/tasks/{id}`
- Cancel: `DELETE /v1/tasks/{id}`

Provider output URLs are treated as ephemeral: the worker downloads results and
stores them in KELBET private storage before capturing credits.

Official references:

- [Runway API reference](https://docs.dev.runwayml.com/api/)
- [Runway model catalog](https://docs.dev.runwayml.com/guides/models/)
- [Runway pricing](https://docs.dev.runwayml.com/guides/pricing/)
- [Runway input limits](https://docs.dev.runwayml.com/assets/inputs/)

## Quote and wallet behavior

1. Catalog capabilities normalize and validate parameters.
2. The API creates a ten-minute immutable quote.
3. Generation validates prompt and assets against the quoted model.
4. Credits are reserved before enqueue.
5. Success stores outputs and captures the reservation.
6. Failure, cancellation, or timeout releases the reservation.

Upscale defaults:

- `scale_factor = 2`
- `flavor = photo`
- `sharpen = 40`
- `smart_grain = 20`
- `ultra_detail = 50`

All values are included in the quote snapshot and request hash.
