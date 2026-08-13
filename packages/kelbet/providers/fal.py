"""fal.ai queue adapter: one API key, many third-party video models.

Two properties of the fal queue API shape this file.

First, polling is not addressable by request id alone. The status URL is
``/{endpoint_id}/requests/{request_id}/status``, so the endpoint id has to travel
with the job. `GenerationJob` stores a single opaque string, so this adapter packs
both into `provider_job_id` as ``endpoint_id|request_id`` and unpacks on the way
back. `_split_job_id` is the only place that knows the encoding.

Second, the request body is not uniform across models. `duration` is a suffixed
string on Veo and Luma (``"8s"``), a bare numeric string on Kling and Seedance
(``"5"``), and a real integer on Grok and Wan 2.7. Sending the wrong type is a 422,
so every model declares its own encoding in `_FAL_MODELS` rather than the adapter
guessing from the value. The same table carries provider cost, because fal prices
per second on some models and per clip on others.

`_FAL_MODELS` is deliberately a closed allowlist. An endpoint id absent from it is
rejected before any HTTP call: an unknown model would otherwise be billed at zero
recorded cost, which is the one failure mode that silently loses money.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)
from kelbet.providers.runway import host_allowed

logger = logging.getLogger(__name__)

_MAX_PROVIDER_ERROR_LENGTH = 500

# `GenerationJob.provider_job_id` is one column, and fal needs two values to poll.
# A pipe cannot occur in either half: fal endpoint ids are slash-separated slugs and
# request ids are UUIDs.
_JOB_SEPARATOR = "|"

# Minimal ISO BMFF stub, mirroring the Runway adapter, so contract tests can serve a
# mocked host without shipping a real MP4 fixture.
_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"

# Duration encodings accepted by fal model schemas.
_DURATION_SUFFIX = "suffix"  # "8s"
_DURATION_STRING = "string"  # "8"
_DURATION_INT = "int"  # 8


@dataclass(frozen=True, slots=True)
class FalModelSpec:
    """How one fal endpoint wants to be called, and what it costs.

    `cost_units_per_second` and `cost_units_per_clip` are mutually exclusive: fal
    bills Kling and Veo by output second, but Hailuo, Luma and PixVerse by finished
    clip, and rounding a per-clip price into a per-second rate misstates the cost of
    every duration except the base one.

    Costs are keyed by the resolution string the catalog declares, with ``""`` as the
    key for models that expose no resolution parameter at all.
    """

    endpoint_id: str
    duration_format: str
    cost_units_per_second: dict[str, int] = field(default_factory=dict)
    cost_units_per_clip: dict[str, int] = field(default_factory=dict)
    # Request-body field names. `None` means the model has no such knob and the field
    # must be omitted, not sent empty: fal rejects unknown properties on some schemas.
    resolution_field: str | None = None
    aspect_field: str | None = None
    duration_field: str | None = "duration"
    # Image-to-video entry point. fal splits t2v and i2v into separate endpoint ids,
    # so a source image changes the URL, not just the body.
    image_endpoint_id: str | None = None
    image_field: str | None = None
    # Audio is billed separately where it exists, so the default is pinned here rather
    # than left to fal: a schema default flipping to true would double the bill.
    audio_field: str | None = None
    audio_enabled: bool = False

    def endpoint_for(self, *, has_image: bool) -> str | None:
        if not has_image:
            return self.endpoint_id
        return self.image_endpoint_id

    def cost_units(self, *, duration_sec: int, resolution: str | None) -> int:
        key = resolution or ""
        if self.cost_units_per_clip:
            clip = self.cost_units_per_clip.get(f"{key}:{duration_sec}")
            if clip is not None:
                return clip
            # Fall through to the per-second table when a duration is priced
            # linearly above the declared clip lengths.
        per_second = self.cost_units_per_second.get(key)
        if per_second is None:
            per_second = self.cost_units_per_second.get("")
        if per_second is None:
            return 0
        return per_second * duration_sec

    def encode_duration(self, duration_sec: int) -> str | int:
        if self.duration_format == _DURATION_INT:
            return duration_sec
        if self.duration_format == _DURATION_SUFFIX:
            return f"{duration_sec}s"
        return str(duration_sec)


# Every price below is fal's published rate, converted to cost units where
# 1 unit == $0.0001. Models whose published price could not be pinned to a number
# (Gemini Omni is token-metered and quoted "approximately") are absent on purpose:
# an unverifiable cost cannot be sold at a defensible margin.
_FAL_MODELS: dict[str, FalModelSpec] = {
    # $0.15 per 5s at 540p, $0.20 at 720p; 8s clips are exactly double.
    "fal-ai/pixverse/v4.5/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/pixverse/v4.5/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_clip={
            "540p:5": 1500,
            "540p:8": 3000,
            "720p:5": 2000,
            "720p:8": 4000,
        },
        resolution_field="resolution",
        aspect_field="aspect_ratio",
    ),
    # $0.20 per 5s clip, $0.40 per 9s clip. No aspect parameter is documented, so
    # the catalog promises 16:9 only.
    "fal-ai/luma-dream-machine/ray-2-flash": FalModelSpec(
        endpoint_id="fal-ai/luma-dream-machine/ray-2-flash",
        duration_format=_DURATION_SUFFIX,
        cost_units_per_clip={":5": 2000, ":9": 4000},
    ),
    # $0.05/s at 480p, $0.07/s at 720p. Duration is a true integer here.
    "xai/grok-imagine-video/text-to-video": FalModelSpec(
        endpoint_id="xai/grok-imagine-video/text-to-video",
        duration_format=_DURATION_INT,
        cost_units_per_second={"480p": 500, "720p": 700},
        resolution_field="resolution",
        aspect_field="aspect_ratio",
        image_endpoint_id="xai/grok-imagine-video/image-to-video",
        image_field="image_url",
    ),
    # $0.28 per 6s clip, $0.56 per 10s. Fixed 768p, no aspect parameter.
    "fal-ai/minimax/hailuo-2.3/standard/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/minimax/hailuo-2.3/standard/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_clip={"768p:6": 2800, "768p:10": 5600},
    ),
    # $0.05/s at 480p, $0.10/s at 720p, $0.15/s at 1080p.
    "fal-ai/wan-25-preview/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/wan-25-preview/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"480p": 500, "720p": 1000, "1080p": 1500},
        resolution_field="resolution",
        aspect_field="aspect_ratio",
    ),
    # $0.10/s at 720p, $0.15/s at 1080p. Integer duration.
    "fal-ai/wan/v2.7/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/wan/v2.7/text-to-video",
        duration_format=_DURATION_INT,
        cost_units_per_second={"720p": 1000, "1080p": 1500},
        resolution_field="resolution",
        aspect_field="aspect_ratio",
    ),
    # Kling exposes no resolution parameter, so cost is keyed on "".
    # $0.07/s without audio.
    "fal-ai/kling-video/v2.5-turbo/pro/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"": 700},
        aspect_field="aspect_ratio",
        image_endpoint_id="fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        image_field="image_url",
    ),
    # $0.07/s without audio, $0.14/s with. Audio stays off; Veo is the audio route.
    "fal-ai/kling-video/v2.6/pro/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/kling-video/v2.6/pro/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"": 700},
        aspect_field="aspect_ratio",
        image_endpoint_id="fal-ai/kling-video/v2.6/pro/image-to-video",
        image_field="start_image_url",
        audio_field="generate_audio",
        audio_enabled=False,
    ),
    # $0.112/s without audio.
    "fal-ai/kling-video/v3/pro/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/kling-video/v3/pro/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"": 1120},
        aspect_field="aspect_ratio",
        image_endpoint_id="fal-ai/kling-video/v3/pro/image-to-video",
        image_field="start_image_url",
        audio_field="generate_audio",
        audio_enabled=False,
    ),
    # $0.28/s.
    "fal-ai/kling-video/v2.1/master/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/kling-video/v2.1/master/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"": 2800},
        aspect_field="aspect_ratio",
        image_endpoint_id="fal-ai/kling-video/v2.1/master/image-to-video",
        image_field="image_url",
    ),
    # $0.42/s at 4K, audio included.
    "fal-ai/kling-video/o3/4k/text-to-video": FalModelSpec(
        endpoint_id="fal-ai/kling-video/o3/4k/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"": 4200},
        aspect_field="aspect_ratio",
        image_endpoint_id="fal-ai/kling-video/o3/4k/image-to-video",
        image_field="image_url",
    ),
    # $0.2419/s at 720p. Only 720p is declared: the 480p tier is token-metered and
    # its effective rate depends on pixel count, which cannot be pinned per second.
    "bytedance/seedance-2.0/fast/text-to-video": FalModelSpec(
        endpoint_id="bytedance/seedance-2.0/fast/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"720p": 2419},
        resolution_field="resolution",
        aspect_field="aspect_ratio",
    ),
    # $0.3034/s at 720p.
    "bytedance/seedance-2.0/text-to-video": FalModelSpec(
        endpoint_id="bytedance/seedance-2.0/text-to-video",
        duration_format=_DURATION_STRING,
        cost_units_per_second={"720p": 3034},
        resolution_field="resolution",
        aspect_field="aspect_ratio",
    ),
}


def fal_model_spec(provider_model_id: str) -> FalModelSpec | None:
    return _FAL_MODELS.get(provider_model_id)


def fal_endpoint_ids() -> frozenset[str]:
    """Endpoint ids this adapter can call. Used by catalog contract tests."""
    return frozenset(_FAL_MODELS)


def _join_job_id(endpoint_id: str, request_id: str) -> str:
    return f"{endpoint_id}{_JOB_SEPARATOR}{request_id}"


def _split_job_id(provider_job_id: str) -> tuple[str, str] | None:
    endpoint_id, separator, request_id = provider_job_id.rpartition(_JOB_SEPARATOR)
    if not separator or not endpoint_id or not request_id:
        return None
    return endpoint_id, request_id


def _provider_error_message(response: httpx.Response) -> str | None:
    """Pull fal's error text out without ever storing a raw body.

    fal returns FastAPI's shape: `detail` is either a string or a list of
    ``{loc, msg, type}`` validation entries.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    detail = payload.get("detail")
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if not isinstance(item, dict):
                continue
            location = item.get("loc")
            field_name = ".".join(str(part) for part in location) if location else None
            text = str(item.get("msg") or "").strip()
            parts.append(f"{field_name}: {text}" if field_name and text else text)
        message = "; ".join(part for part in parts if part)
    else:
        return None

    normalized = " ".join(message.split())
    return normalized[:_MAX_PROVIDER_ERROR_LENGTH] or None


def _http_error_result(
    response: httpx.Response,
    *,
    latency_ms: int,
    provider_job_id: str | None = None,
) -> GenerationProviderResult:
    provider_error = _provider_error_message(response)
    if response.status_code == 401:
        error_code = "provider_auth_error"
    elif response.status_code == 402:
        # fal documents 402 as insufficient credits on the account. Distinguishing it
        # matters: it is the operator's problem to fix, never the user's prompt.
        error_code = "provider_insufficient_credits"
    elif response.status_code == 429:
        error_code = "rate_limited"
    elif response.status_code == 422:
        error_code = "provider_rejected_params"
    elif response.status_code >= 500:
        error_code = "provider_unavailable"
    else:
        error_code = "provider_http_error"

    meta: dict[str, Any] = {"http_status": response.status_code}
    if provider_error:
        meta["provider_error"] = provider_error
    return GenerationProviderResult(
        status="failed",
        provider_job_id=provider_job_id,
        error_code=error_code,
        error_message_safe=provider_error or f"fal HTTP {response.status_code}",
        latency_ms=latency_ms,
        meta=meta,
    )


def _first_output_url(payload: dict[str, Any]) -> str | None:
    """Locate the output file in a fal result body.

    Video models return ``{"video": {"url": ...}}``; a few return a list under
    ``videos``. Images are handled too so an image SKU can reuse this adapter later.
    """
    video = payload.get("video")
    if isinstance(video, dict):
        url = video.get("url")
        if isinstance(url, str) and url:
            return url

    for key in ("videos", "images"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str) and url:
                    return url
            elif isinstance(item, str) and item:
                return item
    return None


class FalProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        output_host_allowlist: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
        max_output_bytes: int = 104_857_600,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._allowlist = output_host_allowlist or [
            "fal.media",
            "fal.run",
            "cdn.fal.test",
        ]
        self._client = client
        self._download_client = download_client
        self._max_output_bytes = max_output_bytes

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
    ) -> FalProvider:
        cfg = settings or get_settings()
        allowlist = [
            part.strip().lower()
            for part in cfg.fal_output_host_allowlist.split(",")
            if part.strip()
        ]
        return cls(
            api_key=cfg.fal_api_key,
            base_url=cfg.fal_queue_base_url,
            timeout_seconds=cfg.fal_http_timeout_seconds,
            output_host_allowlist=allowlist,
            client=client,
            download_client=download_client,
            max_output_bytes=cfg.video_output_max_bytes,
        )

    @property
    def name(self) -> str:
        return "fal"

    def _headers(self) -> dict[str, str]:
        # fal authenticates with the literal scheme "Key", not "Bearer".
        return {
            "Authorization": f"Key {self._api_key}",
            "Content-Type": "application/json",
        }

    def _missing_key(self, started: float) -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code="missing_api_key",
            error_message_safe="fal API key is not configured",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _build_payload(
        self,
        spec: FalModelSpec,
        request: GenerationRequest,
        *,
        duration_sec: int,
        resolution: str | None,
        image_url: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"prompt": request.prompt}
        if spec.duration_field:
            payload[spec.duration_field] = spec.encode_duration(duration_sec)
        if spec.resolution_field and resolution:
            payload[spec.resolution_field] = resolution
        if spec.aspect_field:
            aspect = request.params.get("aspect_ratio")
            if aspect:
                payload[spec.aspect_field] = str(aspect)
        if spec.audio_field is not None:
            payload[spec.audio_field] = spec.audio_enabled
        if spec.image_field and image_url:
            payload[spec.image_field] = image_url
        seed = request.params.get("seed")
        if seed is not None:
            payload["seed"] = int(seed)
        return payload

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return self._missing_key(started)
        if request.modality != "video":
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_modality",
                error_message_safe="fal adapter currently serves video only",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        if request.extension_video is not None:
            # Only the Veo route chains extensions. Accepting the field here would
            # silently drop the previous clip and bill for an unrelated video.
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_workflow",
                error_message_safe="fal adapter does not extend an existing video",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        spec = _FAL_MODELS.get(request.provider_model_id)
        if spec is None:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_unsupported_model",
                error_message_safe="fal model is not in the adapter allowlist",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        image_url = request.input_urls[0] if request.input_urls else None
        endpoint_id = spec.endpoint_for(has_image=image_url is not None)
        if endpoint_id is None:
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_input_mode",
                error_message_safe="This fal model does not accept a source image",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        duration_sec = int(request.params.get("duration_sec") or 5)
        resolution_raw = request.params.get("resolution")
        # "auto" is the catalog's marker for a model with no resolution knob; it must
        # never reach the wire as a literal value.
        resolution = (
            str(resolution_raw) if resolution_raw and str(resolution_raw) != "auto" else None
        )
        payload = self._build_payload(
            spec,
            request,
            duration_sec=duration_sec,
            resolution=resolution,
            image_url=image_url,
        )
        cost_units = spec.cost_units(duration_sec=duration_sec, resolution=resolution)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}/{endpoint_id}",
                json=payload,
                headers=self._headers(),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                logger.warning(
                    "generation_provider_error provider=%s model=%s "
                    "latency_ms=%s status=%s generation_id=%s",
                    self.name,
                    request.provider_model_id,
                    latency_ms,
                    response.status_code,
                    request.generation_id,
                )
                return _http_error_result(response, latency_ms=latency_ms)
            data = response.json()
            request_id = data.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_bad_response",
                    error_message_safe="fal submit response missing request_id",
                    latency_ms=latency_ms,
                )
            logger.info(
                "generation_accepted provider=%s model=%s latency_ms=%s generation_id=%s",
                self.name,
                request.provider_model_id,
                latency_ms,
                request.generation_id,
            )
            return GenerationProviderResult(
                status="accepted",
                provider_job_id=_join_job_id(endpoint_id, request_id),
                latency_ms=latency_ms,
                provider_cost_units=cost_units,
                meta={"endpoint_id": endpoint_id},
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="fal submit timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="fal submit failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (KeyError, TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="fal submit returned invalid JSON",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return self._missing_key(started)

        parts = _split_job_id(provider_job_id)
        if parts is None:
            return GenerationProviderResult(
                status="failed",
                provider_job_id=provider_job_id,
                error_code="provider_bad_job_id",
                error_message_safe="fal job id is missing its endpoint",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        endpoint_id, request_id = parts
        request_root = f"{self._base_url}/{endpoint_id}/requests/{request_id}"

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(f"{request_root}/status", headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return _http_error_result(
                    response,
                    latency_ms=latency_ms,
                    provider_job_id=provider_job_id,
                )
            status = str(response.json().get("status") or "").upper()
            if status in {"IN_QUEUE", "IN_PROGRESS"}:
                return GenerationProviderResult(
                    status="accepted",
                    provider_job_id=provider_job_id,
                    latency_ms=latency_ms,
                    meta={"provider_status": status},
                )
            if status in {"FAILED", "ERROR"}:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_failed",
                    error_message_safe="fal job failed",
                    latency_ms=latency_ms,
                    meta={"provider_status": status},
                )
            if status == "CANCELED":
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_cancelled",
                    error_message_safe="fal job was cancelled",
                    latency_ms=latency_ms,
                )
            if status != "COMPLETED":
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe=f"Unexpected fal status {status}",
                    latency_ms=latency_ms,
                )

            result = await client.get(request_root, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if result.status_code >= 400:
                return _http_error_result(
                    result,
                    latency_ms=latency_ms,
                    provider_job_id=provider_job_id,
                )
            body = result.json()
            if not isinstance(body, dict):
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="fal result body is not an object",
                    latency_ms=latency_ms,
                )
            url = _first_output_url(body)
            if not url:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="fal completed without an output URL",
                    latency_ms=latency_ms,
                )
            if not host_allowed(url, self._allowlist):
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="untrusted_output_host",
                    error_message_safe="fal output host not allowlisted",
                    latency_ms=latency_ms,
                )
            content_type, data_bytes = await self._download_output(url)
            return GenerationProviderResult(
                status="succeeded",
                outputs=[
                    GenerationOutput(
                        content_type=content_type,
                        data=data_bytes,
                        meta={"source_url_host": urlparse(url).hostname},
                    )
                ],
                provider_job_id=provider_job_id,
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="fal poll timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
                provider_job_id=provider_job_id,
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="fal poll failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
                provider_job_id=provider_job_id,
            )
        except (KeyError, TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="fal poll returned invalid JSON",
                latency_ms=int((time.perf_counter() - started) * 1000),
                provider_job_id=provider_job_id,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def _download_output(self, url: str) -> tuple[str, bytes]:
        owns = self._download_client is None
        client = self._download_client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(url)
            response.raise_for_status()
            content_type = (
                (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            )
            if not content_type or content_type == "application/octet-stream":
                suffix = urlparse(url).path.lower()
                content_type = (
                    "video/mp4"
                    if suffix.endswith(".mp4")
                    else "image/jpeg"
                    if suffix.endswith((".jpg", ".jpeg"))
                    else "image/webp"
                    if suffix.endswith(".webp")
                    else "image/png"
                )
            if content_type not in {"image/jpeg", "image/png", "image/webp", "video/mp4"}:
                raise httpx.HTTPError("Provider output MIME type is not allowed")
            data = response.content
            if not data:
                host = (urlparse(url).hostname or "").lower()
                if host.endswith(".test"):
                    data = _MP4_STUB
                else:
                    raise httpx.HTTPError("Provider returned an empty output")
            if len(data) > self._max_output_bytes:
                raise httpx.HTTPError("Provider output exceeds configured size limit")
            if content_type == "video/mp4" and b"ftyp" not in data[:32]:
                raise httpx.HTTPError("Provider output is not a valid MP4")
            return content_type, data
        finally:
            if owns:
                await client.aclose()

    async def cancel(self, provider_job_id: str) -> None:
        if not self._api_key:
            return
        parts = _split_job_id(provider_job_id)
        if parts is None:
            return
        endpoint_id, request_id = parts
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.put(
                f"{self._base_url}/{endpoint_id}/requests/{request_id}/cancel",
                headers=self._headers(),
            )
            # 409 means the job already finished, which is not a cancellation failure.
            if response.status_code == 409:
                return
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("fal_cancel_failed provider_job_id=%s", provider_job_id)
        finally:
            if owns_client:
                await client.aclose()
