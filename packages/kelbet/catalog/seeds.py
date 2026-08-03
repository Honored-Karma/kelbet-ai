"""Canonical catalog seed rows (used by migration and tests)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

# Economics invariant. `provider_cost_units` is USD in fixed point: 1 unit == $0.0001.
# One credit is defined as $0.004 of provider cost, i.e. 40 units. Every billable SKU
# must charge at least its recorded provider cost, otherwise the sale loses money.
# `enforce_economics` below makes that structurally impossible to violate.
CREDIT_COST_UNITS = 40

MOCK_TEXT_ID = UUID("11111111-1111-1111-1111-111111111101")
MOCK_IMAGE_ID = UUID("11111111-1111-1111-1111-111111111102")
OPENROUTER_ID = UUID("11111111-1111-1111-1111-111111111103")
RUNWAY_IMAGE_ID = UUID("11111111-1111-1111-1111-111111111104")
RUNWAY_VIDEO_ID = UUID("11111111-1111-1111-1111-111111111105")
RUNWAY_FAST_IMAGE_ID = UUID("11111111-1111-1111-1111-111111111106")
RUNWAY_QUALITY_IMAGE_ID = UUID("11111111-1111-1111-1111-111111111107")
RUNWAY_FAST_EDIT_ID = UUID("11111111-1111-1111-1111-111111111108")
RUNWAY_QUALITY_EDIT_ID = UUID("11111111-1111-1111-1111-111111111109")
RUNWAY_UPSCALE_ID = UUID("11111111-1111-1111-1111-111111111110")
RUNWAY_FAST_VIDEO_ID = UUID("11111111-1111-1111-1111-111111111111")
RUNWAY_QUALITY_VIDEO_ID = UUID("11111111-1111-1111-1111-111111111112")
GOOGLE_FALLBACK_VIDEO_ID = UUID("11111111-1111-1111-1111-111111111113")
GOOGLE_EXTENDED_VIDEO_ID = UUID("11111111-1111-1111-1111-111111111116")
OPENAI_IMAGE_FAST_ID = UUID("11111111-1111-1111-1111-111111111114")
OPENAI_IMAGE_QUALITY_ID = UUID("11111111-1111-1111-1111-111111111115")
LEGACY_DISABLED_ID = UUID("11111111-1111-1111-1111-111111111199")

# SKUs whose provider cost is strictly linear in output seconds. For these, the
# duration multiplier must be duration/base_duration, never a rounded-up integer
# step: Veo bills each extension for its own new seconds only, so a 29s clip costs
# 29/8 of an 8s clip, not 4x. Charging 4x is not "safe", it just prices the SKU
# out of the market; charging less than linear sells long clips below cost.
DURATION_LINEAR_SLUGS = frozenset({"google-veo31-fast-extended-video"})


def ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)


def cost_floor_credits(provider_cost_units: int) -> int:
    """Minimum credit price that still covers recorded provider cost."""
    return ceil_div(provider_cost_units, CREDIT_COST_UNITS)


def enforce_economics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Raise any below-cost price to its floor and linearise per-second pricing.

    Declared prices in this module are already correct; this pass is a structural
    guarantee so a future edit cannot silently ship a loss-making SKU.
    """
    for row in rows:
        units = row["provider_cost_units"]
        assert isinstance(units, int)
        floor = cost_floor_credits(units)
        if row["user_credit_price"] < floor:
            row["user_credit_price"] = floor

        if row["slug"] not in DURATION_LINEAR_SLUGS:
            continue
        pricing_rules = row["pricing_rules"]
        assert isinstance(pricing_rules, dict)
        multipliers = pricing_rules["duration_multipliers"]
        assert isinstance(multipliers, dict)
        base_duration = min(int(key) for key in multipliers)
        pricing_rules["duration_multipliers"] = {
            key: {"num": int(key), "den": base_duration} for key in multipliers
        }
    return rows


def feature_flag_rows() -> list[dict[str, Any]]:
    return [
        {"key": "runway_media", "enabled": True, "payload": {}},
        {"key": "google_video", "enabled": True, "payload": {}},
        {"key": "veo_extended", "enabled": False, "payload": {}},
        {"key": "google_image", "enabled": False, "payload": {}},
        {"key": "image_fallback", "enabled": False, "payload": {}},
        {"key": "openai_image", "enabled": False, "payload": {}},
        {"key": "referrals", "enabled": False, "payload": {}},
        {"key": "experimental_upscale", "enabled": False, "payload": {}},
    ]


def catalog_model_rows() -> list[dict[str, Any]]:
    rows = [
        {
            "id": MOCK_TEXT_ID,
            "slug": "mock-text",
            "modality": "text",
            "provider": "mock",
            "provider_model_id": "mock-text-v1",
            "display_order": 10,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": None,
            "user_credit_price": 1,
            "provider_cost_units": 0,
            "currency_hint": "USD",
            "capabilities": {
                "max_prompt_chars": 2000,
                "supports_negative_prompt": False,
                "supports_seed": False,
                "max_outputs": 1,
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "forbidden",
                "accepted_mime": [],
                "max_input_bytes": 0,
            },
            "localization": {
                "ru": {"name": "Текст (Mock)", "description": "Тестовая текстовая модель"},
                "kk": {"name": "Мәтін (Mock)", "description": "Сынақ мәтін моделі"},
            },
            "pricing_rules": None,
        },
        {
            "id": MOCK_IMAGE_ID,
            "slug": "mock-image",
            "modality": "image",
            "provider": "mock",
            "provider_model_id": "mock-image-v1",
            "display_order": 20,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": None,
            "user_credit_price": 5,
            "provider_cost_units": 0,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "16:9", "9:16"],
                "resolutions": ["720p", "1080p"],
                "max_prompt_chars": 2000,
                "supports_seed": True,
                "max_outputs": 1,
                "ui": {
                    "simple_default": False,
                    "hidden_in_production": True,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "Изображение (Mock)",
                    "description": "Тестовая генерация картинок",
                },
                "kk": {
                    "name": "Сурет (Mock)",
                    "description": "Сынақ сурет генерациясы",
                },
            },
            "pricing_rules": {
                "resolution_multipliers": {
                    "720p": {"num": 1, "den": 1},
                    "1080p": {"num": 3, "den": 2},
                }
            },
        },
        {
            "id": OPENROUTER_ID,
            "slug": "openrouter-gpt-4o-mini",
            "modality": "text",
            "provider": "openrouter",
            "provider_model_id": "openai/gpt-4o-mini",
            "display_order": 30,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": None,
            # Was 1 credit ($0.004) against a recorded $0.005 cost — sold below cost.
            "user_credit_price": 2,
            "provider_cost_units": 50,
            "currency_hint": "USD",
            "capabilities": {
                "max_prompt_chars": 4000,
                "supports_seed": False,
                "max_outputs": 1,
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "forbidden",
                "accepted_mime": [],
                "max_input_bytes": 0,
            },
            "localization": {
                "ru": {
                    "name": "GPT-4o mini",
                    "description": "Быстрый текст через OpenRouter",
                },
                "kk": {
                    "name": "GPT-4o mini",
                    "description": "OpenRouter арқылы жылдам мәтін",
                },
            },
            "pricing_rules": None,
        },
        {
            "id": RUNWAY_FAST_IMAGE_ID,
            "slug": "runway-seedream5-lite-image",
            "modality": "image",
            "provider": "runway",
            "provider_model_id": "seedream5_lite",
            "display_order": 34,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            "user_credit_price": 10,
            "provider_cost_units": 400,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"],
                "resolutions": ["2k", "3k"],
                "max_prompt_chars": 4000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "create",
                    "studio_tier": "fast",
                    "smart_candidate": True,
                    "simple_default": True,
                    "hidden_in_production": False,
                    "eta_seconds": 25,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "forbidden",
                "accepted_mime": [],
                "max_input_bytes": 0,
                "max_input_assets": 0,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Fast",
                    "description": "Быстрый результат в высоком разрешении",
                },
                "kk": {
                    "name": "KELBET Fast",
                    "description": "Жоғары ажыратымдылықтағы жылдам нәтиже",
                },
            },
            "pricing_rules": None,
        },
        {
            "id": RUNWAY_QUALITY_IMAGE_ID,
            "slug": "runway-seedream5-pro-image",
            "modality": "image",
            "provider": "runway",
            "provider_model_id": "seedream5_pro",
            "display_order": 35,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            # Was 12 credits ($0.048) against $0.05 recorded cost.
            "user_credit_price": 13,
            "provider_cost_units": 500,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
                "resolutions": ["1k", "2k", "auto_1k", "auto_2k"],
                "max_prompt_chars": 4000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "create",
                    "studio_tier": "quality",
                    "smart_candidate": True,
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 45,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "forbidden",
                "accepted_mime": [],
                "max_input_bytes": 0,
                "max_input_assets": 0,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Quality",
                    "description": "Точная композиция и максимум деталей",
                },
                "kk": {
                    "name": "KELBET Quality",
                    "description": "Дәл композиция және барынша көп деталь",
                },
            },
            "pricing_rules": {
                # 2k costs $0.09 against $0.05 at 1k — a 9/5 ratio, not 5/3.
                "resolution_multipliers": {
                    "1k": {"num": 1, "den": 1},
                    "2k": {"num": 9, "den": 5},
                    "auto_1k": {"num": 1, "den": 1},
                    "auto_2k": {"num": 9, "den": 5},
                }
            },
        },
        {
            "id": RUNWAY_FAST_EDIT_ID,
            "slug": "runway-seedream5-lite-edit",
            "modality": "image_edit",
            "provider": "runway",
            "provider_model_id": "seedream5_lite",
            "display_order": 36,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            "user_credit_price": 10,
            "provider_cost_units": 400,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"],
                "resolutions": ["2k", "3k"],
                "max_prompt_chars": 4000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "edit",
                    "studio_tier": "fast",
                    "smart_candidate": True,
                    "simple_default": True,
                    "hidden_in_production": False,
                    "eta_seconds": 30,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "required",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 10,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Edit Fast",
                    "description": "Быстрое редактирование до 10 референсов",
                },
                "kk": {
                    "name": "KELBET Edit Fast",
                    "description": "10 референсқа дейін жылдам өңдеу",
                },
            },
            "pricing_rules": None,
        },
        {
            "id": RUNWAY_QUALITY_EDIT_ID,
            "slug": "runway-seedream5-pro-edit",
            "modality": "image_edit",
            "provider": "runway",
            "provider_model_id": "seedream5_pro",
            "display_order": 37,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            # Was 12 credits ($0.048) against $0.05 recorded cost.
            "user_credit_price": 13,
            "provider_cost_units": 500,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"],
                "resolutions": ["1k", "2k", "auto_1k", "auto_2k"],
                "max_prompt_chars": 4000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "edit",
                    "studio_tier": "quality",
                    "smart_candidate": True,
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 50,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "required",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 10,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Edit Quality",
                    "description": "Точное редактирование сложных сцен",
                },
                "kk": {
                    "name": "KELBET Edit Quality",
                    "description": "Күрделі көріністерді дәл өңдеу",
                },
            },
            "pricing_rules": {
                "resolution_multipliers": {
                    "1k": {"num": 1, "den": 1},
                    "2k": {"num": 9, "den": 5},
                    "auto_1k": {"num": 1, "den": 1},
                    "auto_2k": {"num": 9, "den": 5},
                }
            },
        },
        {
            "id": RUNWAY_UPSCALE_ID,
            "slug": "runway-magnific-image-upscale",
            "modality": "upscale",
            "provider": "runway",
            "provider_model_id": "magnific_precision_upscaler_v2",
            "display_order": 38,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            # Was 60 credits ($0.24) against $0.25 recorded cost.
            "user_credit_price": 63,
            "provider_cost_units": 2500,
            "currency_hint": "USD",
            "capabilities": {
                "scale_factors": [2],
                "flavors": ["photo", "photo_denoiser", "sublime"],
                "defaults": {
                    "sharpen": 40,
                    "smart_grain": 20,
                    "ultra_detail": 50,
                },
                "max_prompt_chars": 0,
                "max_outputs": 1,
                "ui": {
                    "operation": "upscale",
                    "studio_tier": "quality",
                    "simple_default": True,
                    "hidden_in_production": False,
                    "eta_seconds": 60,
                },
            },
            "input_requirements": {
                "prompt": "forbidden",
                "source_image": "required",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
                "max_input_width": 2048,
                "max_input_height": 2048,
                "require_known_dimensions": True,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Upscale 2×",
                    "description": "Увеличение и восстановление деталей",
                },
                "kk": {
                    "name": "KELBET Upscale 2×",
                    "description": "Үлкейту және детальдарды қалпына келтіру",
                },
            },
            "pricing_rules": None,
        },
        {
            "id": RUNWAY_IMAGE_ID,
            "slug": "runway-gen4-image",
            "modality": "image",
            "provider": "runway",
            "provider_model_id": "gen4_image",
            "display_order": 40,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            # Was 8 credits ($0.032) against $0.08 recorded cost — the worst gap in
            # the catalog at 2.5x below cost. Recorded cost is the 1080p figure, so
            # 720p is intentionally priced at the same floor until per-resolution
            # cost is measured and split.
            "user_credit_price": 20,
            "provider_cost_units": 800,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["1:1", "16:9", "9:16"],
                "resolutions": ["720p", "1080p"],
                "max_prompt_chars": 2000,
                "supports_seed": True,
                "max_outputs": 1,
                "ui": {
                    "operation": "create",
                    "studio_tier": "pro",
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 45,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 3,
            },
            "localization": {
                "ru": {
                    "name": "Runway Gen-4 Image",
                    "description": "Изображения через Runway",
                },
                "kk": {
                    "name": "Runway Gen-4 Image",
                    "description": "Runway арқылы суреттер",
                },
            },
            "pricing_rules": {
                "resolution_multipliers": {
                    "720p": {"num": 1, "den": 1},
                    "1080p": {"num": 3, "den": 2},
                }
            },
        },
        {
            "id": RUNWAY_VIDEO_ID,
            "slug": "runway-gen3-video",
            "modality": "video",
            "provider": "runway",
            "provider_model_id": "gen3a_turbo",
            "display_order": 50,
            "enabled": False,
            "deprecated_at": datetime(2026, 7, 30, tzinfo=UTC),
            "replacement_slug": "runway-gemini-omni-video-fast",
            "feature_flag": "runway_media",
            # Was 25 credits ($0.10) against $0.25 recorded cost. Disabled and
            # deprecated, but corrected so it cannot be re-enabled at a loss.
            "user_credit_price": 63,
            "provider_cost_units": 2500,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["16:9", "9:16"],
                "durations_sec": [5, 10],
                "max_prompt_chars": 1500,
                "supports_seed": False,
                "max_outputs": 1,
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "Runway Gen-3 Video",
                    "description": "Видео через Runway",
                },
                "kk": {
                    "name": "Runway Gen-3 Video",
                    "description": "Runway арқылы бейне",
                },
            },
            "pricing_rules": {
                "duration_multipliers": {
                    "5": {"num": 1, "den": 1},
                    "10": {"num": 2, "den": 1},
                }
            },
        },
        {
            "id": RUNWAY_FAST_VIDEO_ID,
            "slug": "runway-gemini-omni-video-fast",
            "modality": "video",
            "provider": "runway",
            "provider_model_id": "gemini_omni_flash",
            "display_order": 51,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            "user_credit_price": 100,
            "provider_cost_units": 4000,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["16:9", "9:16"],
                "resolutions": ["720p"],
                "durations_sec": [4, 8],
                "max_prompt_chars": 1000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "video",
                    "studio_tier": "fast",
                    "smart_candidate": True,
                    "simple_default": True,
                    "hidden_in_production": False,
                    "eta_seconds": 180,
                    "provider_cost_ceiling_units_per_second": 1000,
                },
                "fallback": {
                    "provider": "google",
                    "provider_model_id": "veo-3.1-lite-generate-preview",
                    "provider_cost_units_per_second": 500,
                    "max_attempts": 1,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Video Fast",
                    "description": "Быстрый ролик с движением и звуком",
                },
                "kk": {
                    "name": "KELBET Video Fast",
                    "description": "Қозғалыс пен дыбысы бар жылдам бейне",
                },
            },
            "pricing_rules": {
                "duration_multipliers": {
                    "4": {"num": 1, "den": 1},
                    "8": {"num": 2, "den": 1},
                }
            },
        },
        {
            "id": RUNWAY_QUALITY_VIDEO_ID,
            "slug": "runway-gen45-video-quality",
            "modality": "video",
            "provider": "runway",
            "provider_model_id": "gen4.5",
            "display_order": 52,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "runway_media",
            "user_credit_price": 120,
            "provider_cost_units": 4800,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["16:9", "9:16"],
                "resolutions": ["720p"],
                "durations_sec": [4, 8],
                "max_prompt_chars": 1000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "video",
                    "studio_tier": "quality",
                    "smart_candidate": True,
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 240,
                    "provider_cost_ceiling_units_per_second": 1200,
                },
                "fallback": {
                    "provider": "google",
                    "provider_model_id": "veo-3.1-lite-generate-preview",
                    "provider_cost_units_per_second": 500,
                    "max_attempts": 1,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "KELBET Video Quality",
                    "description": "Более точная пластика камеры и сцены",
                },
                "kk": {
                    "name": "KELBET Video Quality",
                    "description": "Камера мен көріністің дәлірек қозғалысы",
                },
            },
            "pricing_rules": {
                "duration_multipliers": {
                    "4": {"num": 1, "den": 1},
                    "8": {"num": 2, "den": 1},
                }
            },
        },
        {
            "id": GOOGLE_FALLBACK_VIDEO_ID,
            "slug": "google-veo31-lite-video-fallback",
            "modality": "video",
            "provider": "google",
            "provider_model_id": "veo-3.1-lite-generate-preview",
            "display_order": 53,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "google_video",
            "user_credit_price": 50,
            "provider_cost_units": 2000,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["16:9", "9:16"],
                "resolutions": ["720p"],
                "durations_sec": [4, 6, 8],
                "max_prompt_chars": 1000,
                "supports_seed": False,
                "max_outputs": 1,
                "ui": {
                    "operation": "video",
                    "studio_tier": "alternative",
                    "smart_candidate": False,
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 360,
                    "provider_cost_ceiling_units_per_second": 500,
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "Google Veo 3.1 Lite",
                    "description": "Спокойные короткие сцены через Google Veo",
                },
                "kk": {
                    "name": "Google Veo 3.1 Lite",
                    "description": "Google Veo арқылы қысқа әрі тыныш көріністер",
                },
            },
            "pricing_rules": {
                "duration_multipliers": {
                    "4": {"num": 1, "den": 1},
                    "6": {"num": 3, "den": 2},
                    "8": {"num": 2, "den": 1},
                }
            },
        },
        {
            "id": GOOGLE_EXTENDED_VIDEO_ID,
            "slug": "google-veo31-fast-extended-video",
            "modality": "video",
            "provider": "google",
            "provider_model_id": "veo-3.1-fast-generate-preview",
            "display_order": 54,
            "enabled": True,
            "deprecated_at": None,
            "replacement_slug": None,
            "feature_flag": "veo_extended",
            # Was 100 credits ($0.40) against $0.80 recorded cost for the 8s base.
            "user_credit_price": 200,
            "provider_cost_units": 8000,
            "currency_hint": "USD",
            "capabilities": {
                "aspect_ratios": ["16:9", "9:16"],
                "resolutions": ["720p"],
                "durations_sec": [8, 15, 22, 29],
                "max_prompt_chars": 1000,
                "supports_seed": False,
                "max_outputs": 1,
                "workflow": {
                    "type": "veo_extend",
                    "initial_duration_sec": 8,
                    "extension_duration_sec": 7,
                    "cumulative_durations_sec": [8, 15, 22, 29],
                    "final_output_only": True,
                    "fallback": False,
                },
                "ui": {
                    "operation": "video",
                    "studio_tier": "premium",
                    "smart_candidate": False,
                    "simple_default": False,
                    "hidden_in_production": False,
                    "eta_seconds": 960,
                    "badge": "LONG",
                },
            },
            "input_requirements": {
                "prompt": "required",
                "source_image": "optional",
                "accepted_mime": ["image/jpeg", "image/png", "image/webp"],
                "max_input_bytes": 10485760,
                "max_input_assets": 1,
            },
            "localization": {
                "ru": {
                    "name": "Veo 3.1 Fast Extended",
                    "description": (
                        "Непрерывная сцена до ≈30 секунд с последовательным продолжением"
                    ),
                },
                "kk": {
                    "name": "Veo 3.1 Fast Extended",
                    "description": "Кезең-кезеңімен жалғасатын ≈30 секундқа дейінгі тұтас көрініс",
                },
            },
            # Each extend call bills only its own 7 new seconds, so cost is linear in
            # total output seconds. `enforce_economics` rewrites these to duration/8:
            # 8s -> 200, 15s -> 375, 22s -> 550, 29s -> 725 credits. The previous
            # 1x/2x/3x/4x steps charged 2000 credits for 29s, nearly 3x over cost.
            "pricing_rules": {
                "duration_multipliers": {
                    "8": {"num": 8, "den": 8},
                    "15": {"num": 15, "den": 8},
                    "22": {"num": 22, "den": 8},
                    "29": {"num": 29, "den": 8},
                }
            },
        },
        {
            "id": LEGACY_DISABLED_ID,
            "slug": "legacy-disabled",
            "modality": "image",
            "provider": "mock",
            "provider_model_id": "legacy",
            "display_order": 999,
            "enabled": False,
            "deprecated_at": datetime(2026, 1, 1, tzinfo=UTC),
            "replacement_slug": "mock-image",
            "feature_flag": None,
            "user_credit_price": 3,
            "provider_cost_units": 0,
            "currency_hint": None,
            "capabilities": {"aspect_ratios": ["1:1"], "resolutions": ["720p"]},
            "input_requirements": {"prompt": "required"},
            "localization": {
                "ru": {"name": "Устаревшая", "description": "Отключена"},
                "kk": {"name": "Ескірген", "description": "Өшірілген"},
            },
            "pricing_rules": None,
        },
    ]
    # OpenAI GPT Image 2 is an independent primary route. It is disabled until
    # an allowlisted canary has reconciled actual image-token cost and quality.
    rows.extend(
        [
            {
                "id": OPENAI_IMAGE_FAST_ID,
                "slug": "openai-gpt-image-2-fast",
                "modality": "image",
                "provider": "openai",
                "provider_model_id": "gpt-image-2",
                "display_order": 44,
                "enabled": True,
                "deprecated_at": None,
                "replacement_slug": None,
                "feature_flag": "openai_image",
                # Was 8 credits ($0.032) against $0.06 recorded cost.
                "user_credit_price": 15,
                "provider_cost_units": 600,
                "currency_hint": "USD",
                "capabilities": {
                    "aspect_ratios": ["1:1", "16:9", "9:16"],
                    "resolutions": ["1k"],
                    "flavors": ["low"],
                    "max_prompt_chars": 4000,
                    "supports_seed": False,
                    "max_outputs": 1,
                    "ui": {
                        "operation": "create",
                        "studio_tier": "fast",
                        "smart_candidate": True,
                        "simple_default": False,
                        "hidden_in_production": False,
                        "eta_seconds": 75,
                    },
                },
                "input_requirements": {
                    "prompt": "required",
                    "source_image": "forbidden",
                    "accepted_mime": [],
                    "max_input_bytes": 0,
                    "max_input_assets": 0,
                },
                "localization": {
                    "ru": {
                        "name": "GPT Image Fast",
                        "description": "Быстрые черновики через GPT Image 2",
                    },
                    "kk": {
                        "name": "GPT Image Fast",
                        "description": "GPT Image 2 арқылы жылдам нобайлар",
                    },
                },
                "pricing_rules": None,
            },
            {
                "id": OPENAI_IMAGE_QUALITY_ID,
                "slug": "openai-gpt-image-2-quality",
                "modality": "image",
                "provider": "openai",
                "provider_model_id": "gpt-image-2",
                "display_order": 45,
                "enabled": True,
                "deprecated_at": None,
                "replacement_slug": None,
                "feature_flag": "openai_image",
                # Was 16 credits ($0.064) against $0.53 recorded cost — 8x below
                # cost. The recorded cost is a conservative placeholder pending the
                # canary reconciliation, so this price will drop once it is measured.
                "user_credit_price": 133,
                "provider_cost_units": 5300,
                "currency_hint": "USD",
                "capabilities": {
                    "aspect_ratios": ["1:1", "16:9", "9:16"],
                    "resolutions": ["1k"],
                    "flavors": ["medium"],
                    "max_prompt_chars": 4000,
                    "supports_seed": False,
                    "max_outputs": 1,
                    "ui": {
                        "operation": "create",
                        "studio_tier": "quality",
                        "smart_candidate": True,
                        "simple_default": False,
                        "hidden_in_production": False,
                        "eta_seconds": 110,
                    },
                },
                "input_requirements": {
                    "prompt": "required",
                    "source_image": "forbidden",
                    "accepted_mime": [],
                    "max_input_bytes": 0,
                    "max_input_assets": 0,
                },
                "localization": {
                    "ru": {
                        "name": "GPT Image Quality",
                        "description": "Точные изображения через GPT Image 2",
                    },
                    "kk": {
                        "name": "GPT Image Quality",
                        "description": "GPT Image 2 арқылы дәл кескіндер",
                    },
                },
                "pricing_rules": None,
            },
        ]
    )

    # Gemini native image generation/editing is an independent, opt-in fallback.
    # Google does not document deterministic upscale semantics, so the upscale SKU
    # intentionally receives no fallback route.
    image_fallback_slugs = {
        "runway-seedream5-lite-image",
        "runway-seedream5-pro-image",
        "runway-seedream5-lite-edit",
        "runway-seedream5-pro-edit",
        "runway-gen4-image",
    }
    fallback = {
        "provider": "google",
        "provider_model_id": "gemini-3.1-flash-image",
        "supported_modalities": ["image", "image_edit"],
        "provider_feature_flag": "google_image",
        "feature_flag": "image_fallback",
        "provider_cost_units_by_resolution": {
            "512": 450,
            "0.5k": 450,
            "720p": 670,
            "1080p": 670,
            "1k": 670,
            "2k": 1010,
            "3k": 1010,
            "4k": 1510,
        },
        "max_attempts": 1,
    }
    for row in rows:
        if row["slug"] not in image_fallback_slugs:
            continue
        capabilities = row["capabilities"]
        assert isinstance(capabilities, dict)
        capabilities["fallback"] = dict(fallback)
        ui = capabilities.get("ui")
        assert isinstance(ui, dict)
        ui["provider_cost_ceiling_units"] = 1100
    return enforce_economics(rows)
