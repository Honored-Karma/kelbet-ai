"""Economics and period-math guards for recurring plans.

These are pure unit tests: no database, so they run everywhere and fail fast in CI.
Grant idempotency has two independent mechanisms — the UNIQUE(subscription_id,
period_index) constraint and the wallet ledger key — and both need a live Postgres to
exercise, so they belong in the integration suite rather than here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kelbet.domain.enums import Plan, SubscriptionStatus
from kelbet.payments.seeds import payment_product_rows
from kelbet.services.subscription import (
    grant_idempotency_key,
    period_end,
)
from kelbet.subscriptions.seeds import (
    MAX_CREDITS_PER_STAR,
    MIN_PLAN_MARGIN,
    STAR_PAYOUT_USD,
    card_margin,
    credits_per_star,
    stars_margin,
    subscription_plan_rows,
)


def _ordered_plans() -> list[dict[str, object]]:
    return sorted(subscription_plan_rows(), key=lambda row: int(row["stars"]))


def test_every_plan_key_is_a_known_plan_enum_member() -> None:
    """users.plan is written from plan_key, so a typo would create an unreadable user."""
    known = {member.value for member in Plan}
    for row in subscription_plan_rows():
        assert row["plan_key"] in known, row["slug"]
        assert row["plan_key"] != Plan.FREE.value, "a paid plan cannot map to free"


def test_plan_slugs_and_keys_are_unique() -> None:
    rows = subscription_plan_rows()
    slugs = [row["slug"] for row in rows]
    keys = [row["plan_key"] for row in rows]
    assert len(set(slugs)) == len(slugs)
    assert len(set(keys)) == len(keys)


def test_no_plan_falls_below_the_margin_floor_on_stars() -> None:
    for row in _ordered_plans():
        credits = int(row["credits_per_period"])
        stars = int(row["stars"])
        margin = stars_margin(credits, stars)
        assert margin >= MIN_PLAN_MARGIN, (
            f"{row['slug']} margin is {margin:.1%}, below the {MIN_PLAN_MARGIN:.0%} floor"
        )
        assert credits_per_star(credits, stars) <= MAX_CREDITS_PER_STAR, (
            f"{row['slug']} grants {credits_per_star(credits, stars):.3f} credits per "
            f"star, above the {MAX_CREDITS_PER_STAR} generosity ceiling"
        )


def test_generosity_ceiling_matches_the_margin_floor() -> None:
    """The ceiling is not a magic number: it is payout/cost * (1 - floor)."""
    derived = STAR_PAYOUT_USD / 0.004 * (1 - MIN_PLAN_MARGIN)
    assert MAX_CREDITS_PER_STAR == pytest.approx(derived, abs=1e-9)


def test_bigger_plans_are_a_better_deal_never_a_worse_one() -> None:
    previous = 0.0
    for row in _ordered_plans():
        rate = credits_per_star(int(row["credits_per_period"]), int(row["stars"]))
        assert rate >= previous, f"{row['slug']} offers a worse rate than a cheaper plan"
        previous = rate


def test_every_plan_beats_every_top_up_pack() -> None:
    """A pack that beats a subscription makes the pack the rational purchase.

    The shipped catalog had exactly that inversion: the studio pack granted 1.25
    credits per star, more than the planned entry subscription.
    """
    best_pack_rate = max(
        credits_per_star(int(row["credits"]), int(row["stars"]))
        for row in payment_product_rows()
    )
    for row in subscription_plan_rows():
        rate = credits_per_star(int(row["credits_per_period"]), int(row["stars"]))
        assert rate > best_pack_rate, (
            f"{row['slug']} at {rate:.3f} credits per star does not beat the best pack "
            f"at {best_pack_rate:.3f}"
        )


def test_card_prices_hold_a_better_margin_than_stars() -> None:
    """Telegram keeps ~35% of a star payment; a card keeps ~1.5%.

    The card channel must therefore be strictly more profitable per credit, otherwise
    the tenge price was derived from the star price instead of from the market.
    """
    for row in subscription_plan_rows():
        price_kzt = row["price_kzt"]
        assert price_kzt is not None, f"{row['slug']} has no tenge price"
        credits = int(row["credits_per_period"])
        card = card_margin(credits, int(price_kzt))
        stars = stars_margin(credits, int(row["stars"]))
        assert card > stars, f"{row['slug']}: card {card:.1%} <= stars {stars:.1%}"
        assert 0.60 <= card <= 0.70, f"{row['slug']} card margin {card:.1%} off target"


def test_referral_percent_grows_with_the_plan_and_stays_affordable() -> None:
    """Referral is paid in credits, so its real cost is the provider cost, not face
    value. Even the top tier at 10% costs well under the margin headroom.
    """
    previous = -1
    for row in _ordered_plans():
        percent = int(row["referral_percent"])
        assert 0 <= percent <= 20
        assert percent >= previous, f"{row['slug']} pays a smaller share than a cheaper plan"
        previous = percent

        credits = int(row["credits_per_period"])
        stars = int(row["stars"])
        revenue = stars * STAR_PAYOUT_USD
        reward_cost = credits * percent / 100 * 0.004
        margin_after = 1 - (credits * 0.004 + reward_cost) / revenue
        assert margin_after >= 0.40, (
            f"{row['slug']} margin after a {percent}% referral is {margin_after:.1%}"
        )


def test_period_end_is_fixed_length_and_rejects_nonsense() -> None:
    start = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)
    assert period_end(start, 30) == start + timedelta(days=30)
    # A fixed length sidesteps the "31st of February" clamping question entirely.
    assert period_end(datetime(2026, 1, 31, tzinfo=UTC), 30) == datetime(
        2026, 3, 2, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="period_days must be positive"):
        period_end(start, 0)
    with pytest.raises(ValueError, match="period_days must be positive"):
        period_end(start, -1)


def test_grant_key_is_unique_per_period() -> None:
    subscription_id = uuid4()
    other_id = uuid4()
    first = grant_idempotency_key(subscription_id, 0)
    second = grant_idempotency_key(subscription_id, 1)
    assert first != second
    assert grant_idempotency_key(other_id, 0) != first
    # Stable across calls: the key is what makes a replayed renewal a no-op.
    assert grant_idempotency_key(subscription_id, 0) == first
    assert first.startswith("plan_grant:")


def test_subscription_status_values_match_the_db_check_constraint() -> None:
    """migrations/0023 pins these three literals in a CHECK constraint."""
    assert {member.value for member in SubscriptionStatus} == {
        "active",
        "cancelling",
        "expired",
    }
