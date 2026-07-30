"""Unit tests for integer pricing engine."""

import pytest

from kelbet.catalog.pricing import (
    compute_user_credit_price,
    mul_ceil,
    validate_params_against_capabilities,
)
from kelbet.domain.exceptions import InvalidQuoteParamsError


def test_mul_ceil() -> None:
    assert mul_ceil(8, 3, 2) == 12
    assert mul_ceil(5, 1, 1) == 5
    assert mul_ceil(1, 3, 2) == 2


def test_compute_resolution_multiplier() -> None:
    rules = {
        "resolution_multipliers": {
            "720p": {"num": 1, "den": 1},
            "1080p": {"num": 3, "den": 2},
        }
    }
    assert compute_user_credit_price(8, params={"resolution": "720p"}, pricing_rules=rules) == 8
    assert compute_user_credit_price(8, params={"resolution": "1080p"}, pricing_rules=rules) == 12


def test_compute_duration_multiplier() -> None:
    rules = {"duration_multipliers": {"5": {"num": 1, "den": 1}, "10": {"num": 2, "den": 1}}}
    assert compute_user_credit_price(25, params={"duration_sec": 5}, pricing_rules=rules) == 25
    assert compute_user_credit_price(25, params={"duration_sec": 10}, pricing_rules=rules) == 50


def test_validate_params_defaults_and_rejects() -> None:
    caps = {
        "aspect_ratios": ["1:1", "16:9"],
        "resolutions": ["720p", "1080p"],
        "supports_seed": True,
    }
    cleaned = validate_params_against_capabilities({}, caps)
    assert cleaned["aspect_ratio"] == "1:1"
    assert cleaned["resolution"] == "720p"

    with pytest.raises(InvalidQuoteParamsError):
        validate_params_against_capabilities({"resolution": "4k"}, caps)


def test_upscale_params_are_capability_bound() -> None:
    caps = {
        "scale_factors": [2],
        "flavors": ["photo", "photo_denoiser"],
        "defaults": {"sharpen": 40, "smart_grain": 20, "ultra_detail": 50},
    }
    cleaned = validate_params_against_capabilities({}, caps)
    assert cleaned == {
        "scale_factor": 2,
        "flavor": "photo",
        "sharpen": 40,
        "smart_grain": 20,
        "ultra_detail": 50,
    }

    with pytest.raises(InvalidQuoteParamsError):
        validate_params_against_capabilities({"scale_factor": 4}, caps)
    with pytest.raises(InvalidQuoteParamsError):
        validate_params_against_capabilities({"sharpen": 101}, caps)
