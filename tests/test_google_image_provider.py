from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from kelbet.config import Settings
from kelbet.providers.base import GenerationRequest
from kelbet.providers.factory import resolve_provider
from kelbet.providers.google_image import GoogleGeminiImageProvider
from kelbet.providers.google_veo import GoogleVeoProvider

FIXTURE = Path(__file__).parent / "fixtures" / "google_interactions_image_completed.json"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_google_interactions_image_generation_contract_is_safe_and_costed() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "test-google"
        return httpx.Response(200, json=fixture)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleGeminiImageProvider(
            api_key="test-google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gemini-3.1-flash-image",
                modality="image",
                prompt="A product photograph on a neutral background",
                params={"aspect_ratio": "1:1", "resolution": "2k"},
            )
        )

    assert result.status == "succeeded"
    assert result.outputs[0].data == PNG_1X1
    assert result.provider_cost_units == 1010
    assert result.meta == {
        "http_status": 200,
        "provider_status": "completed",
        "tokens_in": 24,
        "tokens_out": 1120,
    }
    assert captured["model"] == "gemini-3.1-flash-image"
    assert captured["response_format"] == {
        "type": "image",
        "aspect_ratio": "1:1",
        "image_size": "2K",
    }


@pytest.mark.asyncio
async def test_google_image_edit_inlines_source_without_logging_or_response_passthrough() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=fixture)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleGeminiImageProvider(
            api_key="test-google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gemini-3.1-flash-image",
                modality="image_edit",
                prompt="Change only the background color",
                params={"aspect_ratio": "4:3", "resolution": "1k"},
                input_urls=[f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}"],
            )
        )

    assert result.status == "succeeded"
    inputs = captured["input"]
    assert isinstance(inputs, list) and inputs[1]["type"] == "image"
    assert "steps" not in result.meta and "data" not in result.meta


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(429, "rate_limited"), (503, "provider_unavailable"), (403, "provider_account_error")],
)
async def test_google_image_http_failures_are_safely_classified(
    status_code: int,
    error_code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code, json={"error": {"message": "must not persist"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleGeminiImageProvider(
            api_key="test-google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gemini-3.1-flash-image",
                modality="image",
                prompt="Safe prompt",
                params={"aspect_ratio": "1:1", "resolution": "1k"},
            )
        )
    assert result.error_code == error_code
    assert "must not persist" not in str(result)


@pytest.mark.asyncio
async def test_google_image_explicitly_rejects_upscale() -> None:
    provider = GoogleGeminiImageProvider(
        api_key="test-google",
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    result = await provider.generate(
        GenerationRequest(
            generation_id=uuid4(),
            provider_model_id="gemini-3.1-flash-image",
            modality="upscale",
            prompt="",
            params={"resolution": "2k"},
        )
    )
    assert result.error_code == "unsupported_capability"


def test_google_factory_routes_image_and_video_to_distinct_adapters() -> None:
    settings = Settings(google_api_key="test")
    assert isinstance(
        resolve_provider("google", modality="image", settings=settings),
        GoogleGeminiImageProvider,
    )
    assert isinstance(
        resolve_provider("google", modality="video", settings=settings),
        GoogleVeoProvider,
    )
