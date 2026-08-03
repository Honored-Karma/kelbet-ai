"""Editable launch packages; Stars economics must be reviewed before enabling payments.

Credit-per-star rates are deliberately monotonic: the bigger the pack, the better the
rate, but every pack stays worse than any future subscription so top-ups can never
cannibalise a subscription. At a $0.013 Telegram payout per star and $0.004 provider
cost per credit, the rates below hold a 65-69% gross margin.

    starter  100 cr / 99  XTR -> 1.010 cr per star -> 68.9% margin
    creator  300 cr / 285 XTR -> 1.053 cr per star -> 67.6% margin
    studio   800 cr / 720 XTR -> 1.111 cr per star -> 65.8% margin

The previous studio rate of 1.25 cr per star (800/640) was more generous than the
planned Start subscription, which would have made the pack the rational purchase and
undercut recurring revenue.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

STARTER_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222201")
CREATOR_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222202")
STUDIO_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222203")

# Telegram pays out roughly $0.013 per star; one credit costs $0.004 of provider
# spend. A pack may never grant more than 3.25 * (1 - target_margin) credits per star.
STAR_PAYOUT_USD = 0.013
CREDIT_COST_USD = 0.004
MAX_CREDITS_PER_STAR = 1.30  # ceiling at a 60% target gross margin


def payment_product_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": STARTER_PRODUCT_ID,
            "slug": "starter",
            "credits": 100,
            "stars": 99,
            "enabled": True,
            "display_order": 10,
            "localization": {
                "ru": {
                    "name": "Старт",
                    "description": "10 быстрых изображений или 2 коротких видео",
                },
                "kk": {
                    "name": "Бастау",
                    "description": "10 жылдам сурет немесе 2 қысқа видео",
                },
            },
        },
        {
            "id": CREATOR_PRODUCT_ID,
            "slug": "creator",
            "credits": 300,
            "stars": 285,
            "enabled": True,
            "display_order": 20,
            "localization": {
                "ru": {
                    "name": "Креатор",
                    "description": "Для регулярного контента и экспериментов",
                },
                "kk": {
                    "name": "Креатор",
                    "description": "Тұрақты контент пен тәжірибелерге арналған",
                },
            },
        },
        {
            "id": STUDIO_PRODUCT_ID,
            "slug": "studio",
            "credits": 800,
            "stars": 720,
            "enabled": True,
            "display_order": 30,
            "localization": {
                "ru": {
                    "name": "Студия",
                    "description": "Большой пакет для бизнеса и команд",
                },
                "kk": {
                    "name": "Студия",
                    "description": "Бизнес пен командаларға арналған үлкен пакет",
                },
            },
        },
    ]


def payment_product_row(slug: str) -> dict[str, Any]:
    """Look up one seeded pack by slug.

    Tests and callers that need a pack's star price should read it from here rather than
    hardcoding it. Repricing a pack used to silently invalidate assertions written as
    literals, which is how a stale `100` outlived the move of `starter` to 99 stars.
    """
    for row in payment_product_rows():
        if row["slug"] == slug:
            return row
    raise KeyError(f"no seeded payment product with slug {slug!r}")
