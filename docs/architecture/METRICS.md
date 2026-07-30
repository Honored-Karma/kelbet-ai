# Metrics naming (noop default)

Default implementation: `NoopMetrics` via `kelbet.observability.get_metrics()`.

## Counters

| Name | Tags | When |
|------|------|------|
| `auth.telegram.ok` | — | Successful Mini App auth |
| `auth.telegram.fail` | `reason` | Failed initData / replay |
| `generation.created` | `modality`, `provider` | Job queued |
| `generation.terminal` | `status`, `modality` | succeeded/failed/cancelled/timed_out |
| `wallet.reserve` | — | Soft-hold created |
| `wallet.capture` | — | Hold captured |
| `wallet.release` | — | Hold released |
| `rate_limit.hit` | `scope` | 429 path |

## Histograms

| Name | Unit | Tags |
|------|------|------|
| `generation.latency_ms` | ms | `provider`, `modality` |
| `provider.http_latency_ms` | ms | `provider` |

Wire Prometheus later by replacing the global metrics backend with `set_metrics(...)`.
