# KELBET AI — Studio Video Operations

Status: Stage 4 production-hardening implemented  
Updated: 30 July 2026

## Product contract

The user chooses a task instead of a provider:

- text-to-video;
- photo-to-video with one starting frame;
- Smart, Fast, or Quality;
- landscape `16:9` or portrait `9:16`;
- 4 or 8 seconds;
- exact credit price and ETA before launch.

Both visible modes produce 720p MP4 with native provider audio when the selected
model supports it. The UI never exposes the fallback provider in Simple mode.

## Provider routes

| Studio tier | Primary route | Independent fallback | 4s user price | 8s user price |
|---|---|---|---:|---:|
| Fast | Runway `gemini_omni_flash` | Google `veo-3.1-lite-generate-preview` | 100 | 200 |
| Quality | Runway `gen4.5` | Google `veo-3.1-lite-generate-preview` | 120 | 240 |

The deprecated `gen3a_turbo` SKU is disabled and points to the Fast replacement.

Provider prices and capabilities were verified against:

- Runway API: <https://docs.dev.runwayml.com/api/>
- Runway pricing: <https://docs.dev.runwayml.com/guides/pricing/>
- Google Veo API: <https://ai.google.dev/gemini-api/docs/veo>
- Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>

## Request mapping

Catalog quote params:

```json
{
  "aspect_ratio": "9:16",
  "resolution": "720p",
  "duration_sec": 4
}
```

Runway:

- no source image → `POST /v1/text_to_video`;
- one source image → `POST /v1/image_to_video`;
- the private source is passed through a short-lived signed GET URL.

Google Veo:

- `POST /v1beta/models/{model}:predictLongRunning`;
- source image is downloaded server-side and sent as base64 `inlineData`;
- the long-running operation name is stored as `provider_job_id`;
- output URI is allowlisted and downloaded immediately into KELBET private storage.

## Lifecycle and money

```text
quote → reserve → queued → submitting → running → finalizing → capture
                     ├─ cancel ───────────────────────────────→ release
                     ├─ timeout ──────────────────────────────→ release
                     └─ transient provider failure
                            ├─ allowed fallback → running
                            └─ no safe fallback → release
```

Fallback is permitted only for temporary provider errors:

- timeout;
- rate limit;
- unavailable/5xx;
- transport failure with no reliable status.

Moderation failures, invalid input, and other permanent errors never switch
providers. This prevents fallback from becoming a moderation bypass.

Each visible model defines a provider cost ceiling per output second. The Google
fallback is started only when its expected cost is at or below this ceiling.
The user price never changes after the quote is reserved.

Provider usage stores the expected primary or fallback cost even when a poll
response does not repeat billing metadata.

## Reliability controls

- dedicated `kelbet:video` queue with concurrency 2;
- one active video generation per user;
- Runway polling every 5 seconds plus per-job jitter;
- signed Google `video.generated` callback with five-minute replay protection;
- atomic `(provider, event_id)` callback deduplication;
- fast callback acknowledgement before provider polling or output download;
- 30-minute video deadline;
- immediate worker wake-up after a running cancel request;
- generic secret-protected webhook intake remains available for internal providers;
- MP4 magic-header and 100 MiB output ceiling;
- output hostname allowlists for both providers;
- automatic Telegram notification on success;
- release of the credit reservation on fail, cancel, or timeout.

## Deployment requirements

```env
RUNWAY_API_KEY=...
GOOGLE_API_KEY=...
STORAGE_BACKEND=s3
S3_*=...
WEBHOOK_SECRET=...
GOOGLE_WEBHOOK_SIGNING_SECRETS=whsec_...
```

Before production traffic:

1. verify bucket CORS for Mini App uploads;
2. set real provider keys and host allowlists;
3. register the signed Google `video.generated` static webhook;
4. run and pass the automated 100-job reliability and financial reconciliation;
5. confirm that real output sizes remain below the configured ceiling.

The exact rollout and rollback procedure is documented in
[`VIDEO_PRODUCTION_GATE.md`](./VIDEO_PRODUCTION_GATE.md).
