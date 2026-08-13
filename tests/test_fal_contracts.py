"""fal.ai adapter contract tests.

The three behaviours guarded hardest here are the ones that cost money or break
silently rather than loudly:

* `duration` is typed differently per model. A string where fal wants an integer is
  a 422 that only shows up against the live API, so every encoding is asserted on
  the wire.
* The poll URL needs the endpoint id, which the job id has to carry. If that packing
  regresses, jobs are submitted and billed but never collected.
* An endpoint outside the adapter allowlist must be refused before any HTTP call,
  because an unknown model would be recorded at zero provider cost.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from kelbet.catalog.seeds import catalog_model_rows
from kelbet.config import Settings
from kelbet.providers.base import GenerationRequest
from kelbet.providers.factory import resolve_provider
from kelbet.providers.fal import FalProvider, fal_endpoint_ids, fal_model_spec

_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"

_BASE_URL = "https://queue.fal.run"
_KLING = "fal-ai/kling-video/v3/pro/text-to-video"
_GROK = "xai/grok-imagine-video/text-to-video"
_LUMA = "fal-ai/luma-dream-machine/ray-2-flash"
_REQUEST_ID = "9a2f1c8e-9b1c-4d6f-9e21-7f3d4e5b1234"


def _provider(handler: Any) -> tuple[FalProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    provider = FalProvider(
        api_key="test-fal-key",
        base_url=_BASE_URL,
        client=client,
        download_client=client,
        output_host_allowlist=["cdn.fal.test"],
    )
    return provider, client


def _request(
    provider_model_id: str = _KLING,
    *,
    params: dict[str, Any] | None = None,
    input_urls: list[str] | None = None,
) -> GenerationRequest:
    return GenerationRequest(
        generation_id=uuid4(),
        provider_model_id=provider_model_id,
        modality="video",
        prompt="A calm steppe sunrise",
        params=params if params is not None else {"duration_sec": 5, "aspect_ratio": "16:9"},
        input_urls=input_urls or [],
    )


def _accepted(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "request_id": _REQUEST_ID,
            "status": "IN_QUEUE",
            "status_url": f"{request.url}/requests/{_REQUEST_ID}/status",
            "response_url": f"{request.url}/requests/{_REQUEST_ID}",
        },
    )


@pytest.mark.asyncio
async def test_submit_authenticates_with_the_key_scheme_not_bearer() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request())

    assert result.status == "accepted"
    # fal rejects "Bearer"; the scheme is the literal word "Key".
    assert seen["auth"] == "Key test-fal-key"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_model_id", "expected_duration"),
    [
        # Bare numeric string (Kling, Seedance, Wan 2.5, PixVerse, Hailuo).
        (_KLING, "5"),
        # Real integer (Grok Imagine, Wan 2.7).
        (_GROK, 5),
        # Suffixed string (Luma).
        (_LUMA, "5s"),
    ],
)
async def test_duration_is_encoded_per_model_schema(
    provider_model_id: str,
    expected_duration: str | int,
) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content.decode()))
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request(provider_model_id, params={"duration_sec": 5}))

    assert result.status == "accepted"
    assert bodies[0]["duration"] == expected_duration
    # A bare int and the string "5" are different values to fal, so identity of the
    # Python type is the thing under test, not just equality.
    assert isinstance(bodies[0]["duration"], type(expected_duration))


@pytest.mark.asyncio
async def test_submit_posts_to_the_endpoint_id_path() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        await provider.generate(_request())

    assert urls == [f"{_BASE_URL}/{_KLING}"]


@pytest.mark.asyncio
async def test_job_id_carries_the_endpoint_so_polling_can_address_the_request() -> None:
    """The poll URL is /{endpoint_id}/requests/{id}/status, and the job column holds
    one string. Losing the endpoint half means paying for work never collected."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "POST":
            return _accepted(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "IN_PROGRESS"})
        return httpx.Response(404, json={"detail": "unexpected"})

    provider, client = _provider(handler)
    async with client:
        accepted = await provider.generate(_request())
        assert accepted.provider_job_id == f"{_KLING}|{_REQUEST_ID}"
        polled = await provider.get_status(accepted.provider_job_id or "")

    assert polled.status == "accepted"
    assert paths[-1] == f"/{_KLING}/requests/{_REQUEST_ID}/status"


@pytest.mark.asyncio
async def test_completed_job_downloads_the_video_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "cdn.fal.test":
            return httpx.Response(200, content=_MP4_STUB, headers={"content-type": "video/mp4"})
        return httpx.Response(
            200,
            json={
                "video": {"url": "https://cdn.fal.test/files/out.mp4", "content_type": "video/mp4"}
            },
        )

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status(f"{_KLING}|{_REQUEST_ID}")

    assert result.status == "succeeded"
    assert len(result.outputs) == 1
    assert result.outputs[0].content_type == "video/mp4"
    assert result.outputs[0].data == _MP4_STUB


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_status", "expected_code"),
    [
        ("FAILED", "provider_failed"),
        ("ERROR", "provider_failed"),
        ("CANCELED", "provider_cancelled"),
        ("SOMETHING_NEW", "provider_bad_response"),
    ],
)
async def test_terminal_statuses_map_to_distinct_error_codes(
    provider_status: str,
    expected_code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": provider_status})

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status(f"{_KLING}|{_REQUEST_ID}")

    assert result.status == "failed"
    assert result.error_code == expected_code


@pytest.mark.asyncio
async def test_output_from_an_unlisted_host_is_refused_before_download() -> None:
    downloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host != "queue.fal.run":
            downloads.append(str(request.url))
            return httpx.Response(200, content=_MP4_STUB)
        return httpx.Response(200, json={"video": {"url": "https://evil.example.com/out.mp4"}})

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status(f"{_KLING}|{_REQUEST_ID}")

    assert result.status == "failed"
    assert result.error_code == "untrusted_output_host"
    assert downloads == []


@pytest.mark.asyncio
async def test_insufficient_provider_credit_is_named_as_the_operators_problem() -> None:
    """402 is the fal account being out of money, never a bad prompt. Collapsing it
    into a generic HTTP error sends the user to support for something only the
    operator can fix."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": "Insufficient credits"})

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request())

    assert result.status == "failed"
    assert result.error_code == "provider_insufficient_credits"
    assert result.error_message_safe == "Insufficient credits"


@pytest.mark.asyncio
async def test_validation_error_reports_the_offending_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": [
                    {"loc": ["body", "duration"], "msg": "value is not a valid integer"},
                ]
            },
        )

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request())

    assert result.error_code == "provider_rejected_params"
    assert result.error_message_safe == "body.duration: value is not a valid integer"


@pytest.mark.asyncio
async def test_model_outside_the_allowlist_never_reaches_the_network() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request("fal-ai/some/unreviewed/model"))

    assert result.status == "failed"
    assert result.error_code == "provider_unsupported_model"
    assert result.provider_cost_units == 0
    assert calls == []


@pytest.mark.asyncio
async def test_auto_resolution_is_a_catalog_marker_and_never_sent_on_the_wire() -> None:
    """Kling exposes no resolution parameter. The catalog still has to declare one
    because the Mini App always sends it, so "auto" is the agreed placeholder."""
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content.decode()))
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        await provider.generate(_request(_KLING, params={"duration_sec": 5, "resolution": "auto"}))

    assert "resolution" not in bodies[0]


@pytest.mark.asyncio
async def test_a_source_image_switches_to_the_image_to_video_endpoint() -> None:
    urls: list[str] = []
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(request.url.path)
        bodies.append(json.loads(request.content.decode()))
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            _request(_GROK, params={"duration_sec": 6}, input_urls=["https://cdn.fal.test/in.jpg"])
        )

    assert result.status == "accepted"
    assert urls == ["/xai/grok-imagine-video/image-to-video"]
    assert bodies[0]["image_url"] == "https://cdn.fal.test/in.jpg"


@pytest.mark.asyncio
async def test_a_text_only_model_refuses_a_source_image() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            _request(_LUMA, params={"duration_sec": 5}, input_urls=["https://cdn.fal.test/in.jpg"])
        )

    assert result.status == "failed"
    assert result.error_code == "unsupported_input_mode"


@pytest.mark.asyncio
async def test_extension_chaining_is_refused_rather_than_silently_dropped() -> None:
    from kelbet.providers.base import GenerationOutput

    def handler(request: httpx.Request) -> httpx.Response:
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(
            GenerationRequest(
                generation_id=uuid4(),
                provider_model_id=_KLING,
                modality="video",
                prompt="continue the shot",
                params={"duration_sec": 5},
                extension_video=GenerationOutput(content_type="video/mp4", data=_MP4_STUB),
            )
        )

    assert result.error_code == "unsupported_workflow"


@pytest.mark.asyncio
async def test_a_job_id_without_its_endpoint_fails_loudly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "COMPLETED"})

    provider, client = _provider(handler)
    async with client:
        result = await provider.get_status("bare-request-id")

    assert result.error_code == "provider_bad_job_id"


@pytest.mark.asyncio
async def test_cancelling_an_already_finished_job_is_not_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == f"/{_KLING}/requests/{_REQUEST_ID}/cancel"
        return httpx.Response(409, json={"detail": "Request already finished"})

    provider, client = _provider(handler)
    async with client:
        await provider.cancel(f"{_KLING}|{_REQUEST_ID}")


@pytest.mark.asyncio
async def test_an_unconfigured_key_fails_closed_without_calling_fal() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return _accepted(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=_BASE_URL)
    provider = FalProvider(api_key="", base_url=_BASE_URL, client=client, download_client=client)
    async with client:
        submitted = await provider.generate(_request())
        polled = await provider.get_status(f"{_KLING}|{_REQUEST_ID}")

    assert submitted.error_code == "missing_api_key"
    assert polled.error_code == "missing_api_key"
    assert calls == []


@pytest.mark.asyncio
async def test_accepted_job_records_the_provider_cost_it_will_be_billed() -> None:
    """Cost is recorded at submit because reconciliation and the generation passport
    both read it. Zero here would make the SKU look free after the fact."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _accepted(request)

    provider, client = _provider(handler)
    async with client:
        result = await provider.generate(_request(_KLING, params={"duration_sec": 10}))

    # Kling 3.0 Pro is $0.112/s without audio: 10s == $1.12 == 11200 units.
    assert result.provider_cost_units == 11200


def test_factory_routes_the_fal_provider_name() -> None:
    provider = resolve_provider("fal", modality="video", settings=Settings())
    assert isinstance(provider, FalProvider)
    assert provider.name == "fal"


def test_every_fal_catalog_row_points_at_an_endpoint_the_adapter_can_call() -> None:
    """The catalog and the adapter are edited in different files. A slug typo would
    otherwise reach production as a model billed at zero recorded cost."""
    allowlist = fal_endpoint_ids()
    fal_rows = [row for row in catalog_model_rows() if row["provider"] == "fal"]

    assert fal_rows, "the fal catalog is empty"
    for row in fal_rows:
        endpoint_id = row["provider_model_id"]
        assert endpoint_id in allowlist, f"{row['slug']} points at unknown endpoint {endpoint_id}"


def test_every_fal_row_declares_a_resolution_the_adapter_understands() -> None:
    """The Mini App always sends a resolution, and the quote rejects any value the
    catalog does not declare, so an empty list would make the SKU unquotable."""
    for row in catalog_model_rows():
        if row["provider"] != "fal":
            continue
        capabilities = row["capabilities"]
        assert isinstance(capabilities, dict)
        resolutions = capabilities.get("resolutions")
        assert resolutions, f"{row['slug']} declares no resolution"
        spec = fal_model_spec(str(row["provider_model_id"]))
        assert spec is not None
        if spec.resolution_field is None:
            # The endpoint takes no resolution parameter, so the user cannot choose
            # one. Offering a list would render a selector that changes nothing while
            # still moving the price. A single entry is the only honest declaration:
            # the model's real fixed output ("768p", "4k") where that is known, and
            # "auto" where it is not.
            assert len(resolutions) == 1, (
                f"{row['slug']} offers a choice of {resolutions} although the endpoint "
                "accepts no resolution parameter"
            )
        else:
            assert "auto" not in resolutions, (
                f"{row['slug']} declares auto although the endpoint accepts a real resolution"
            )


def test_packed_job_id_fits_the_provider_job_id_column() -> None:
    """`generation_jobs.provider_job_id` is VARCHAR(128) and this adapter stores two
    values in it. Overflowing that column raises on INSERT *after* fal has accepted
    and started billing the job, so the clip is paid for and then orphaned. Endpoint
    ids are the half that grows, so the budget is checked here rather than discovered
    in production.
    """
    column_limit = 128
    uuid_length = 36  # fal request ids are UUIDs

    endpoints = set(fal_endpoint_ids())
    for endpoint_id in fal_endpoint_ids():
        spec = fal_model_spec(endpoint_id)
        assert spec is not None
        if spec.image_endpoint_id:
            endpoints.add(spec.image_endpoint_id)

    for endpoint_id in endpoints:
        packed = len(endpoint_id) + 1 + uuid_length
        assert packed <= column_limit, (
            f"{endpoint_id} packs to {packed} characters, over the {column_limit} the "
            "provider_job_id column holds"
        )


def test_catalog_recorded_cost_matches_what_the_adapter_will_bill() -> None:
    """`provider_cost_units` lives in the catalog, the real rate table lives in the
    adapter, and nothing connects them at runtime. If they drift, every margin check
    in `test_catalog_economics` is verifying a number the provider never charged."""
    for row in catalog_model_rows():
        if row["provider"] != "fal":
            continue
        capabilities = row["capabilities"]
        assert isinstance(capabilities, dict)
        spec = fal_model_spec(str(row["provider_model_id"]))
        assert spec is not None

        # The base row price is quoted for the first declared resolution and duration.
        resolution = str(capabilities["resolutions"][0])
        billed = spec.cost_units(
            duration_sec=int(capabilities["durations_sec"][0]),
            resolution=None if resolution == "auto" else resolution,
        )
        assert billed == row["provider_cost_units"], (
            f"{row['slug']} records {row['provider_cost_units']} units but the adapter "
            f"will bill {billed}"
        )


def test_every_fal_duration_is_priced() -> None:
    """A duration offered by the catalog but missing from the pricing rules would be
    charged at the base price regardless of length."""
    for row in catalog_model_rows():
        if row["provider"] != "fal":
            continue
        capabilities = row["capabilities"]
        pricing_rules = row["pricing_rules"]
        assert isinstance(capabilities, dict)
        assert isinstance(pricing_rules, dict)
        multipliers = pricing_rules["duration_multipliers"]
        assert isinstance(multipliers, dict)
        for duration in capabilities["durations_sec"]:
            assert str(duration) in multipliers, f"{row['slug']} has no price for {duration}s"
