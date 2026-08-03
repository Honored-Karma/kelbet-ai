"""Pricing invariants for the recurring tiers.

These are the constraints that a repricing edit is most likely to break quietly, because
breaking them produces a plausible-looking number rather than an error. Each one is
checked against the live seeds, so the guard cannot drift from what is actually sold.
"""

from __future__ import annotations

from kelbet.domain.enums import Plan
from kelbet.payments import payment_product_rows
from kelbet.subscriptions import (
    MAX_SUBSCRIPTION_STARS,
    MIN_SUBSCRIPTION_MARGIN,
    SUBSCRIPTION_PERIOD_SECONDS,
    credits_per_star,
    gross_margin,
    subscription_plan_rows,
)


def test_every_tier_holds_the_minimum_gross_margin() -> None:
    """Generosity is capped by arithmetic, not by judgement. At a $0.013 payout per star
    and $0.004 per credit, granting more than 3.25 * (1 - margin) credits per star sells
    the period below the intended margin."""
    for row in subscription_plan_rows():
        margin = gross_margin(int(row["monthly_credits"]), int(row["stars"]))
        rate = credits_per_star(int(row["monthly_credits"]), int(row["stars"]))
        assert margin >= MIN_SUBSCRIPTION_MARGIN, (
            f"tier {row['slug']} grants {rate:.3f} credits per star, leaving a "
            f"{margin:.1%} margin, below the {MIN_SUBSCRIPTION_MARGIN:.0%} floor"
        )


def test_no_pack_is_ever_a_better_deal_than_a_subscription() -> None:
    """If a one-off pack gave more credits per star than a tier, the rational buyer would
    never subscribe and the packs would cannibalise recurring revenue. Compared against
    the live pack seeds rather than a copied constant, so repricing either side is caught."""
    best_pack = max(
        payment_product_rows(),
        key=lambda row: credits_per_star(int(row["credits"]), int(row["stars"])),
    )
    best_pack_rate = credits_per_star(int(best_pack["credits"]), int(best_pack["stars"]))

    for row in subscription_plan_rows():
        tier_rate = credits_per_star(int(row["monthly_credits"]), int(row["stars"]))
        assert tier_rate > best_pack_rate, (
            f"tier {row['slug']} gives {tier_rate:.3f} credits per star while pack "
            f"{best_pack['slug']} gives {best_pack_rate:.3f} — the pack would be the "
            "rational purchase and undercut the subscription"
        )


def test_bigger_tiers_are_strictly_better_value() -> None:
    """A tier that costs more but gives a worse rate has no reason to be bought, and the
    non-monotonic pack grid this project already had to fix shows it happens by accident."""
    ordered = sorted(subscription_plan_rows(), key=lambda row: int(row["stars"]))
    rates = [
        (row["slug"], credits_per_star(int(row["monthly_credits"]), int(row["stars"])))
        for row in ordered
    ]
    for (lower_slug, lower_rate), (higher_slug, higher_rate) in zip(rates, rates[1:], strict=False):
        assert higher_rate > lower_rate, (
            f"{higher_slug} costs more than {lower_slug} but gives {higher_rate:.3f} "
            f"credits per star against {lower_rate:.3f}"
        )
    # Credits and price must climb together, or the display order lies to the buyer.
    assert [int(row["monthly_credits"]) for row in ordered] == sorted(
        int(row["monthly_credits"]) for row in ordered
    )
    assert [int(row["display_order"]) for row in ordered] == sorted(
        int(row["display_order"]) for row in ordered
    )


def test_prices_stay_inside_the_limits_telegram_enforces() -> None:
    """Telegram: "Subscription price must no exceed 10000 Telegram Stars" and the period
    "must always be 2592000 (30 days)". Violating either is rejected at invoice creation,
    so the check belongs here rather than in a provider error at runtime."""
    assert SUBSCRIPTION_PERIOD_SECONDS == 2_592_000
    for row in subscription_plan_rows():
        stars = int(row["stars"])
        assert 1 <= stars <= MAX_SUBSCRIPTION_STARS, (
            f"tier {row['slug']} is priced at {stars} stars, outside Telegram's 1-"
            f"{MAX_SUBSCRIPTION_STARS} range for subscriptions"
        )


def test_every_tier_maps_to_a_distinct_real_plan() -> None:
    """The plan value ends up on `users.plan`, so an unknown or duplicated value would
    either fail to parse or make two tiers indistinguishable in entitlement checks."""
    rows = subscription_plan_rows()
    plans = [row["plan"] for row in rows]
    assert len(set(plans)) == len(plans)
    assert Plan.FREE.value not in plans, "free is the absence of a subscription, not a tier"
    for plan in plans:
        Plan(plan)  # raises if the seed names a plan the enum does not define
    slugs = [row["slug"] for row in rows]
    assert len(set(slugs)) == len(slugs)


def test_card_prices_are_cheaper_for_the_buyer_than_stars() -> None:
    """Card is the higher-margin channel and must also be the better deal for the user, or
    there is no reason for anyone to use it. Stars bought in-app cost the buyer roughly
    $0.0377 each; the tenge price is compared at 473.59 KZT per dollar."""
    app_store_usd_per_star = 0.0377
    kzt_per_usd = 473.59
    for row in subscription_plan_rows():
        kzt_price = row["kzt_price"]
        assert kzt_price is not None, f"tier {row['slug']} has no card price"
        card_usd = int(kzt_price) / kzt_per_usd
        stars_usd = int(row["stars"]) * app_store_usd_per_star
        assert card_usd < stars_usd, (
            f"tier {row['slug']} costs ${card_usd:.2f} by card against ${stars_usd:.2f} "
            "in stars — the cheaper channel for us must not be the dearer one for the buyer"
        )
