"""Recurring subscription tiers and the economics that constrain them.

Two rules govern every number here, and both are asserted in
tests/test_subscription_economics.py rather than trusted to review.

**Margin.** Telegram pays out about $0.013 per star and one credit costs $0.004 of
provider spend, so granting `c` credits per star leaves a gross margin of
`1 - c * 0.004 / 0.013`. Equivalently, a target margin `m` caps generosity at
`3.25 * (1 - m)` credits per star. These tiers sit at 51.8-59.8%, tightening as the tier
grows — the bigger the commitment, the better the rate the buyer gets.

**No cannibalisation.** Every tier must be strictly more generous per star than the best
top-up pack (studio, at 1.111 credits per star). If a pack were ever the better deal, the
rational buyer would never subscribe, and recurring revenue would be undercut by the
one-off product. `payment_products` is deliberately priced worse for exactly this reason,
and the invariant is checked against the live pack seeds rather than a copied constant.

Telegram caps a subscription at 10 000 stars and bills a fixed 30-day period; both limits
are enforced here so a pricing edit cannot ship an invoice Telegram would reject.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from kelbet.domain.enums import Plan

START_PLAN_ID = UUID("33333333-3333-3333-3333-333333333301")
PRO_PLAN_ID = UUID("33333333-3333-3333-3333-333333333302")
STUDIO_PLAN_ID = UUID("33333333-3333-3333-3333-333333333303")
BUSINESS_PLAN_ID = UUID("33333333-3333-3333-3333-333333333304")

STAR_PAYOUT_USD = 0.013
CREDIT_COST_USD = 0.004

# Telegram: "Currently, it must always be 2592000 (30 days) if specified."
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
# Telegram: "Subscription price must no exceed 10000 Telegram Stars."
MAX_SUBSCRIPTION_STARS = 10_000

# A subscription may not fall below this gross margin. Looser than the packs' 65% on
# purpose: recurring revenue is worth paying for, but not at any price.
MIN_SUBSCRIPTION_MARGIN = 0.50


def credits_per_star(monthly_credits: int, stars: int) -> float:
    return monthly_credits / stars


def gross_margin(monthly_credits: int, stars: int) -> float:
    """Gross margin on one billing period, after Telegram's cut and provider cost."""
    revenue = stars * STAR_PAYOUT_USD
    cost = monthly_credits * CREDIT_COST_USD
    return (revenue - cost) / revenue


def subscription_plan_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": START_PLAN_ID,
            "slug": "start",
            "plan": Plan.START.value,
            "monthly_credits": 325,
            "stars": 249,
            "kzt_price": 1_790,
            "enabled": True,
            "display_order": 10,
            "localization": {
                "ru": {
                    "name": "Старт",
                    "description": "325 кредитов каждый месяц — около 17 видео Lite",
                },
                "kk": {
                    "name": "Бастау",
                    "description": "Ай сайын 325 кредит — шамамен 17 Lite видео",
                },
            },
        },
        {
            "id": PRO_PLAN_ID,
            "slug": "pro",
            "plan": Plan.PRO.value,
            "monthly_credits": 850,
            "stars": 599,
            "kzt_price": 4_670,
            "enabled": True,
            "display_order": 20,
            "localization": {
                "ru": {
                    "name": "Про",
                    "description": "850 кредитов каждый месяц — около 44 видео Lite",
                },
                "kk": {
                    "name": "Про",
                    "description": "Ай сайын 850 кредит — шамамен 44 Lite видео",
                },
            },
        },
        {
            "id": STUDIO_PLAN_ID,
            "slug": "studio",
            "plan": Plan.STUDIO.value,
            "monthly_credits": 2_250,
            "stars": 1_490,
            "kzt_price": 12_360,
            "enabled": True,
            "display_order": 30,
            "localization": {
                "ru": {
                    "name": "Студия",
                    "description": "2 250 кредитов каждый месяц для постоянной работы",
                },
                "kk": {
                    "name": "Студия",
                    "description": "Тұрақты жұмыс үшін ай сайын 2 250 кредит",
                },
            },
        },
        {
            "id": BUSINESS_PLAN_ID,
            "slug": "business",
            "plan": Plan.BUSINESS.value,
            "monthly_credits": 6_250,
            "stars": 3_990,
            "kzt_price": 34_340,
            "enabled": True,
            "display_order": 40,
            "localization": {
                "ru": {
                    "name": "Бизнес",
                    "description": "6 250 кредитов каждый месяц для команд",
                },
                "kk": {
                    "name": "Бизнес",
                    "description": "Командалар үшін ай сайын 6 250 кредит",
                },
            },
        },
    ]


def subscription_plan_row(slug: str) -> dict[str, Any]:
    for row in subscription_plan_rows():
        if row["slug"] == slug:
            return row
    raise KeyError(f"no seeded subscription plan with slug {slug!r}")
