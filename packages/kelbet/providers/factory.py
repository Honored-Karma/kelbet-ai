"""Resolve generation providers by catalog provider name + modality."""

from __future__ import annotations

from kelbet.config import Settings, get_settings
from kelbet.providers.base import GenerationProvider
from kelbet.providers.google_image import GoogleGeminiImageProvider
from kelbet.providers.google_veo import GoogleVeoProvider
from kelbet.providers.mock import MockImageProvider, MockTextProvider
from kelbet.providers.openai_image import OpenAIImageProvider
from kelbet.providers.openrouter import OpenRouterTextProvider
from kelbet.providers.runway import RunwayProvider


def resolve_provider(
    provider_name: str,
    *,
    modality: str,
    settings: Settings | None = None,
) -> GenerationProvider:
    name = provider_name.strip().lower()
    mod = modality.strip().lower()
    cfg = settings or get_settings()

    if name == "openrouter":
        return OpenRouterTextProvider.from_settings(cfg)

    if name == "runway":
        return RunwayProvider.from_settings(cfg)

    if name == "google":
        if mod in {"image", "image_edit", "upscale"}:
            return GoogleGeminiImageProvider.from_settings(cfg)
        return GoogleVeoProvider.from_settings(cfg)

    if name == "openai":
        return OpenAIImageProvider.from_settings(cfg)

    if name == "mock":
        if mod == "text":
            return MockTextProvider()
        return MockImageProvider()

    if mod == "text":
        return MockTextProvider()
    return MockImageProvider()
