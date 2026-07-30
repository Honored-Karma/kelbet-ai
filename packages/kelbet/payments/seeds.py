"""Editable launch packages; Stars economics must be reviewed before enabling payments."""

from __future__ import annotations

from typing import Any
from uuid import UUID

STARTER_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222201")
CREATOR_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222202")
STUDIO_PRODUCT_ID = UUID("22222222-2222-2222-2222-222222222203")


def payment_product_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": STARTER_PRODUCT_ID,
            "slug": "starter",
            "credits": 100,
            "stars": 100,
            "enabled": True,
            "display_order": 10,
            "localization": {
                "ru": {
                    "name": "Старт",
                    "description": "10 быстрых изображений или 1 короткое видео",
                },
                "kk": {
                    "name": "Бастау",
                    "description": "10 жылдам сурет немесе 1 қысқа видео",
                },
            },
        },
        {
            "id": CREATOR_PRODUCT_ID,
            "slug": "creator",
            "credits": 300,
            "stars": 270,
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
            "stars": 640,
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
