from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from kelbet.chat import ChatCompletionResult, ChatMessage
from kelbet.config import Settings
from kelbet.domain.exceptions import ChatProviderError

logger = logging.getLogger(__name__)


class OpenRouterChatProvider:
    """OpenRouter chat provider using the OpenAI-compatible HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        http_referer: str,
        app_title: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            msg = "OPENROUTER_API_KEY is not set"
            raise ValueError(msg)
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._http_referer = http_referer
        self._app_title = app_title
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> OpenRouterChatProvider:
        return cls(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            timeout_seconds=settings.chat_timeout_seconds,
            http_referer=settings.openrouter_http_referer,
            app_title=settings.openrouter_app_title,
            client=client,
        )

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        messages: list[ChatMessage],
        request_id: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletionResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer,
            "X-Title": self._app_title,
            "X-Request-Id": request_id,
        }
        url = f"{self._base_url}/chat/completions"
        started = time.perf_counter()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)

        try:
            response = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                logger.warning(
                    "chat_provider_error provider=%s model=%s latency_ms=%s status=%s",
                    self.name,
                    self._model,
                    latency_ms,
                    response.status_code,
                )
                raise ChatProviderError(f"OpenRouter HTTP {response.status_code}")

            data = response.json()
            content = self._extract_content(data)
            logger.info(
                "chat_complete provider=%s model=%s latency_ms=%s status=ok",
                self.name,
                self._model,
                latency_ms,
            )
            return ChatCompletionResult(
                content=content,
                provider=self.name,
                model=self._model,
                latency_ms=latency_ms,
                status="ok",
            )
        except ChatProviderError:
            raise
        except httpx.TimeoutException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "chat_provider_error provider=%s model=%s latency_ms=%s status=timeout",
                self.name,
                self._model,
                latency_ms,
            )
            raise ChatProviderError("OpenRouter request timed out") from exc
        except httpx.HTTPError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "chat_provider_error provider=%s model=%s latency_ms=%s status=http_error",
                self.name,
                self._model,
                latency_ms,
            )
            raise ChatProviderError("OpenRouter request failed") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "chat_provider_error provider=%s model=%s latency_ms=%s status=bad_response",
                self.name,
                self._model,
                latency_ms,
            )
            raise ChatProviderError("OpenRouter returned an invalid response") from exc
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data["choices"]
        message = choices[0]["message"]
        content = message["content"]
        if not isinstance(content, str) or not content.strip():
            raise ChatProviderError("OpenRouter returned empty content")
        return content.strip()


# Keep SYSTEM_PROMPT import used by callers building messages.
__all__ = ["OpenRouterChatProvider"]
