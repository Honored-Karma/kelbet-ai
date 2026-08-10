from __future__ import annotations

from uuid import uuid4

import pytest

from kelbet.config import Settings
from kelbet.providers.base import GenerationRequest
from kelbet.providers.factory import (
    UnsupportedGenerationProvider,
    resolve_provider,
)
from kelbet.providers.mock import MockImageProvider, MockTextProvider


@pytest.mark.parametrize(
    ("modality", "expected_type"),
    [("text", MockTextProvider), ("image", MockImageProvider)],
)
def test_factory_uses_mock_only_when_it_is_explicitly_configured(
    modality: str,
    expected_type: type[MockTextProvider] | type[MockImageProvider],
) -> None:
    provider = resolve_provider("mock", modality=modality, settings=Settings())
    assert isinstance(provider, expected_type)


@pytest.mark.asyncio
@pytest.mark.parametrize("modality", ["text", "image", "video"])
async def test_factory_fails_closed_for_unknown_provider(modality: str) -> None:
    provider = resolve_provider("typo-provider", modality=modality, settings=Settings())

    assert isinstance(provider, UnsupportedGenerationProvider)
    result = await provider.generate(
        GenerationRequest(
            generation_id=uuid4(),
            provider_model_id="unknown-model",
            modality=modality,
            prompt="Safe prompt",
        )
    )

    assert provider.name == "unsupported"
    assert result.status == "failed"
    assert result.error_code == "provider_unsupported"
    assert result.outputs == []
    assert result.provider_job_id is None


@pytest.mark.asyncio
async def test_unsupported_provider_polling_and_cancellation_are_safe() -> None:
    provider = UnsupportedGenerationProvider()

    status = await provider.get_status("provider-job-id")
    await provider.cancel("provider-job-id")

    assert status.status == "failed"
    assert status.error_code == "provider_unsupported"
