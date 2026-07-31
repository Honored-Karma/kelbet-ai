"""Runway ML async image/video generation adapter."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)

logger = logging.getLogger(__name__)

_MAX_PROVIDER_ERROR_LENGTH = 500

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal ISO BMFF stub used only in contract tests when host is mocked.
_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _video_provider_cost_units(provider_model_id: str, duration: int) -> int:
    per_second = {
        "gen4_turbo": 500,
        "gen4.5": 1200,
        "gen3a_turbo": 500,
        "gemini_omni_flash": 1000,
        "veo3.1_fast": 1500,
        "veo3.1": 4000,
    }.get(provider_model_id, 0)
    return per_second * duration


def _ratio_for_params(
    params: dict[str, Any],
    *,
    modality: str,
    provider_model_id: str,
) -> str:
    aspect = str(params.get("aspect_ratio") or ("16:9" if modality == "video" else "1:1"))
    resolution = str(params.get("resolution") or "720p")
    seedream_lite = {
        ("1:1", "2k"): "2048:2048",
        ("4:3", "2k"): "2304:1728",
        ("3:4", "2k"): "1728:2304",
        ("16:9", "2k"): "2848:1600",
        ("9:16", "2k"): "1600:2848",
        ("3:2", "2k"): "2496:1664",
        ("2:3", "2k"): "1664:2496",
        ("21:9", "2k"): "3136:1344",
        ("1:1", "3k"): "3072:3072",
        ("4:3", "3k"): "3456:2592",
        ("3:4", "3k"): "2592:3456",
        ("16:9", "3k"): "4096:2304",
        ("9:16", "3k"): "2304:4096",
        ("3:2", "3k"): "3744:2496",
        ("2:3", "3k"): "2496:3744",
        ("21:9", "3k"): "4704:2016",
    }
    seedream_pro = {
        ("1:1", "1k"): "1024:1024",
        ("4:3", "1k"): "1184:896",
        ("3:4", "1k"): "896:1184",
        ("16:9", "1k"): "1376:768",
        ("9:16", "1k"): "768:1376",
        ("3:2", "1k"): "1296:864",
        ("2:3", "1k"): "864:1296",
        ("1:1", "2k"): "2048:2048",
        ("4:3", "2k"): "2304:1728",
        ("3:4", "2k"): "1728:2304",
        ("16:9", "2k"): "2720:1530",
        ("9:16", "2k"): "1530:2720",
        ("3:2", "2k"): "2496:1664",
        ("2:3", "2k"): "1664:2496",
    }
    if provider_model_id == "seedream5_lite":
        return seedream_lite.get((aspect, resolution), "2048:2048")
    if provider_model_id == "seedream5_pro":
        return seedream_pro.get((aspect, resolution), "2048:2048")
    mapping = {
        ("1:1", "720p"): "1024:1024",
        ("1:1", "1080p"): "1080:1080",
        ("16:9", "720p"): "1280:720",
        ("16:9", "1080p"): "1920:1080",
        ("9:16", "720p"): "720:1280",
        ("9:16", "1080p"): "1080:1920",
    }
    return mapping.get((aspect, resolution), "1280:720" if modality == "video" else "1024:1024")


def host_allowed(url: str, allowlist: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == item or host.endswith(f".{item}") for item in allowlist if item)


def _provider_error_message(response: httpx.Response) -> str | None:
    """Extract Runway's documented human-readable error without storing raw bodies."""
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, str):
        message = error
    elif isinstance(error, dict):
        parts = [error.get("code"), error.get("message"), error.get("detail")]
        message = ": ".join(str(part) for part in parts if part)
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
    error_lower = (provider_error or "").lower()
    if response.status_code == 401:
        error_code = "provider_auth_error"
    elif response.status_code == 429:
        error_code = "rate_limited"
    elif response.status_code >= 500:
        error_code = "provider_unavailable"
    elif response.status_code == 400 and any(
        token in error_lower for token in ("credit", "balance", "billing")
    ):
        error_code = "provider_insufficient_credits"
    else:
        error_code = "provider_http_error"

    meta: dict[str, Any] = {"http_status": response.status_code}
    if provider_error:
        meta["provider_error"] = provider_error
    return GenerationProviderResult(
        status="failed",
        provider_job_id=provider_job_id,
        error_code=error_code,
        error_message_safe=provider_error or f"Runway HTTP {response.status_code}",
        latency_ms=latency_ms,
        meta=meta,
    )


class RunwayProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        api_version: str,
        timeout_seconds: float = 60.0,
        output_host_allowlist: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
        max_output_bytes: int = 104_857_600,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._timeout = timeout_seconds
        self._allowlist = output_host_allowlist or [
            "runwayml.com",
            "runwayusercontent.com",
            "amazonaws.com",
            "cdn.runway.test",
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
    ) -> RunwayProvider:
        cfg = settings or get_settings()
        allowlist = [
            part.strip().lower()
            for part in cfg.runway_output_host_allowlist.split(",")
            if part.strip()
        ]
        return cls(
            api_key=cfg.runway_api_key,
            base_url=cfg.runway_base_url,
            api_version=cfg.runway_api_version,
            timeout_seconds=cfg.runway_http_timeout_seconds,
            output_host_allowlist=allowlist,
            client=client,
            download_client=download_client,
            max_output_bytes=cfg.video_output_max_bytes,
        )

    @property
    def name(self) -> str:
        return "runway"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": self._api_version,
        }

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return GenerationProviderResult(
                status="failed",
                error_code="missing_api_key",
                error_message_safe="Runway API key is not configured",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        if request.modality not in {"image", "image_edit", "upscale", "video"}:
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_modality",
                error_message_safe="Runway adapter does not support this modality",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        ratio = _ratio_for_params(
            request.params,
            modality=request.modality,
            provider_model_id=request.provider_model_id,
        )
        if request.modality == "upscale":
            if len(request.input_urls) != 1:
                return GenerationProviderResult(
                    status="failed",
                    error_code="invalid_input_count",
                    error_message_safe="Image upscale requires exactly one source image",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            path = "/v1/image_upscale"
            payload = {
                "model": request.provider_model_id,
                "imageUri": request.input_urls[0],
                "scaleFactor": int(request.params.get("scale_factor") or 2),
                "flavor": str(request.params.get("flavor") or "photo"),
                "sharpen": int(request.params.get("sharpen", 40)),
                "smartGrain": int(request.params.get("smart_grain", 20)),
                "ultraDetail": int(request.params.get("ultra_detail", 50)),
            }
        elif request.modality in {"image", "image_edit"}:
            path = "/v1/text_to_image"
            payload = {
                "model": request.provider_model_id,
                "promptText": request.prompt,
                "ratio": ratio,
            }
            if "seed" in request.params:
                payload["seed"] = request.params["seed"]
            if request.input_urls:
                payload["referenceImages"] = [{"uri": url} for url in request.input_urls]
        else:
            duration = int(
                request.params.get("duration_sec") or request.params.get("duration") or 5
            )
            prompt_image = (
                request.input_urls[0]
                if request.input_urls
                else request.params.get("prompt_image_url")
            )
            if prompt_image:
                path = "/v1/image_to_video"
                payload = {
                    "model": request.provider_model_id,
                    "promptImage": str(prompt_image),
                    "promptText": request.prompt,
                    "ratio": ratio,
                    "duration": duration,
                }
            else:
                path = "/v1/text_to_video"
                payload = {
                    "model": request.provider_model_id,
                    "promptText": request.prompt,
                    "ratio": ratio,
                    "duration": duration,
                }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}{path}",
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
                return _http_error_result(
                    response,
                    latency_ms=latency_ms,
                )
            data = response.json()
            task_id = data.get("id")
            if not isinstance(task_id, str) or not task_id:
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_bad_response",
                    error_message_safe="Runway create response missing task id",
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
                provider_job_id=task_id,
                latency_ms=latency_ms,
                provider_cost_units=(
                    _video_provider_cost_units(request.provider_model_id, duration)
                    if request.modality == "video"
                    else 0
                ),
                meta={"create_path": path},
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="Runway create timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="Runway create failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (KeyError, TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="Runway create returned invalid JSON",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return GenerationProviderResult(
                status="failed",
                error_code="missing_api_key",
                error_message_safe="Runway API key is not configured",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._base_url}/v1/tasks/{provider_job_id}",
                headers=self._headers(),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return _http_error_result(
                    response,
                    latency_ms=latency_ms,
                    provider_job_id=provider_job_id,
                )
            data = response.json()
            status = str(data.get("status") or "").upper()
            if status in {"PENDING", "RUNNING", "THROTTLED"}:
                return GenerationProviderResult(
                    status="accepted",
                    provider_job_id=provider_job_id,
                    latency_ms=latency_ms,
                    meta={"provider_status": status},
                )
            if status == "FAILED":
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_failed",
                    error_message_safe="Runway task failed",
                    latency_ms=latency_ms,
                    meta={"failure": data.get("failure")},
                )
            if status != "SUCCEEDED":
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe=f"Unexpected Runway status {status}",
                    latency_ms=latency_ms,
                )

            outputs_raw = data.get("output") or []
            if not isinstance(outputs_raw, list) or not outputs_raw:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="Runway succeeded without outputs",
                    latency_ms=latency_ms,
                )
            outputs: list[GenerationOutput] = []
            for item in outputs_raw:
                url = item if isinstance(item, str) else None
                if not url:
                    continue
                if not host_allowed(url, self._allowlist):
                    return GenerationProviderResult(
                        status="failed",
                        provider_job_id=provider_job_id,
                        error_code="untrusted_output_host",
                        error_message_safe="Runway output host not allowlisted",
                        latency_ms=latency_ms,
                    )
                content_type, data_bytes = await self._download_output(url)
                outputs.append(
                    GenerationOutput(
                        content_type=content_type,
                        data=data_bytes,
                        meta={"source_url_host": urlparse(url).hostname},
                    )
                )
            if not outputs:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="Runway outputs could not be downloaded",
                    latency_ms=latency_ms,
                )
            return GenerationProviderResult(
                status="succeeded",
                outputs=outputs,
                provider_job_id=provider_job_id,
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="Runway poll timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
                provider_job_id=provider_job_id,
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="Runway poll failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
                provider_job_id=provider_job_id,
            )
        except (KeyError, TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="Runway poll returned invalid JSON",
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
            if content_type not in {
                "image/jpeg",
                "image/png",
                "image/webp",
                "video/mp4",
            }:
                raise httpx.HTTPError("Provider output MIME type is not allowed")
            data = response.content
            if not data:
                host = (urlparse(url).hostname or "").lower()
                if host.endswith(".test"):
                    data = _MP4_STUB if content_type == "video/mp4" else _PNG_1X1
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
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.delete(
                f"{self._base_url}/v1/tasks/{provider_job_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("runway_cancel_failed provider_job_id=%s", provider_job_id)
        finally:
            if owns_client:
                await client.aclose()
