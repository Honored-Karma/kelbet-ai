"""OpenRouter text generation adapter unit tests (mocked HTTP)."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from kelbet.providers.base import GenerationRequest
from kelbet.providers.openrouter import OpenRouterTextProvider


def _provider(client: httpx.AsyncClient) -> OpenRouterTextProvider:
    return OpenRouterTextProvider(
        api_key="test-key",
        base_url="https://openrouter.test/api/v1",
        timeout_seconds=5.0,
        http_referer="https://kelbet.ai",
        app_title="KELBET AI",
        client=client,
    )


@pytest.mark.asyncio
async def test_openrouter_text_success_uses_catalog_model() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        body = json.loads(request.content.decode())
        seen["model"] = body["model"]
        seen["messages"] = body["messages"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "  Сәлем!  "}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _provider(client).generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="openai/gpt-4o-mini",
                modality="text",
                prompt="Привет",
            )
        )

    assert result.status == "succeeded"
    assert result.outputs[0].data.decode("utf-8") == "Сәлем!"
    assert result.meta["tokens_in"] == 12
    assert result.meta["tokens_out"] == 4
    assert seen["model"] == "openai/gpt-4o-mini"
    assert seen["url"] == "https://openrouter.test/api/v1/chat/completions"
    assert seen["messages"][1] == {"role": "user", "content": "Привет"}  # type: ignore[index]


@pytest.mark.asyncio
async def test_openrouter_http_error_does_not_succeed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _provider(client).generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="openai/gpt-4o-mini",
                modality="text",
                prompt="x",
            )
        )
    assert result.status == "failed"
    assert result.error_code == "provider_http_error"


@pytest.mark.asyncio
async def test_openrouter_missing_api_key() -> None:
    provider = OpenRouterTextProvider(
        api_key="",
        base_url="https://openrouter.test/api/v1",
        timeout_seconds=5.0,
        http_referer="https://kelbet.ai",
        app_title="KELBET AI",
    )
    result = await provider.generate(
        GenerationRequest(
            generation_id=uuid4(),
            provider_model_id="openai/gpt-4o-mini",
            modality="text",
            prompt="x",
        )
    )
    assert result.status == "failed"
    assert result.error_code == "missing_api_key"
