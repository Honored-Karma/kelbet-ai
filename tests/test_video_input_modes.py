"""Video input modes: reject at quote time what Veo would reject at cost."""

from __future__ import annotations

from typing import Any

import pytest

from kelbet.catalog.pricing import validate_params_against_capabilities
from kelbet.catalog.seeds import catalog_model_rows
from kelbet.catalog.video_inputs import (
    DEFAULT_MODE,
    MAX_REFERENCE_ASSETS,
    REFERENCE_ASSETS,
    declared_modes,
    narrow_aspect_ratios,
    requires_prompt,
    resolve_mode,
    validate_asset_count,
)
from kelbet.domain.exceptions import InvalidQuoteParamsError

CONSISTENT_SLUG = "google-veo31-fast-consistent-video"


def _capabilities(slug: str) -> dict[str, Any]:
    row = next(row for row in catalog_model_rows() if row["slug"] == slug)
    return dict(row["capabilities"])


def test_model_without_declared_modes_keeps_the_previous_behaviour() -> None:
    """Rows that predate modes must still accept one optional opening frame."""

    modes = declared_modes(_capabilities("google-veo31-lite-video-fallback"))
    assert set(modes) == {DEFAULT_MODE}
    assert modes[DEFAULT_MODE].max_assets == 1
    assert modes[DEFAULT_MODE].min_assets == 0


def test_consistent_route_declares_all_three_shapes() -> None:
    modes = declared_modes(_capabilities(CONSISTENT_SLUG))
    assert set(modes) == {"first_frame", "first_last_frame", REFERENCE_ASSETS}
    assert modes[REFERENCE_ASSETS].max_assets == MAX_REFERENCE_ASSETS
    # A transition needs both ends, so neither is optional.
    assert modes["first_last_frame"].min_assets == 2
    assert modes["first_last_frame"].max_assets == 2


def test_unknown_mode_is_refused_with_the_supported_list() -> None:
    with pytest.raises(InvalidQuoteParamsError) as excinfo:
        resolve_mode(_capabilities(CONSISTENT_SLUG), "lipsync")
    assert "lipsync" in str(excinfo.value)
    assert REFERENCE_ASSETS in str(excinfo.value)


def test_mode_a_model_does_not_declare_is_refused() -> None:
    """Lite has no reference support, so asking for it must fail before pricing."""

    with pytest.raises(InvalidQuoteParamsError):
        resolve_mode(_capabilities("google-veo31-lite-video-fallback"), REFERENCE_ASSETS)


def test_declared_reference_count_can_never_exceed_the_api_ceiling() -> None:
    """A seed edit must not be able to promise more references than Veo accepts."""

    mode = resolve_mode(
        {"video_inputs": {"modes": {REFERENCE_ASSETS: {"min_assets": 1, "max_assets": 9}}}},
        REFERENCE_ASSETS,
    )
    assert mode.max_assets == MAX_REFERENCE_ASSETS


@pytest.mark.parametrize("count", [0, 4])
def test_reference_mode_rejects_counts_outside_its_range(count: int) -> None:
    mode = resolve_mode(_capabilities(CONSISTENT_SLUG), REFERENCE_ASSETS)
    with pytest.raises(InvalidQuoteParamsError):
        validate_asset_count(mode, count)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_reference_mode_accepts_one_to_three(count: int) -> None:
    validate_asset_count(resolve_mode(_capabilities(CONSISTENT_SLUG), REFERENCE_ASSETS), count)


def test_first_last_frame_needs_both_ends() -> None:
    mode = resolve_mode(_capabilities(CONSISTENT_SLUG), "first_last_frame")
    with pytest.raises(InvalidQuoteParamsError):
        validate_asset_count(mode, 1)
    validate_asset_count(mode, 2)


def test_reference_images_require_a_prompt_and_frames_do_not() -> None:
    capabilities = _capabilities(CONSISTENT_SLUG)
    assert requires_prompt(resolve_mode(capabilities, REFERENCE_ASSETS)) is True
    assert requires_prompt(resolve_mode(capabilities, "first_frame")) is False


def test_vertical_video_is_refused_with_reference_images() -> None:
    """Google restricts reference images to 16:9 and answers 9:16 with a 400.

    Quoting it would sell a request that cannot run, so the narrower list wins
    over the model's own aspect ratios.
    """

    capabilities = _capabilities(CONSISTENT_SLUG)
    assert "9:16" in capabilities["aspect_ratios"]

    with pytest.raises(InvalidQuoteParamsError) as excinfo:
        validate_params_against_capabilities(
            {"input_mode": REFERENCE_ASSETS, "aspect_ratio": "9:16"},
            capabilities,
        )
    assert "9:16" in str(excinfo.value)
    assert REFERENCE_ASSETS in str(excinfo.value)


def test_vertical_video_is_allowed_in_the_frame_modes() -> None:
    for mode in ("first_frame", "first_last_frame"):
        cleaned = validate_params_against_capabilities(
            {"input_mode": mode, "aspect_ratio": "9:16"},
            _capabilities(CONSISTENT_SLUG),
        )
        assert cleaned["aspect_ratio"] == "9:16"


def test_reference_mode_defaults_to_a_ratio_it_can_actually_run() -> None:
    """The default must come from the intersection, not from the model's list.

    Both lists start at 16:9 today, so this asserts the narrowing rather than a
    coincidence: a model listing 9:16 first would otherwise default to a ratio
    the mode forbids.
    """

    narrowed = narrow_aspect_ratios(
        ["9:16", "16:9"], resolve_mode(_capabilities(CONSISTENT_SLUG), REFERENCE_ASSETS)
    )
    assert narrowed == ["16:9"]

    cleaned = validate_params_against_capabilities(
        {"input_mode": REFERENCE_ASSETS},
        _capabilities(CONSISTENT_SLUG),
    )
    assert cleaned["aspect_ratio"] == "16:9"


def test_omitting_the_mode_leaves_params_as_they_were() -> None:
    """Existing clients send no mode, and their quotes must not change shape."""

    cleaned = validate_params_against_capabilities(
        {"aspect_ratio": "16:9", "duration_sec": 8},
        _capabilities("google-veo31-lite-video-fallback"),
    )
    assert "input_mode" not in cleaned
    assert cleaned == {"aspect_ratio": "16:9", "resolution": "720p", "duration_sec": 8}


def test_mode_survives_into_the_quote_params() -> None:
    """The provider reads the mode from params, so it has to be carried through."""

    cleaned = validate_params_against_capabilities(
        {"input_mode": REFERENCE_ASSETS, "duration_sec": 8},
        _capabilities(CONSISTENT_SLUG),
    )
    assert cleaned["input_mode"] == REFERENCE_ASSETS


def test_consistent_route_is_not_an_extending_route() -> None:
    """Reference images and the extension chain are mutually exclusive at Google.

    Keeping the workflow block off this row is what stops a request from carrying
    `video` and `referenceImages` together.
    """

    capabilities = _capabilities(CONSISTENT_SLUG)
    assert "workflow" not in capabilities

    extended = _capabilities("google-veo31-fast-extended-video")
    assert extended["workflow"]["type"] == "veo_extend"
    assert declared_modes(extended).keys() == {DEFAULT_MODE}
