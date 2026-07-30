from __future__ import annotations

import time

from kelbet.chat import SYSTEM_PROMPT, ChatCompletionResult, ChatMessage
from kelbet.domain.exceptions import ChatProviderError


class MockChatProvider:
    """Deterministic provider for tests and local development."""

    def __init__(
        self,
        *,
        model: str = "mock-model",
        fail: bool = False,
        reply_prefix: str = "MOCK",
    ) -> None:
        self._model = model
        self._fail = fail
        self._reply_prefix = reply_prefix

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return self._model

    def set_fail(self, fail: bool) -> None:
        self._fail = fail

    async def complete(
        self,
        *,
        messages: list[ChatMessage],
        request_id: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletionResult:
        started = time.perf_counter()
        if self._fail:
            raise ChatProviderError("Mock provider forced failure")

        user_text = ""
        for message in reversed(messages):
            if message.role == "user":
                user_text = message.content
                break

        content = f"{self._reply_prefix}: {user_text}"
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ChatCompletionResult(
            content=content,
            provider=self.name,
            model=self._model,
            latency_ms=latency_ms,
            status="ok",
        )


def build_system_message() -> ChatMessage:
    return ChatMessage(role="system", content=SYSTEM_PROMPT)
