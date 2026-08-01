"""OpenRouter text generation adapter (Mini App generations path)."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

import httpx

from kelbet.chat import SYSTEM_PROMPT
from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)

logger = logging.getLogger(__name__)


class OpenRouterTextProvider:
    """Chat-completions via OpenRouter for async text generations.

    Distinct from ``OpenRouterChatProvider`` / bot ``ChatService`` (ADR-009).
    Uses catalog ``provider_model_id`` per request, not settings default model alone.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        http_referer: str,
        app_title: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._http_referer = http_referer
        self._app_title = app_title
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> OpenRouterTextProvider:
        cfg = settings or get_settings()
        return cls(
            api_key=cfg.openrouter_api_key,
            base_url=cfg.openrouter_base_url,
            timeout_seconds=cfg.chat_timeout_seconds,
            http_referer=cfg.openrouter_http_referer,
            app_title=cfg.openrouter_app_title,
            client=client,
        )

    @property
    def name(self) -> str:
        return "openrouter"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if not self._api_key:
            return GenerationProviderResult(
                status="failed",
                error_code="missing_api_key",
                error_message_safe="OpenRouter API key is not configured",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        if request.modality != "text":
            return GenerationProviderResult(
                status="failed",
                error_code="unsupported_modality",
                error_message_safe="OpenRouter adapter supports text only",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        model = request.provider_model_id
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.prompt},
            ],
        }
        request_id = str(request.generation_id)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer,
            "X-Title": self._app_title,
            "X-Request-Id": request_id,
        }
        url = f"{self._base_url}/chat/completions"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)

        try:
            response = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                logger.warning(
                    "generation_provider_error provider=%s model=%s "
                    "latency_ms=%s status=%s generation_id=%s",
                    self.name,
                    model,
                    latency_ms,
                    response.status_code,
                    request.generation_id,
                )
                return GenerationProviderResult(
                    status="failed",
                    error_code="provider_http_error",
                    error_message_safe=f"OpenRouter HTTP {response.status_code}",
                    latency_ms=latency_ms,
                    meta={"http_status": response.status_code},
                )

            data = response.json()
            content = self._extract_content(data)
            usage = data.get("usage") if isinstance(data, dict) else None
            tokens_in = None
            tokens_out = None
            if isinstance(usage, dict):
                tokens_in = usage.get("prompt_tokens")
                tokens_out = usage.get("completion_tokens")
            logger.info(
                "generation_complete provider=%s model=%s latency_ms=%s status=ok generation_id=%s",
                self.name,
                model,
                latency_ms,
                request.generation_id,
            )
            return GenerationProviderResult(
                status="succeeded",
                outputs=[
                    GenerationOutput(
                        content_type="text/plain; charset=utf-8",
                        data=content.encode("utf-8"),
                        meta={"chars": len(content)},
                    )
                ],
                provider_job_id=f"or-{uuid4().hex[:16]}",
                latency_ms=latency_ms,
                provider_cost_units=0,
                meta={
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )
        except httpx.TimeoutException:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "generation_provider_error provider=%s model=%s "
                "latency_ms=%s status=timeout generation_id=%s",
                self.name,
                model,
                latency_ms,
                request.generation_id,
            )
            return GenerationProviderResult(
                status="failed",
                error_code="provider_timeout",
                error_message_safe="OpenRouter request timed out",
                latency_ms=latency_ms,
            )
        except httpx.HTTPError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "generation_provider_error provider=%s model=%s "
                "latency_ms=%s status=http_error generation_id=%s",
                self.name,
                model,
                latency_ms,
                request.generation_id,
            )
            return GenerationProviderResult(
                status="failed",
                error_code="provider_http_error",
                error_message_safe="OpenRouter request failed",
                latency_ms=latency_ms,
            )
        except (KeyError, IndexError, TypeError, ValueError):
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "generation_provider_error provider=%s model=%s "
                "latency_ms=%s status=bad_response generation_id=%s",
                self.name,
                model,
                latency_ms,
                request.generation_id,
            )
            return GenerationProviderResult(
                status="failed",
                error_code="provider_bad_response",
                error_message_safe="OpenRouter returned an invalid response",
                latency_ms=latency_ms,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code="not_async",
            error_message_safe="OpenRouter text provider is synchronous",
        )

    async def cancel(self, provider_job_id: str) -> None:
        return None

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data["choices"]
        message = choices[0]["message"]
        content = message["content"]
        if not isinstance(content, str) or not content.strip():
            msg = "OpenRouter returned empty content"
            raise ValueError(msg)
        return content.strip()
