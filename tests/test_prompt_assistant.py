from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.chat import ChatCompletionResult, ChatMessage
from kelbet.chat.mock import MockChatProvider
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.domain.exceptions import (
    ChatMessageTooLongError,
    ChatProviderError,
    IdempotencyConflictError,
    InsufficientCreditsError,
)
from kelbet.repositories.user import UserRepository
from kelbet.services.prompt_assistant import PromptAssistantService
from kelbet.services.registration import RegistrationService


class RecordingProvider(MockChatProvider):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(fail=fail, reply_prefix="POLISHED")
        self.calls: list[list[ChatMessage]] = []

    async def complete(
        self,
        *,
        messages: list[ChatMessage],
        request_id: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatCompletionResult:
        self.calls.append(messages)
        return await super().complete(
            messages=messages,
            request_id=request_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )


async def _user_id(
    session: AsyncSession,
    *,
    telegram_id: int,
    language: Language,
    settings: Settings,
) -> UUID:
    await RegistrationService(session, settings=settings).register_with_language(
        telegram_id=telegram_id,
        username="prompt_user",
        language=language,
    )
    user = await UserRepository(session).get_by_telegram_id(telegram_id)
    assert user is not None
    return user.id


@pytest.mark.asyncio
async def test_prompt_assistant_charges_only_after_success_and_replays(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        welcome_credits=5,
        prompt_assistant_credit_cost=1,
        prompt_assistant_max_input_chars=1200,
    )
    provider = RecordingProvider()
    request_id = str(uuid4())

    async with session_factory() as session, session.begin():
        user_id = await _user_id(
            session,
            telegram_id=8101,
            language=Language.RU,
            settings=settings,
        )
        service = PromptAssistantService(session, provider, settings)
        first = await service.improve(
            user_id=user_id,
            brief="Тёплая предметная фотография казахского чая",
            request_id=request_id,
            intent="product",
        )
        replay = await service.improve(
            user_id=user_id,
            brief="Тёплая предметная фотография казахского чая",
            request_id=request_id,
            intent="product",
        )

        assert first.charged is True
        assert first.balance == 4
        assert replay.charged is False
        assert replay.balance == 4
        assert replay.improved_prompt == first.improved_prompt
        assert len(provider.calls) == 1
        assert "untrusted data" in provider.calls[0][0].content
        assert "<user_brief>" in provider.calls[0][1].content


@pytest.mark.asyncio
async def test_prompt_assistant_uses_kazakh_output_instruction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    provider = RecordingProvider()
    async with session_factory() as session, session.begin():
        user_id = await _user_id(
            session,
            telegram_id=8102,
            language=Language.KK,
            settings=settings,
        )
        result = await PromptAssistantService(session, provider, settings).improve(
            user_id=user_id,
            brief="Алматыдағы кешкі көше",
            request_id="kk-output",
            intent="social",
        )
        assert result.language is Language.KK
        assert "in Kazakh" in provider.calls[0][0].content


@pytest.mark.asyncio
async def test_prompt_assistant_rejects_idempotency_key_reuse(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    provider = RecordingProvider()
    async with session_factory() as session, session.begin():
        user_id = await _user_id(
            session,
            telegram_id=8103,
            language=Language.RU,
            settings=settings,
        )
        service = PromptAssistantService(session, provider, settings)
        await service.improve(
            user_id=user_id,
            brief="Первый сюжет",
            request_id="same-key",
        )
        with pytest.raises(IdempotencyConflictError):
            await service.improve(
                user_id=user_id,
                brief="Другой сюжет",
                request_id="same-key",
            )


@pytest.mark.asyncio
async def test_prompt_assistant_validates_balance_and_length_before_provider(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        welcome_credits=1,
        prompt_assistant_credit_cost=2,
        prompt_assistant_max_input_chars=10,
    )
    provider = RecordingProvider()
    async with session_factory() as session, session.begin():
        user_id = await _user_id(
            session,
            telegram_id=8104,
            language=Language.RU,
            settings=settings,
        )
        service = PromptAssistantService(session, provider, settings)
        with pytest.raises(ChatMessageTooLongError):
            await service.improve(
                user_id=user_id,
                brief="Слишком длинный пользовательский запрос",
                request_id="too-long",
            )
        with pytest.raises(InsufficientCreditsError):
            await service.improve(
                user_id=user_id,
                brief="Коротко",
                request_id="no-money",
            )
        assert provider.calls == []


@pytest.mark.asyncio
async def test_prompt_assistant_provider_failure_does_not_debit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    provider = RecordingProvider(fail=True)
    async with session_factory() as session, session.begin():
        user_id = await _user_id(
            session,
            telegram_id=8105,
            language=Language.RU,
            settings=settings,
        )

    with pytest.raises(ChatProviderError):
        async with session_factory() as session, session.begin():
            await PromptAssistantService(session, provider, settings).improve(
                user_id=user_id,
                brief="Сцена без списания",
                request_id="provider-failure",
            )

    async with session_factory() as session, session.begin():
        profile = await RegistrationService(session, settings=settings).handle_start(
            8105,
            "prompt_user",
        )
        assert profile.user is not None
        assert profile.user.balance == 5
