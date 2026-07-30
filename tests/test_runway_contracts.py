"""Runway adapter contract tests against recorded HTTP fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from kelbet.providers.base import GenerationRequest
from kelbet.providers.runway import RunwayProvider

FIXTURES = Path(__file__).resolve().parent / "contracts" / "runway"

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _provider(handler: object) -> tuple[RunwayProvider, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, base_url="https://api.dev.runwayml.com")
    provider = RunwayProvider(
        api_key="test-runway-key",
        base_url="https://api.dev.runwayml.com",
        api_version="2024-11-06",
        client=client,
        download_client=client,
        output_host_allowlist=["cdn.runway.test"],
    )
    return provider, client


@pytest.mark.asyncio
async def test_runway_image_create_and_poll_fixtures() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(f"{request.method} {path}")
        if request.method == "POST" and path == "/v1/text_to_image":
            body = json.loads(request.content.decode())
            assert body["model"] == "gen4_image"
            assert "promptText" in body
            assert request.headers["X-Runway-Version"] == "2024-11-06"
            return httpx.Response(200, json=_load("create_image_accepted.json"))
        if request.method == "GET" and path == "/v1/tasks/task_image_001":
            if calls.count("GET /v1/tasks/task_image_001") == 1:
                return httpx.Response(200, json=_load("task_image_running.json"))
            return httpx.Response(200, json=_load("task_image_succeeded.json"))
        if request.method == "GET" and path.endswith("/image_001.png"):
            return httpx.Response(200, content=_PNG_1X1, headers={"content-type": "image/png"})
        return httpx.Response(404, json={"error": "unexpected", "path": path})

    provider, client = _provider(handler)
    async with client:
        accepted = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gen4_image",
                modality="image",
                prompt="a lake at dusk",
                params={"aspect_ratio": "16:9", "resolution": "720p"},
            )
        )
        assert accepted.status == "accepted"
        assert accepted.provider_job_id == "task_image_001"

        running = await provider.get_status("task_image_001")
        assert running.status == "accepted"

        done = await provider.get_status("task_image_001")
        assert done.status == "succeeded"
        assert done.outputs[0].content_type == "image/png"
        assert done.outputs[0].data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_runway_image_sends_reference_images() -> None:
    reference_url = "https://assets.example.test/reference.jpg?signature=short-lived"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/text_to_image":
            body = json.loads(request.content.decode())
            assert body["referenceImages"] == [{"uri": reference_url}]
            return httpx.Response(200, json={"id": "task_reference_001"})
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        accepted = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gen4_image",
                modality="image",
                prompt="turn the product into a premium studio campaign",
                params={"aspect_ratio": "1:1", "resolution": "720p"},
                input_urls=[reference_url],
            )
        )

    assert accepted.status == "accepted"
    assert accepted.provider_job_id == "task_reference_001"


@pytest.mark.asyncio
async def test_runway_seedream_edit_keeps_reference_order() -> None:
    references = [
        "https://assets.example.test/front.jpg",
        "https://assets.example.test/side.jpg",
        "https://assets.example.test/style.webp",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/text_to_image":
            body = json.loads(request.content.decode())
            assert body == {
                "model": "seedream5_pro",
                "promptText": "Keep the product, change the campaign setting",
                "ratio": "2720:1530",
                "referenceImages": [{"uri": url} for url in references],
            }
            return httpx.Response(200, json={"id": "task_edit_001"})
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="seedream5_pro",
                modality="image_edit",
                prompt="Keep the product, change the campaign setting",
                params={"aspect_ratio": "16:9", "resolution": "2k"},
                input_urls=references,
            )
        )

    assert result.status == "accepted"
    assert result.provider_job_id == "task_edit_001"


@pytest.mark.asyncio
async def test_runway_image_upscale_contract() -> None:
    source = "https://assets.example.test/photo.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_upscale":
            body = json.loads(request.content.decode())
            assert body == {
                "model": "magnific_precision_upscaler_v2",
                "imageUri": source,
                "scaleFactor": 2,
                "flavor": "photo_denoiser",
                "sharpen": 0,
                "smartGrain": 15,
                "ultraDetail": 65,
            }
            return httpx.Response(200, json={"id": "task_upscale_001"})
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="magnific_precision_upscaler_v2",
                modality="upscale",
                prompt="",
                params={
                    "scale_factor": 2,
                    "flavor": "photo_denoiser",
                    "sharpen": 0,
                    "smart_grain": 15,
                    "ultra_detail": 65,
                },
                input_urls=[source],
            )
        )

    assert result.status == "accepted"
    assert result.provider_job_id == "task_upscale_001"


@pytest.mark.asyncio
async def test_runway_video_create_and_poll_fixtures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/text_to_video":
            body = json.loads(request.content.decode())
            assert body["model"] == "gemini_omni_flash"
            assert body["duration"] == 4
            return httpx.Response(200, json=_load("create_video_accepted.json"))
        if request.method == "GET" and path == "/v1/tasks/task_video_001":
            return httpx.Response(200, json=_load("task_video_succeeded.json"))
        if request.method == "GET" and path.endswith("/video_001.mp4"):
            return httpx.Response(200, content=_MP4_STUB, headers={"content-type": "video/mp4"})
        return httpx.Response(404, json={"error": path})

    provider, client = _provider(handler)
    async with client:
        accepted = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gemini_omni_flash",
                modality="video",
                prompt="waves on a shore",
                params={
                    "duration_sec": 4,
                    "resolution": "720p",
                    "aspect_ratio": "16:9",
                },
            )
        )
        assert accepted.status == "accepted"
        assert accepted.provider_cost_units == 4000
        done = await provider.get_status("task_video_001")
        assert done.status == "succeeded"
        assert done.outputs[0].content_type == "video/mp4"


@pytest.mark.asyncio
async def test_runway_image_to_video_uses_first_frame() -> None:
    source = "https://cdn.runway.test/inputs/first-frame.png"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/image_to_video"
        body = json.loads(request.content.decode())
        assert body == {
            "model": "gen4.5",
            "promptImage": source,
            "promptText": "The camera moves slowly toward the product",
            "ratio": "720:1280",
            "duration": 8,
        }
        return httpx.Response(200, json={"id": "task_image_video_001"})

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="gen4.5",
                modality="video",
                prompt="The camera moves slowly toward the product",
                params={
                    "duration_sec": 8,
                    "resolution": "720p",
                    "aspect_ratio": "9:16",
                },
                input_urls=[source],
            )
        )
    assert result.status == "accepted"
    assert result.provider_cost_units == 9600


@pytest.mark.asyncio
async def test_runway_rejects_untrusted_output_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/tasks/"):
            return httpx.Response(
                200,
                json={
                    "id": "task_x",
                    "status": "SUCCEEDED",
                    "output": ["https://evil.example/steal.png"],
                },
            )
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status("task_x")
    assert result.status == "failed"
    assert result.error_code == "untrusted_output_host"


@pytest.mark.asyncio
async def test_runway_rejects_unexpected_output_mime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/tasks/"):
            return httpx.Response(
                200,
                json={
                    "id": "task_bad_mime",
                    "status": "SUCCEEDED",
                    "output": ["https://cdn.runway.test/output/video.mp4"],
                },
            )
        if request.url.path.endswith("/video.mp4"):
            return httpx.Response(
                200,
                content=b"<html>not a video</html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status("task_bad_mime")
    assert result.status == "failed"
    assert result.error_code == "provider_http_error"
