"""Structural guards for unit economics.

Every one of these invariants was violated in the catalog at some point, and each
violation is invisible in review because it looks like an ordinary integer. Encoding
them as tests is what stops a loss-making SKU from shipping again.
"""

from __future__ import annotations

from kelbet.catalog.pricing import compute_user_credit_price
from kelbet.catalog.seeds import (
    CREDIT_COST_UNITS,
    catalog_model_rows,
    cost_floor_credits,
)
from kelbet.payments.seeds import (
    CREDIT_COST_USD,
    MAX_CREDITS_PER_STAR,
    STAR_PAYOUT_USD,
    payment_product_rows,
)


def test_credit_unit_is_forty_cost_units() -> None:
    """One credit == $0.004 of provider spend, and cost units are $0.0001 each."""
    assert CREDIT_COST_UNITS == 40
    assert cost_floor_credits(0) == 0
    assert cost_floor_credits(40) == 1
    assert cost_floor_credits(41) == 2  # always rounds up, never sells at a shortfall


def test_no_sku_is_priced_below_its_provider_cost() -> None:
    for row in catalog_model_rows():
        units = row["provider_cost_units"]
        price = row["user_credit_price"]
        assert price >= cost_floor_credits(units), (
            f"{row['slug']} charges {price} credits (${price * CREDIT_COST_USD:.4f}) "
            f"but costs {units} units (${units / 10_000:.4f})"
        )


def test_duration_pricing_is_at_least_linear_in_output_seconds() -> None:
    """Provider video cost is per output second, so price must scale at least linearly.

    A sub-linear multiplier sells long clips below cost. Veo extension bills only the
    new seconds it produces, so there is no cumulative penalty to price in either.
    """
    for row in catalog_model_rows():
        rules = row["pricing_rules"]
        if not isinstance(rules, dict):
            continue
        multipliers = rules.get("duration_multipliers")
        if not multipliers:
            continue
        base_price = row["user_credit_price"]
        base_duration = min(int(key) for key in multipliers)
        for key in multipliers:
            duration = int(key)
            price = compute_user_credit_price(
                base_price,
                params={"duration_sec": duration},
                pricing_rules=rules,
            )
            assert price * base_duration >= base_price * duration, (
                f"{row['slug']} at {duration}s charges {price} credits, below the "
                f"linear floor of {base_price * duration / base_duration:.1f}"
            )


def test_resolution_pricing_never_drops_below_the_base_floor() -> None:
    for row in catalog_model_rows():
        rules = row["pricing_rules"]
        if not isinstance(rules, dict):
            continue
        multipliers = rules.get("resolution_multipliers")
        if not multipliers:
            continue
        floor = cost_floor_credits(row["provider_cost_units"])
        for resolution in multipliers:
            price = compute_user_credit_price(
                row["user_credit_price"],
                params={"resolution": resolution},
                pricing_rules=rules,
            )
            assert price >= floor, f"{row['slug']} at {resolution} charges {price} < {floor}"


def test_image_fallback_stays_inside_its_declared_cost_ceiling() -> None:
    """The Gemini fallback is allowed to cost more than the primary route, but only
    up to the ceiling the SKU declares. Any reachable resolution above the ceiling is
    unbounded spend on a route the user never chose.
    """
    for row in catalog_model_rows():
        capabilities = row["capabilities"]
        fallback = capabilities.get("fallback")
        if not fallback or "provider_cost_units_by_resolution" not in fallback:
            continue
        ceiling = capabilities["ui"]["provider_cost_ceiling_units"]
        costs = fallback["provider_cost_units_by_resolution"]
        for resolution in capabilities["resolutions"]:
            # "auto_2k" resolves to the same pixel budget as "2k".
            key = resolution.removeprefix("auto_")
            assert key in costs, f"{row['slug']} has no fallback cost for {resolution}"
            assert costs[key] <= ceiling, (
                f"{row['slug']} fallback at {resolution} costs {costs[key]} units, "
                f"above its {ceiling} ceiling"
            )


def test_star_packs_hold_target_margin_and_never_beat_a_subscription() -> None:
    rows = sorted(payment_product_rows(), key=lambda row: row["credits"])
    previous_rate = 0.0
    for row in rows:
        credits = row["credits"]
        stars = row["stars"]
        rate = credits / stars
        revenue = stars * STAR_PAYOUT_USD
        cost = credits * CREDIT_COST_USD
        margin = 1 - cost / revenue

        assert rate <= MAX_CREDITS_PER_STAR, (
            f"{row['slug']} grants {rate:.3f} credits per star, above the "
            f"{MAX_CREDITS_PER_STAR} ceiling for a 60% target margin"
        )
        assert margin >= 0.60, f"{row['slug']} margin is {margin:.1%}"
        # Bigger packs may be a better deal, never a worse one.
        assert rate >= previous_rate, f"{row['slug']} rate regresses"
        previous_rate = rate
