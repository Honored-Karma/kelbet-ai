"""Official Gemini API Veo predictLongRunning contract tests."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest

from kelbet.providers.base import GenerationRequest
from kelbet.providers.google_veo import GoogleVeoProvider

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _provider(handler: object) -> tuple[GoogleVeoProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return (
        GoogleVeoProvider(
            api_key="google-test-key",
            base_url="https://google.test/v1beta",
            output_host_allowlist=["google.test"],
            client=client,
            download_client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_google_veo_text_create_and_poll() -> None:
    operation = "models/veo-3.1-lite-generate-preview/operations/op-001"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(
            "/models/veo-3.1-lite-generate-preview:predictLongRunning"
        ):
            assert request.headers["x-goog-api-key"] == "google-test-key"
            body = json.loads(request.content)
            assert body["instances"] == [{"prompt": "A felt yurt opens at sunrise"}]
            assert body["parameters"] == {
                "aspectRatio": "9:16",
                "durationSeconds": 4,
                "resolution": "720p",
                "numberOfVideos": 1,
            }
            return httpx.Response(200, json={"name": operation})
        if request.method == "GET" and request.url.path.endswith("/operations/op-001"):
            return httpx.Response(
                200,
                json={
                    "name": operation,
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [
                                {"video": {"uri": "https://google.test/files/out.mp4"}}
                            ]
                        }
                    },
                },
            )
        if request.method == "GET" and request.url.path == "/files/out.mp4":
            return httpx.Response(
                200,
                content=_MP4,
                headers={"content-type": "video/mp4"},
            )
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        accepted = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="veo-3.1-lite-generate-preview",
                modality="video",
                prompt="A felt yurt opens at sunrise",
                params={
                    "aspect_ratio": "9:16",
                    "resolution": "720p",
                    "duration_sec": 4,
                },
            )
        )
        assert accepted.status == "accepted"
        assert accepted.provider_job_id == operation
        assert accepted.provider_cost_units == 2000

        done = await provider.get_status(operation)
        assert done.status == "succeeded"
        assert done.outputs[0].content_type == "video/mp4"
        assert done.outputs[0].data == _MP4


@pytest.mark.asyncio
async def test_google_veo_image_to_video_uses_inline_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        inline = body["instances"][0]["image"]["inlineData"]
        assert inline["mimeType"] == "image/png"
        assert base64.b64decode(inline["data"]) == _PNG_1X1
        return httpx.Response(200, json={"name": "operations/image-001"})

    provider, client = _provider(handler)
    source = f"data:image/png;base64,{base64.b64encode(_PNG_1X1).decode('ascii')}"
    async with client:
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id="veo-3.1-lite-generate-preview",
                modality="video",
                prompt="Steam rises as the camera moves closer",
                params={"duration_sec": 8},
                input_urls=[source],
            )
        )
    assert result.status == "accepted"
    assert result.provider_cost_units == 4000


@pytest.mark.asyncio
async def test_google_veo_rejects_untrusted_output_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": {
                    "generateVideoResponse": {
                        "generatedSamples": [{"video": {"uri": "https://evil.example/video.mp4"}}]
                    }
                },
            },
        )

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status("operations/unsafe")
    assert result.status == "failed"
    assert result.error_code == "untrusted_output_host"


@pytest.mark.asyncio
async def test_google_veo_rejects_unexpected_output_mime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/operations/bad-mime"):
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [
                                {"video": {"uri": "https://google.test/files/not-video.mp4"}}
                            ]
                        }
                    },
                },
            )
        if request.url.path.endswith("/files/not-video.mp4"):
            return httpx.Response(
                200,
                content=b"<html>not a video</html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404)

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status("operations/bad-mime")
    assert result.status == "failed"
    assert result.error_code == "provider_http_error"
