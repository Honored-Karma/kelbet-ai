"""Canonical subscription plan seed rows (used by migration and tests).

Economics, all verified against measured provider cost:

    one credit          == $0.004 of provider spend
    Telegram payout     == $0.013 per star
    generosity ceiling  == 3.25 * (1 - target_margin) credits per star

A plan may therefore hand out at most 1.30 credits per star at a 60% target margin,
or 1.63 at 50%. The grid below runs 1.305 -> 1.566 credits per star, i.e. a 59.8%
margin on the entry plan easing to 51.8% on the top plan: bigger commitments buy a
better rate, which is the whole point of a subscription, and nothing drops below 50%.

Subscriptions are deliberately more generous per star than every top-up pack in
`kelbet.payments.seeds`. A pack that beat a subscription would make the pack the
rational purchase and quietly kill recurring revenue — the shipped catalog had
exactly that inversion before it was corrected.

Tenge prices are derived from the market, not from "stars plus a margin". At a 1.5%
Halyk ePay fee and 473.59 KZT/USD they hold a flat 65% margin — better than the Stars
channel, because Telegram keeps roughly 35% of every star payment. A card payment is
also cheaper for the buyer: 599 stars costs about $22.60 through the App Store, while
Pro on a card costs $9.86.

Credits do not expire and unused balance carries over indefinitely. That is a
deliberate trust position against competitors whose credits burn, and it costs
nothing: the margin above is computed at 100% utilisation, so any unspent credit is
pure upside rather than a liability.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

START_PLAN_ID = UUID("33333333-3333-3333-3333-333333333301")
PRO_PLAN_ID = UUID("33333333-3333-3333-3333-333333333302")
STUDIO_PLAN_ID = UUID("33333333-3333-3333-3333-333333333303")
BUSINESS_PLAN_ID = UUID("33333333-3333-3333-3333-333333333304")

#: Telegram's payout to the developer per star. Not contractually fixed — treat the
#: 0.012-0.015 band as the planning range and re-derive the grid if it moves.
STAR_PAYOUT_USD = 0.013
#: One credit is defined as this much provider spend. Mirrors catalog.seeds.
CREDIT_COST_USD = 0.004
#: Halyk ePay retains ~1.5%, and its built-in fiscalisation satisfies the Kazakh
#: online-till requirement for card payments from individuals.
CARD_SETTLEMENT_RATE = 0.985
KZT_PER_USD = 473.59

#: No plan may fall below this gross margin at full credit utilisation.
MIN_PLAN_MARGIN = 0.50
#: Ceiling implied by MIN_PLAN_MARGIN: 0.013 / 0.004 * (1 - 0.50).
MAX_CREDITS_PER_STAR = 1.625

DEFAULT_PERIOD_DAYS = 30


def credits_per_star(credits: int, stars: int) -> float:
    return credits / stars


def stars_margin(credits: int, stars: int) -> float:
    revenue = stars * STAR_PAYOUT_USD
    return 1 - (credits * CREDIT_COST_USD) / revenue


def card_margin(credits: int, price_kzt: int) -> float:
    revenue = price_kzt / KZT_PER_USD * CARD_SETTLEMENT_RATE
    return 1 - (credits * CREDIT_COST_USD) / revenue


def subscription_plan_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": START_PLAN_ID,
            "slug": "start",
            "plan_key": "start",
            "stars": 249,
            "price_kzt": 1790,
            "credits_per_period": 325,
            "period_days": DEFAULT_PERIOD_DAYS,
            "referral_percent": 3,
            "enabled": True,
            "display_order": 10,
            "localization": {
                "ru": {
                    "name": "Старт",
                    "description": "Около 30 картинок или 6 коротких роликов в месяц",
                },
                "kk": {
                    "name": "Бастау",
                    "description": "Айына шамамен 30 сурет немесе 6 қысқа бейне",
                },
            },
        },
        {
            "id": PRO_PLAN_ID,
            "slug": "pro",
            "plan_key": "pro",
            "stars": 599,
            "price_kzt": 4670,
            "credits_per_period": 850,
            "period_days": DEFAULT_PERIOD_DAYS,
            "referral_percent": 5,
            "enabled": True,
            "display_order": 20,
            "localization": {
                "ru": {
                    "name": "Про",
                    "description": "Около 85 картинок или 17 роликов в месяц",
                },
                "kk": {
                    "name": "Про",
                    "description": "Айына шамамен 85 сурет немесе 17 бейне",
                },
            },
        },
        {
            "id": STUDIO_PLAN_ID,
            "slug": "studio",
            "plan_key": "studio",
            "stars": 1490,
            "price_kzt": 12360,
            "credits_per_period": 2250,
            "period_days": DEFAULT_PERIOD_DAYS,
            "referral_percent": 7,
            "enabled": True,
            "display_order": 30,
            "localization": {
                "ru": {
                    "name": "Студия",
                    "description": "Для постоянного контента и небольших команд",
                },
                "kk": {
                    "name": "Студия",
                    "description": "Тұрақты контент пен шағын командаларға",
                },
            },
        },
        {
            "id": BUSINESS_PLAN_ID,
            "slug": "business",
            "plan_key": "business",
            "stars": 3990,
            "price_kzt": 34340,
            "credits_per_period": 6250,
            "period_days": DEFAULT_PERIOD_DAYS,
            "referral_percent": 10,
            "enabled": True,
            "display_order": 40,
            "localization": {
                "ru": {
                    "name": "Бизнес",
                    "description": "Максимальный объём и приоритетная очередь",
                },
                "kk": {
                    "name": "Бизнес",
                    "description": "Ең жоғары көлем және басым кезек",
                },
            },
        },
    ]
