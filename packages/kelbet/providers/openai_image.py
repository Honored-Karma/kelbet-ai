"""OpenAI GPT Image synchronous adapter for safe image generation and editing."""

from __future__ import annotations

import base64
import binascii
import time

import httpx

from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)

_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_SIZE_BY_ASPECT = {
    "1:1": "1024x1024",
    "16:9": "1280x720",
    "9:16": "720x1280",
}
_QUALITY_COST_UNITS = {"low": 600, "medium": 5300, "high": 21_100}


def _looks_like_image(content_type: str, payload: bytes) -> bool:
    if content_type == "image/png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return payload.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    return False


class OpenAIImageProvider:
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
    ) -> OpenAIImageProvider:
        cfg = settings or get_settings()
        return cls(
            api_key=cfg.openai_image_api_key,
            base_url=cfg.openai_image_base_url,
            timeout_seconds=float(cfg.openai_image_timeout_seconds),
            max_output_bytes=cfg.openai_image_max_output_bytes,
            client=client,
            download_client=download_client,
        )

    @property
    def name(self) -> str:
        return "openai"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return self._failure(
                "missing_api_key", "OpenAI image API key is not configured", started
            )
        if request.modality not in {"image", "image_edit"}:
            return self._failure(
                "unsupported_modality",
                "OpenAI image adapter does not support this modality",
                started,
            )
        if request.modality == "image_edit" and not request.input_urls:
            return self._failure(
                "invalid_input_count", "OpenAI image edit requires a source image", started
            )
        if len(request.input_urls) > 10:
            return self._failure(
                "invalid_input_count", "OpenAI image edit accepts at most 10 images", started
            )

        aspect_ratio = str(request.params.get("aspect_ratio") or "1:1")
        size = _SIZE_BY_ASPECT.get(aspect_ratio)
        quality = str(request.params.get("flavor") or "medium").lower()
        if size is None or quality not in _QUALITY_COST_UNITS:
            return self._failure(
                "unsupported_capability", "Requested image shape or quality is unsupported", started
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Idempotency-Key": str(request.generation_id),
            }
            if request.modality == "image":
                response = await client.post(
                    f"{self._base_url}/images/generations",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": request.provider_model_id,
                        "prompt": request.prompt,
                        "n": 1,
                        "size": size,
                        "quality": quality,
                    },
                )
            else:
                files = []
                for index, url in enumerate(request.input_urls):
                    content_type, image = await self._load_input_image(url)
                    extension = content_type.rsplit("/", 1)[-1].replace("jpeg", "jpg")
                    files.append(
                        ("image[]", (f"reference-{index}.{extension}", image, content_type))
                    )
                response = await client.post(
                    f"{self._base_url}/images/edits",
                    headers=headers,
                    data={
                        "model": request.provider_model_id,
                        "prompt": request.prompt,
                        "n": "1",
                        "size": size,
                        "quality": quality,
                    },
                    files=files,
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return self._http_failure(response.status_code, latency_ms=latency_ms)
            return self._parse_response(response, latency_ms=latency_ms, quality=quality)
        except httpx.TimeoutException:
            return self._failure("provider_timeout", "OpenAI image request timed out", started)
        except httpx.HTTPError:
            return self._failure("provider_http_error", "OpenAI image request failed", started)
        except (binascii.Error, KeyError, TypeError, ValueError):
            return self._failure(
                "provider_bad_response", "OpenAI image response could not be processed", started
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        del provider_job_id
        return GenerationProviderResult(
            status="failed",
            error_code="unsupported_sync_operation",
            error_message_safe="OpenAI image generation is synchronous",
        )

    async def cancel(self, provider_job_id: str) -> None:
        del provider_job_id

    def _parse_response(
        self,
        response: httpx.Response,
        *,
        latency_ms: int,
        quality: str,
    ) -> GenerationProviderResult:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Image response must be an object")
        rows = data.get("data")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise ValueError("Image response contains no output")
        encoded = rows[0].get("b64_json")
        if not isinstance(encoded, str):
            raise ValueError("Image output is missing base64 data")
        payload = base64.b64decode(encoded, validate=True)
        if not payload or len(payload) > self._max_output_bytes:
            raise ValueError("Image output size is invalid")
        if not _looks_like_image("image/png", payload):
            raise ValueError("Image output MIME does not match payload")
        return GenerationProviderResult(
            status="succeeded",
            outputs=[GenerationOutput(content_type="image/png", data=payload)],
            latency_ms=latency_ms,
            provider_cost_units=_QUALITY_COST_UNITS[quality],
            meta={"http_status": response.status_code, "provider_status": "completed"},
        )

    async def _load_input_image(self, url: str) -> tuple[str, bytes]:
        if url.startswith("data:"):
            header, separator, encoded = url.partition(",")
            if not separator or ";base64" not in header:
                raise ValueError("Unsupported data URI")
            content_type = header[5:].split(";", 1)[0].strip().lower()
            image = base64.b64decode(encoded, validate=True)
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
            raise ValueError("Input image is invalid")
        if len(image) > self._max_output_bytes or not _looks_like_image(content_type, image):
            raise ValueError("Input image is invalid or too large")
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
        elif status_code == 400:
            error_code = "invalid_input"
        else:
            error_code = "provider_http_error"
        return GenerationProviderResult(
            status="failed",
            error_code=error_code,
            error_message_safe=f"OpenAI image request HTTP {status_code}",
            latency_ms=latency_ms,
            meta={"http_status": status_code},
        )
