"""Generation provider port."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    generation_id: UUID
    provider_model_id: str
    modality: str
    prompt: str
    params: dict[str, Any] = field(default_factory=dict)
    input_object_keys: list[str] = field(default_factory=list)
    input_urls: list[str] = field(default_factory=list)
    # Complete MP4 returned by a previous Veo operation. Providers must treat
    # this as mutually exclusive with image inputs.
    extension_video: GenerationOutput | None = None


@dataclass(frozen=True, slots=True)
class GenerationOutput:
    content_type: str
    data: bytes
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationProviderResult:
    status: str  # succeeded | failed | accepted (async)
    outputs: list[GenerationOutput] = field(default_factory=list)
    provider_job_id: str | None = None
    error_code: str | None = None
    error_message_safe: str | None = None
    latency_ms: int = 0
    provider_cost_units: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class GenerationProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult: ...

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult: ...

    async def cancel(self, provider_job_id: str) -> None: ...
