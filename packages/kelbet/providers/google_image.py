"""Google Gemini Interactions adapter for synchronous image generation and editing."""

from __future__ import annotations

import base64
import binascii
import time
from typing import Any

import httpx

from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)

_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ASPECT_RATIOS = {
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
}
_SIZE_ALIASES = {
    "512": "512",
    "0.5k": "512",
    "720p": "1K",
    "1080p": "1K",
    "1k": "1K",
    "2k": "2K",
    "3k": "2K",
    "4k": "4K",
}
_COST_UNITS = {"512": 450, "1K": 670, "2K": 1010, "4K": 1510}


def google_image_size(params: dict[str, Any]) -> str | None:
    value = str(params.get("resolution") or params.get("image_size") or "1k").strip().lower()
    return _SIZE_ALIASES.get(value)


def google_image_cost_units(params: dict[str, Any]) -> int:
    size = google_image_size(params)
    return _COST_UNITS.get(size or "", 0)


def _looks_like_image(content_type: str, payload: bytes) -> bool:
    if content_type == "image/png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return payload.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    return False


def _image_blocks(value: object) -> list[dict[str, Any]]:
    """Collect only typed image blocks; never retain the provider response."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") == "image" and isinstance(value.get("data"), str):
            found.append(value)
        for child in value.values():
            found.extend(_image_blocks(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_image_blocks(child))
    return found


def _usage_tokens(data: dict[str, Any], key: str) -> int | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and value >= 0 else None


class GoogleGeminiImageProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_output_bytes: int = 20_971_520,
        client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._client = client
        self._download_client = download_client

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        download_client: httpx.AsyncClient | None = None,
    ) -> GoogleGeminiImageProvider:
        cfg = settings or get_settings()
        return cls(
            api_key=cfg.google_api_key,
            base_url=cfg.google_image_base_url,
            timeout_seconds=float(cfg.google_image_timeout_seconds),
            max_output_bytes=cfg.google_image_max_output_bytes,
            client=client,
            download_client=download_client,
        )

    @property
    def name(self) -> str:
        return "google"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return self._failure("missing_api_key", "Google API key is not configured", started)
        if request.modality == "upscale":
            return self._failure(
                "unsupported_capability",
                "Google image fallback does not provide deterministic upscale",
                started,
            )
        if request.modality not in {"image", "image_edit"}:
            return self._failure(
                "unsupported_modality",
                "Google image adapter does not support this modality",
                started,
            )
        if request.modality == "image_edit" and not request.input_urls:
            return self._failure(
                "invalid_input_count", "Google image edit requires a source image", started
            )
        if len(request.input_urls) > 10:
            return self._failure(
                "invalid_input_count", "Google image fallback accepts at most 10 images", started
            )

        aspect_ratio = str(request.params.get("aspect_ratio") or "1:1")
        image_size = google_image_size(request.params)
        if aspect_ratio not in _ASPECT_RATIOS or image_size is None:
            return self._failure(
                "unsupported_capability",
                "Requested image shape or size is unsupported by Google",
                started,
            )

        inputs: list[dict[str, str]] = [{"type": "text", "text": request.prompt}]
        try:
            for url in request.input_urls:
                content_type, image_bytes = await self._load_input_image(url)
                inputs.append(
                    {
                        "type": "image",
                        "mime_type": content_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    }
                )
        except (httpx.HTTPError, ValueError, binascii.Error):
            return self._failure(
                "input_download_failed", "Could not prepare the source image for Google", started
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}/interactions",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                json={
                    "model": request.provider_model_id,
                    "input": inputs,
                    "response_format": {
                        "type": "image",
                        "aspect_ratio": aspect_ratio,
                        "image_size": image_size,
                    },
                },
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return self._http_failure(response.status_code, latency_ms=latency_ms)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Interaction response must be an object")
            status = data.get("status")
            if status not in {None, "completed"}:
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_rejected",
                    error_message_safe="Google did not complete the image request",
                    latency_ms=latency_ms,
                    meta={"http_status": response.status_code, "provider_status": str(status)[:32]},
                )
            blocks = _image_blocks(data)
            if not blocks:
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_bad_response",
                    error_message_safe="Google image response did not contain an image",
                    latency_ms=latency_ms,
                    meta={"http_status": response.status_code},
                )
            block = blocks[-1]
            content_type = str(block.get("mime_type") or "image/png").lower()
            if content_type not in _IMAGE_MIME_TYPES:
                raise ValueError("Unsupported output MIME")
            output = base64.b64decode(str(block["data"]), validate=True)
            if not output or len(output) > self._max_output_bytes:
                raise ValueError("Invalid output size")
            if not _looks_like_image(content_type, output):
                raise ValueError("Output content does not match MIME")
            return GenerationProviderResult(
                status="succeeded",
                outputs=[GenerationOutput(content_type=content_type, data=output)],
                latency_ms=latency_ms,
                provider_cost_units=_COST_UNITS[image_size],
                meta={
                    "http_status": response.status_code,
                    "provider_status": "completed",
                    "tokens_in": _usage_tokens(data, "input_tokens"),
                    "tokens_out": _usage_tokens(data, "output_tokens"),
                },
            )
        except httpx.TimeoutException:
            return self._failure("provider_timeout", "Google image request timed out", started)
        except httpx.HTTPError:
            return self._failure("provider_http_error", "Google image request failed", started)
        except (binascii.Error, KeyError, TypeError, ValueError):
            return self._failure(
                "provider_bad_response", "Google image response could not be processed", started
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        del provider_job_id
        return GenerationProviderResult(
            status="failed",
            error_code="unsupported_sync_operation",
            error_message_safe="Google image generation is synchronous",
        )

    async def cancel(self, provider_job_id: str) -> None:
        del provider_job_id

    async def _load_input_image(self, url: str) -> tuple[str, bytes]:
        if url.startswith("data:"):
            header, separator, payload = url.partition(",")
            if not separator or ";base64" not in header:
                raise ValueError("Unsupported data URI")
            content_type = header[5:].split(";", 1)[0].strip().lower()
            if content_type not in _IMAGE_MIME_TYPES:
                raise ValueError("Unsupported image MIME")
            image = base64.b64decode(payload, validate=True)
        else:
            owns_client = self._download_client is None
            client = self._download_client or httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            )
            try:
                response = await client.get(url)
                response.raise_for_status()
                content_type = (
                    (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                )
                image = response.content
            finally:
                if owns_client:
                    await client.aclose()
        if content_type not in _IMAGE_MIME_TYPES or not image:
            raise ValueError("Invalid source image")
        if len(image) > self._max_output_bytes or not _looks_like_image(content_type, image):
            raise ValueError("Source image is invalid or too large")
        return content_type, image

    @staticmethod
    def _failure(code: str, message: str, started: float) -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code=code,
            error_message_safe=message,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _http_failure(status_code: int, *, latency_ms: int) -> GenerationProviderResult:
        if status_code in {408, 429}:
            error_code = "rate_limited" if status_code == 429 else "provider_timeout"
        elif status_code >= 500:
            error_code = "provider_unavailable"
        elif status_code in {401, 403}:
            error_code = "provider_account_error"
        elif status_code == 404:
            error_code = "unsupported_capability"
        else:
            error_code = "invalid_input"
        return GenerationProviderResult(
            status="failed",
            error_code=error_code,
            error_message_safe=f"Google image request HTTP {status_code}",
            latency_ms=latency_ms,
            meta={"http_status": status_code},
        )
