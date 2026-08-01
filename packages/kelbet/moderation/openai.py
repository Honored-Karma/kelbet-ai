from __future__ import annotations

from typing import Any

import httpx

from kelbet.moderation.base import ModerationProviderError, ProviderModerationResult

_ALLOWED_CATEGORIES = frozenset(
    {
        "harassment",
        "harassment_threatening",
        "hate",
        "hate_threatening",
        "illicit",
        "illicit_violent",
        "self_harm",
        "self_harm_instructions",
        "self_harm_intent",
        "sexual",
        "sexual_minors",
        "violence",
        "violence_graphic",
    }
)


def _category_code(value: str) -> str | None:
    normalized = value.strip().lower().replace("/", "_").replace("-", "_")
    return normalized if normalized in _ALLOWED_CATEGORIES else None


class OpenAIModerationProvider:
    """Text-only adapter for the documented POST /v1/moderations contract."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._model = model.strip()
        self._timeout = timeout_seconds
        self._client = client

    async def moderate_text(self, text: str) -> ProviderModerationResult:
        if not self._api_key:
            raise ModerationProviderError("provider_not_configured")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}/moderations",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": text},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ModerationProviderError("provider_unavailable") from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 429:
            raise ModerationProviderError("provider_rate_limit")
        if response.status_code >= 400:
            raise ModerationProviderError("provider_http_error")
        try:
            payload: dict[str, Any] = response.json()
            results = payload["results"]
            first = results[0]
            raw_categories = first["categories"]
            categories = tuple(
                code
                for key, flagged in raw_categories.items()
                if flagged is True and (code := _category_code(str(key))) is not None
            )
            flagged = bool(first["flagged"])
            request_id = str(payload["id"])
            model = str(payload["model"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModerationProviderError("provider_invalid_response") from exc
        return ProviderModerationResult(
            flagged=flagged,
            categories=categories,
            provider="openai",
            model=model,
            request_id=request_id,
        )
