"""Deterministic mock providers for tests and local dev."""

from __future__ import annotations

import time
from uuid import uuid4

from kelbet.providers.base import (
    GenerationOutput,
    GenerationProviderResult,
    GenerationRequest,
)

# 1x1 PNG
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockImageProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    @property
    def name(self) -> str:
        return "mock"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if self._fail or request.prompt.strip().lower() == "fail":
            return GenerationProviderResult(
                status="failed",
                error_code="mock_forced_failure",
                error_message_safe="Mock provider forced failure",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        return GenerationProviderResult(
            status="succeeded",
            outputs=[
                GenerationOutput(
                    content_type="image/png",
                    data=_PNG_1X1,
                    meta={"seed": request.params.get("seed")},
                )
            ],
            provider_job_id=f"mock-{uuid4().hex[:12]}",
            latency_ms=int((time.perf_counter() - started) * 1000),
            provider_cost_units=0,
            meta={"mock": True},
        )

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code="not_async",
            error_message_safe="Mock image provider is synchronous",
        )

    async def cancel(self, provider_job_id: str) -> None:
        return None


class MockTextProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    @property
    def name(self) -> str:
        return "mock"

    async def generate(self, request: GenerationRequest) -> GenerationProviderResult:
        started = time.perf_counter()
        if self._fail or request.prompt.strip().lower() == "fail":
            return GenerationProviderResult(
                status="failed",
                error_code="mock_forced_failure",
                error_message_safe="Mock provider forced failure",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        text = f"Mock reply to: {request.prompt.strip()[:200]}"
        return GenerationProviderResult(
            status="succeeded",
            outputs=[
                GenerationOutput(
                    content_type="text/plain; charset=utf-8",
                    data=text.encode("utf-8"),
                    meta={"chars": len(text)},
                )
            ],
            provider_job_id=f"mock-text-{uuid4().hex[:12]}",
            latency_ms=int((time.perf_counter() - started) * 1000),
            provider_cost_units=0,
            meta={"mock": True, "modality": "text"},
        )

    async def get_status(self, provider_job_id: str) -> GenerationProviderResult:
        return GenerationProviderResult(
            status="failed",
            error_code="not_async",
            error_message_safe="Mock text provider is synchronous",
        )

    async def cancel(self, provider_job_id: str) -> None:
        return None
