from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest

from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows
from kelbet.config import Settings
from kelbet.providers.base import GenerationRequest
from kelbet.providers.factory import resolve_provider
from kelbet.providers.openai_image import OpenAIImageProvider

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_openai_image_generation_uses_safe_contract_and_idempotency_key() -> None:
    captured: dict[str, object] = {}
    generation_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        assert request.url.path == "/v1/images/generations"
        assert request.headers["authorization"] == "Bearer test-openai"
        assert request.headers["idempotency-key"] == str(generation_id)
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(PNG_1X1).decode()}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIImageProvider(
            api_key="test-openai",
            base_url="https://api.openai.com/v1",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=generation_id,
                provider_model_id="gpt-image-2",
                modality="image",
                prompt="A well-lit product photograph",
                params={"aspect_ratio": "1:1", "resolution": "1k", "flavor": "low"},
            )
        )

    assert result.status == "succeeded"
    assert result.outputs[0].content_type == "image/png"
    assert result.outputs[0].data == PNG_1X1
    assert result.provider_cost_units == 600
    assert result.meta == {"http_status": 200, "provider_status": "completed"}
    assert captured["body"] == {
        "model": "gpt-image-2",
        "prompt": "A well-lit product photograph",
        "n": 1,
        "size": "1024x1024",
        "quality": "low",
    }


@pytest.mark.asyncio
async def test_openai_image_edit_uploads_typed_references_without_response_passthrough() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/edits"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b"image[]" in request.content
        assert b"image/png" in request.content
        assert b"Change only the background" in request.content
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(PNG_1X1).decode()}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIImageProvider(
            api_key="test-openai",
            base_url="https://api.openai.com/v1",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gpt-image-2",
                modality="image_edit",
                prompt="Change only the background",
                params={"aspect_ratio": "9:16", "resolution": "1k", "flavor": "medium"},
                input_urls=[f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}"],
            )
        )

    assert result.status == "succeeded"
    assert result.provider_cost_units == 5300
    assert "data" not in str(result.meta)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(429, "rate_limited"), (503, "provider_unavailable"), (401, "provider_account_error")],
)
async def test_openai_image_http_failures_are_safe_and_retryable_when_appropriate(
    status_code: int,
    error_code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code, json={"error": {"message": "secret provider detail"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIImageProvider(
            api_key="test-openai",
            base_url="https://api.openai.com/v1",
            client=client,
        )
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gpt-image-2",
                modality="image",
                prompt="Safe prompt",
                params={"aspect_ratio": "1:1", "flavor": "medium"},
            )
        )

    assert result.error_code == error_code
    assert "secret provider detail" not in str(result)


def test_openai_factory_returns_image_adapter() -> None:
    provider = resolve_provider("openai", modality="image", settings=Settings())
    assert isinstance(provider, OpenAIImageProvider)


def test_openai_image_catalog_is_disabled_until_an_operator_enables_its_flag() -> None:
    models = {row["slug"]: row for row in catalog_model_rows()}
    flags = {row["key"]: row for row in feature_flag_rows()}

    assert flags["openai_image"]["enabled"] is False
    fast = models["openai-gpt-image-2-fast"]
    quality = models["openai-gpt-image-2-quality"]
    assert fast["provider"] == quality["provider"] == "openai"
    assert fast["provider_model_id"] == quality["provider_model_id"] == "gpt-image-2"
    assert fast["provider_cost_units"] == 600
    assert quality["provider_cost_units"] == 5300
    assert fast["feature_flag"] == "openai_image"
    assert quality["feature_flag"] == "openai_image"
