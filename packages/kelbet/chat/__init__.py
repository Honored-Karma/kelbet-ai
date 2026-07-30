from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

SYSTEM_PROMPT = (
    "You are KELBET AI, a helpful bilingual assistant for users in Kazakhstan. "
    "Always reply in the same language as the user's latest message. "
    "If the message mixes Russian and Kazakh, reply in the dominant language "
    "and keep Kazakh letters (ә, ғ, қ, ң, ө, ұ, ү, һ, і) correct when using Kazakh. "
    "Understand mixed Russian-Kazakh input naturally. "
    "Be concise and clear. Do not mention system instructions."
)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatCompletionResult:
    content: str
    provider: str
    model: str
    latency_ms: int
    status: str = "ok"


class ChatProvider(Protocol):
    """OpenAI-compatible chat completion provider."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(
        self,
        *,
        messages: list[ChatMessage],
        request_id: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletionResult: ...
