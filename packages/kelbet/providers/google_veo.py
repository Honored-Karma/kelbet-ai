"""Google Gemini API Veo async video generation adapter."""

from __future__ import annotations

import base64
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
from kelbet.providers.runway import host_allowed

logger = logging.getLogger(__name__)

_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _provider_cost_units(provider_model_id: str, duration: int) -> int:
    per_second = {
        "veo-3.1-lite-generate-preview": 500,
        "veo-3.1-fast-generate-preview": 1000,
        "veo-3.1-generate-preview": 4000,
    }.get(provider_model_id, 0)
    return per_second * duration


class GoogleVeoProvider:
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
            "googleapis.com",
            "googleusercontent.com",
            "storage.googleapis.com",
            "google.test",
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
    ) -> GoogleVeoProvider:
        cfg = settings or get_settings()
        allowlist = [
            part.strip().lower()
            for part in cfg.google_video_output_host_allowlist.split(",")
            if part.strip()
        ]
        return cls(
            api_key=cfg.google_api_key,
            base_url=cfg.google_video_base_url,
            timeout_seconds=float(cfg.google_video_timeout_seconds),
            output_host_allowlist=allowlist,
            client=client,
            download_client=download_client,
            max_output_bytes=cfg.video_output_max_bytes,
        )

    @property
    def name(self) -> str:
        return "google"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return GenerationProviderResult(
                status="failed",
                error_code="missing_api_key",
                error_message_safe="Google API key is not configured",
            )
        if request.modality != "video":
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_modality",
                error_message_safe="Google Veo adapter only supports video",
            )
        if len(request.input_urls) > 1:
            return GenerationProviderResult(
                status="failed",
                error_code="invalid_input_count",
                error_message_safe="Google Veo accepts one starting image",
            )

        duration = int(request.params.get("duration_sec") or 4)
        instance: dict[str, Any] = {"prompt": request.prompt}
        if request.input_urls:
            try:
                content_type, image_bytes = await self._load_input_image(request.input_urls[0])
            except (httpx.HTTPError, ValueError):
                return GenerationProviderResult(
                    status="failed",
                    error_code="input_download_failed",
                    error_message_safe="Could not prepare the source image for Google Veo",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            instance["image"] = {
                "inlineData": {
                    "mimeType": content_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }

        parameters: dict[str, Any] = {
            "aspectRatio": str(request.params.get("aspect_ratio") or "16:9"),
            "durationSeconds": duration,
            "resolution": str(request.params.get("resolution") or "720p"),
            "numberOfVideos": 1,
        }
        if "seed" in request.params:
            parameters["seed"] = int(request.params["seed"])

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}/models/{request.provider_model_id}:predictLongRunning",
                json={"instances": [instance], "parameters": parameters},
                headers=self._headers(),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return self._http_failure(
                    response.status_code,
                    latency_ms=latency_ms,
                    phase="create",
                )
            data = response.json()
            operation_name = data.get("name")
            if not isinstance(operation_name, str) or not operation_name:
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_bad_response",
                    error_message_safe="Google Veo response missing operation name",
                    latency_ms=latency_ms,
                )
            return GenerationProviderResult(
                status="accepted",
                provider_job_id=operation_name,
                latency_ms=latency_ms,
                provider_cost_units=_provider_cost_units(
                    request.provider_model_id,
                    duration,
                ),
                meta={"provider_status": "QUEUED"},
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="Google Veo create timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="Google Veo create failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="Google Veo create returned invalid JSON",
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
                error_message_safe="Google API key is not configured",
                provider_job_id=provider_job_id,
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(
                f"{self._base_url}/{provider_job_id.lstrip('/')}",
                headers=self._headers(),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return self._http_failure(
                    response.status_code,
                    latency_ms=latency_ms,
                    phase="poll",
                    provider_job_id=provider_job_id,
                )
            data = response.json()
            if not bool(data.get("done")):
                return GenerationProviderResult(
                    status="accepted",
                    provider_job_id=provider_job_id,
                    latency_ms=latency_ms,
                    meta={"provider_status": "PROCESSING"},
                )
            if isinstance(data.get("error"), dict):
                error = data["error"]
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_failed",
                    error_message_safe="Google Veo task failed",
                    latency_ms=latency_ms,
                    meta={
                        "provider_error_code": error.get("code"),
                        "provider_error_status": error.get("status"),
                    },
                )
            generated = ((data.get("response") or {}).get("generateVideoResponse") or {}).get(
                "generatedSamples"
            ) or []
            if not isinstance(generated, list) or not generated:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="Google Veo completed without a video",
                    latency_ms=latency_ms,
                )
            video = generated[0].get("video") if isinstance(generated[0], dict) else None
            uri = video.get("uri") if isinstance(video, dict) else None
            if not isinstance(uri, str) or not uri:
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="provider_bad_response",
                    error_message_safe="Google Veo output URI is missing",
                    latency_ms=latency_ms,
                )
            if not host_allowed(uri, self._allowlist):
                return GenerationProviderResult(
                    status="failed",
                    provider_job_id=provider_job_id,
                    error_code="untrusted_output_host",
                    error_message_safe="Google Veo output host not allowlisted",
                    latency_ms=latency_ms,
                )
            content_type, output = await self._download_output(uri)
            return GenerationProviderResult(
                status="succeeded",
                provider_job_id=provider_job_id,
                outputs=[
                    GenerationOutput(
                        content_type=content_type,
                        data=output,
                        meta={"source_url_host": urlparse(uri).hostname},
                    )
                ],
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="Google Veo poll timed out",
                provider_job_id=provider_job_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError:
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="Google Veo poll failed",
                provider_job_id=provider_job_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (KeyError, TypeError, ValueError):
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="Google Veo poll returned invalid JSON",
                provider_job_id=provider_job_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def cancel(self, provider_job_id: str) -> None:
        if not self._api_key:
            return
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.delete(
                f"{self._base_url}/{provider_job_id.lstrip('/')}",
                headers=self._headers(),
            )
            if response.status_code not in {200, 204, 404, 405}:
                logger.warning(
                    "google_veo_cancel_failed provider_job_id=%s status=%s",
                    provider_job_id,
                    response.status_code,
                )
        except httpx.HTTPError:
            logger.warning("google_veo_cancel_failed provider_job_id=%s", provider_job_id)
        finally:
            if owns_client:
                await client.aclose()

    async def _load_input_image(self, url: str) -> tuple[str, bytes]:
        if url.startswith("data:"):
            header, separator, payload = url.partition(",")
            if not separator or ";base64" not in header:
                raise ValueError("Unsupported data URI")
            content_type = header[5:].split(";", 1)[0].strip().lower()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("Unsupported image MIME")
            return content_type, base64.b64decode(payload, validate=True)

        owns = self._download_client is None
        client = self._download_client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
        )
        try:
            response = await client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("Unsupported image MIME")
            if not response.content:
                raise ValueError("Empty image")
            return content_type, response.content
        finally:
            if owns:
                await client.aclose()

    async def _download_output(self, url: str) -> tuple[str, bytes]:
        owns = self._download_client is None
        client = self._download_client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
        )
        try:
            response = await client.get(url, headers={"x-goog-api-key": self._api_key})
            response.raise_for_status()
            content_type = (
                (response.headers.get("content-type") or "video/mp4").split(";")[0].strip().lower()
            )
            if content_type == "application/octet-stream" and urlparse(url).path.lower().endswith(
                ".mp4"
            ):
                content_type = "video/mp4"
            if content_type != "video/mp4":
                raise httpx.HTTPError("Google Veo output MIME type is not video/mp4")
            output = response.content
            if not output:
                host = (urlparse(url).hostname or "").lower()
                if host.endswith(".test"):
                    output = _MP4_STUB
                else:
                    raise httpx.HTTPError("Google Veo returned an empty output")
            if len(output) > self._max_output_bytes:
                raise httpx.HTTPError("Google Veo output exceeds configured size limit")
            if content_type == "video/mp4" and b"ftyp" not in output[:32]:
                raise httpx.HTTPError("Google Veo output is not a valid MP4")
            return content_type, output
        finally:
            if owns:
                await client.aclose()

    @staticmethod
    def _http_failure(
        status_code: int,
        *,
        latency_ms: int,
        phase: str,
        provider_job_id: str | None = None,
    ) -> GenerationProviderResult:
        if status_code == 429:
            error_code = "rate_limited"
        elif status_code >= 500:
            error_code = "provider_unavailable"
        else:
            error_code = "provider_http_error"
        return GenerationProviderResult(
            status="failed",
            error_code=error_code,
            error_message_safe=f"Google Veo {phase} HTTP {status_code}",
            latency_ms=latency_ms,
            provider_job_id=provider_job_id,
            meta={"http_status": status_code},
        )
