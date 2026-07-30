from __future__ import annotations

from kelbet.chat import ChatProvider
from kelbet.chat.mock import MockChatProvider
from kelbet.chat.openrouter import OpenRouterChatProvider
from kelbet.config import Settings


def build_chat_provider(settings: Settings) -> ChatProvider:
    provider = settings.chat_provider.strip().lower()
    if provider in {"", "mock"}:
        return MockChatProvider(model=settings.openrouter_model or "mock-model")
    if provider == "openrouter":
        return OpenRouterChatProvider.from_settings(settings)
    msg = f"Unsupported CHAT_PROVIDER: {settings.chat_provider}"
    raise ValueError(msg)
