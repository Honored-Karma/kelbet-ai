"""Integer pricing helpers for catalog quotes."""

from __future__ import annotations

from typing import Any

from kelbet.catalog.video_inputs import (
    DEFAULT_MODE,
    narrow_aspect_ratios,
    resolve_mode,
)
from kelbet.domain.exceptions import InvalidQuoteParamsError


def mul_ceil(amount: int, num: int, den: int) -> int:
    """Multiply `amount` by num/den and round up (integer-only)."""
    if den <= 0 or num < 0:
        msg = f"Invalid multiplier num={num} den={den}"
        raise ValueError(msg)
    if amount < 0:
        msg = "amount must be non-negative"
        raise ValueError(msg)
    return (amount * num + den - 1) // den


def _factor(rules: dict[str, Any] | None, group: str, key: str) -> tuple[int, int]:
    if not rules:
        return 1, 1
    group_map = rules.get(group) or {}
    raw = group_map.get(key)
    if raw is None:
        return 1, 1
    num = int(raw["num"])
    den = int(raw["den"])
    if den <= 0 or num < 0:
        raise InvalidQuoteParamsError(f"Invalid pricing factor for {group}.{key}")
    return num, den


def validate_params_against_capabilities(
    params: dict[str, Any],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    """Normalize and validate quote params; return cleaned params."""
    cleaned: dict[str, Any] = {}

    # Resolved first because it can narrow what follows: reference images are
    # accepted at fewer aspect ratios than plain generation, so the mode has to
    # be known before an aspect ratio is validated or defaulted.
    mode = resolve_mode(capabilities, params.get("input_mode"))
    if params.get("input_mode") is not None or mode.name != DEFAULT_MODE:
        cleaned["input_mode"] = mode.name

    aspect = params.get("aspect_ratio")
    allowed_aspects = narrow_aspect_ratios(capabilities.get("aspect_ratios"), mode)
    if aspect is not None:
        if not allowed_aspects or aspect not in allowed_aspects:
            raise InvalidQuoteParamsError(
                f"Unsupported aspect_ratio: {aspect}"
                if mode.name == DEFAULT_MODE
                else f"aspect_ratio {aspect} is not supported with input_mode {mode.name}"
            )
        cleaned["aspect_ratio"] = aspect
    elif allowed_aspects:
        cleaned["aspect_ratio"] = allowed_aspects[0]

    resolution = params.get("resolution")
    allowed_res = capabilities.get("resolutions")
    if resolution is not None:
        if not allowed_res or resolution not in allowed_res:
            raise InvalidQuoteParamsError(f"Unsupported resolution: {resolution}")
        cleaned["resolution"] = resolution
    elif allowed_res:
        cleaned["resolution"] = allowed_res[0]

    duration = params.get("duration_sec")
    allowed_durations = capabilities.get("durations_sec")
    if duration is not None:
        if not allowed_durations or int(duration) not in [int(x) for x in allowed_durations]:
            raise InvalidQuoteParamsError(f"Unsupported duration_sec: {duration}")
        cleaned["duration_sec"] = int(duration)
    elif allowed_durations:
        cleaned["duration_sec"] = int(allowed_durations[0])

    seed = params.get("seed")
    if seed is not None:
        if not capabilities.get("supports_seed"):
            raise InvalidQuoteParamsError("seed is not supported for this model")
        cleaned["seed"] = int(seed)

    scale_factor = params.get("scale_factor")
    allowed_scale_factors = capabilities.get("scale_factors")
    if scale_factor is not None:
        normalized_scale = int(scale_factor)
        if not allowed_scale_factors or normalized_scale not in [
            int(value) for value in allowed_scale_factors
        ]:
            raise InvalidQuoteParamsError(f"Unsupported scale_factor: {scale_factor}")
        cleaned["scale_factor"] = normalized_scale
    elif allowed_scale_factors:
        cleaned["scale_factor"] = int(allowed_scale_factors[0])

    flavor = params.get("flavor")
    allowed_flavors = capabilities.get("flavors")
    if flavor is not None:
        if not allowed_flavors or flavor not in allowed_flavors:
            raise InvalidQuoteParamsError(f"Unsupported flavor: {flavor}")
        cleaned["flavor"] = str(flavor)
    elif allowed_flavors:
        cleaned["flavor"] = str(allowed_flavors[0])

    defaults = capabilities.get("defaults") or {}
    for key in ("sharpen", "smart_grain", "ultra_detail"):
        value = params.get(key, defaults.get(key))
        if value is None:
            continue
        normalized = int(value)
        if normalized < 0 or normalized > 100:
            raise InvalidQuoteParamsError(f"{key} must be between 0 and 100")
        cleaned[key] = normalized

    # Reject unknown keys that look like pricing knobs
    allowed_keys = {
        "aspect_ratio",
        "resolution",
        "duration_sec",
        "seed",
        "scale_factor",
        "flavor",
        "input_mode",
        "sharpen",
        "smart_grain",
        "ultra_detail",
    }
    unknown = set(params) - allowed_keys
    if unknown:
        raise InvalidQuoteParamsError(f"Unknown params: {sorted(unknown)}")

    return cleaned


def credit_price_range(
    base_price: int,
    *,
    capabilities: dict[str, Any],
    pricing_rules: dict[str, Any] | None,
) -> tuple[int, int]:
    """Cheapest and dearest quote a model can produce, over every reachable option.

    A single "from" price misleads once a model spans a 10x range: Kling O3 4K starts
    at 525 credits and reaches 1050, and a user who sees only the lower number finds
    out at the confirmation step. Aspect ratio is ignored because it never moves the
    price — only resolution, duration and scale factor do.
    """
    # A single `None` stands for "this model has no such knob", which keeps the loop
    # below one shape instead of three nested special cases.
    resolutions: list[str | None] = [
        str(value) for value in (capabilities.get("resolutions") or [])
    ]
    durations: list[int | None] = [
        int(value) for value in (capabilities.get("durations_sec") or [])
    ]
    scale_factors: list[int | None] = [
        int(value) for value in (capabilities.get("scale_factors") or [])
    ]
    resolutions = resolutions or [None]
    durations = durations or [None]
    scale_factors = scale_factors or [None]

    prices: list[int] = []
    for resolution in resolutions:
        for duration in durations:
            for scale_factor in scale_factors:
                params: dict[str, Any] = {}
                if resolution is not None:
                    params["resolution"] = resolution
                if duration is not None:
                    params["duration_sec"] = duration
                if scale_factor is not None:
                    params["scale_factor"] = scale_factor
                prices.append(
                    compute_user_credit_price(
                        base_price,
                        params=params,
                        pricing_rules=pricing_rules,
                    )
                )
    return min(prices), max(prices)


def compute_user_credit_price(
    base_price: int,
    *,
    params: dict[str, Any],
    pricing_rules: dict[str, Any] | None,
) -> int:
    if base_price <= 0:
        msg = "base_price must be positive"
        raise ValueError(msg)

    price = base_price
    if "resolution" in params:
        num, den = _factor(pricing_rules, "resolution_multipliers", str(params["resolution"]))
        price = mul_ceil(price, num, den)
    if "duration_sec" in params:
        num, den = _factor(pricing_rules, "duration_multipliers", str(params["duration_sec"]))
        price = mul_ceil(price, num, den)
    if "scale_factor" in params:
        num, den = _factor(
            pricing_rules,
            "scale_factor_multipliers",
            str(params["scale_factor"]),
        )
        price = mul_ceil(price, num, den)
    return price
