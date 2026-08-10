"""Resolve generation providers by catalog provider name + modality."""

from __future__ import annotations

from kelbet.config import Settings, get_settings
from kelbet.providers.base import (
    GenerationProvider,
    GenerationProviderResult,
    GenerationRequest,
)
from kelbet.providers.google_image import GoogleGeminiImageProvider
from kelbet.providers.google_veo import GoogleVeoProvider
from kelbet.providers.mock import MockImageProvider, MockTextProvider
from kelbet.providers.openai_image import OpenAIImageProvider
from kelbet.providers.openrouter import OpenRouterTextProvider
from kelbet.providers.runway import RunwayProvider


class UnsupportedGenerationProvider:
    """Fail closed when a catalog references an unknown provider adapter."""

    @property
    def name(self) -> str:
        return "unsupported"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        del request
        return self._failure()

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        del provider_job_id
        return self._failure()

    async def cancel(self, provider_job_id: str) -> None:
        del provider_job_id

    @staticmethod
    def _failure() -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code="provider_unsupported",
            error_message_safe="The configured generation provider is unsupported",
        )


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

    return UnsupportedGenerationProvider()
