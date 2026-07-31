"""ChatService bilingual AI chat tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.bot.handlers.chat import on_chat_cancel
from apps.bot.states import ChatStates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.chat.mock import MockChatProvider
from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.domain.exceptions import (
    ChatMessageTooLongError,
    ChatProviderError,
    InsufficientCreditsError,
)
from kelbet.i18n import Msg, t, texts_for
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.chat import ChatService, chat_idempotency_key
from kelbet.services.registration import RegistrationService


async def _register_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    language: Language,
    settings: Settings,
) -> None:
    service = RegistrationService(session, settings=settings)
    await service.register_with_language(
        telegram_id=telegram_id,
        username="chat_user",
        language=language,
    )


@pytest.mark.asyncio
async def test_successful_chat_debits_one_credit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1, chat_max_input_chars=2000)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5001, language=Language.RU, settings=settings)
        service = ChatService(session, provider, settings=settings)
        result = await service.ask(
            telegram_id=5001,
            message="Привет, как дела?",
            request_id="req-success-1",
        )
        assert result.debit_applied is True
        assert result.balance == 4
        assert "Привет, как дела?" in result.answer
        assert result.provider == "mock"

        wallets = WalletRepository(session)
        user_service = RegistrationService(session, settings=settings)
        start = await user_service.handle_start(5001, "chat_user")
        assert start.user is not None
        wallet = await wallets.get_by_user_id(start.user.id)
        assert wallet is not None
        assert wallet.balance == 4
        assert await wallets.count_transactions(wallet.id) == 2  # welcome + chat
        tx = await wallets.get_transaction_by_idempotency_key(chat_idempotency_key("req-success-1"))
        assert tx is not None
        assert tx.amount == -1
        assert tx.reason == "ai_chat"


@pytest.mark.asyncio
async def test_provider_error_does_not_debit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1)
    provider = MockChatProvider(fail=True)

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5002, language=Language.RU, settings=settings)
        service = ChatService(session, provider, settings=settings)
        with pytest.raises(ChatProviderError):
            await service.ask(
                telegram_id=5002,
                message="Вопрос",
                request_id="req-fail-1",
            )

        user_service = RegistrationService(session, settings=settings)
        start = await user_service.handle_start(5002, "chat_user")
        assert start.user is not None
        assert start.user.balance == 5
        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(start.user.id)
        assert wallet is not None
        assert await wallets.count_transactions(wallet.id) == 1


@pytest.mark.asyncio
async def test_insufficient_balance(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=1, chat_credit_cost=1)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5003, language=Language.KK, settings=settings)
        service = ChatService(session, provider, settings=settings)
        first = await service.ask(
            telegram_id=5003,
            message="Сәлем",
            request_id="req-spend-last",
        )
        assert first.balance == 0
        with pytest.raises(InsufficientCreditsError):
            await service.ask(
                telegram_id=5003,
                message="Тағы",
                request_id="req-no-balance",
            )


@pytest.mark.asyncio
async def test_same_request_id_does_not_debit_twice(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5004, language=Language.RU, settings=settings)
        service = ChatService(session, provider, settings=settings)
        first = await service.ask(
            telegram_id=5004,
            message="Первый",
            request_id="req-idempotent",
        )
        second = await service.ask(
            telegram_id=5004,
            message="Первый",
            request_id="req-idempotent",
        )
        assert first.debit_applied is True
        assert first.balance == 4
        assert second.debit_applied is False
        assert second.balance == 4

        user_service = RegistrationService(session, settings=settings)
        start = await user_service.handle_start(5004, "chat_user")
        assert start.user is not None
        wallets = WalletRepository(session)
        wallet = await wallets.get_by_user_id(start.user.id)
        assert wallet is not None
        assert wallet.balance == 4
        assert await wallets.count_transactions(wallet.id) == 2


@pytest.mark.asyncio
async def test_russian_request(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5005, language=Language.RU, settings=settings)
        service = ChatService(session, provider, settings=settings)
        result = await service.ask(
            telegram_id=5005,
            message="Расскажи кратко о Алматы",
            request_id="req-ru",
        )
        assert result.language == Language.RU
        assert "Алматы" in result.answer


@pytest.mark.asyncio
async def test_kazakh_request(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5006, language=Language.KK, settings=settings)
        service = ChatService(session, provider, settings=settings)
        result = await service.ask(
            telegram_id=5006,
            message="Алматы туралы қысқаша айтшы",
            request_id="req-kk",
        )
        assert result.language == Language.KK
        assert "қысқаша" in result.answer
        assert any(ch in t(Msg.CHAT_PROMPT, Language.KK) for ch in "әғқңөұүһі")


@pytest.mark.asyncio
async def test_message_too_long(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5, chat_credit_cost=1, chat_max_input_chars=10)
    provider = MockChatProvider()

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5007, language=Language.RU, settings=settings)
        service = ChatService(session, provider, settings=settings)
        with pytest.raises(ChatMessageTooLongError):
            await service.ask(
                telegram_id=5007,
                message="это сообщение длиннее лимита",
                request_id="req-long",
            )
        user_service = RegistrationService(session, settings=settings)
        start = await user_service.handle_start(5007, "chat_user")
        assert start.user is not None
        assert start.user.balance == 5


@pytest.mark.asyncio
async def test_fsm_cancel_clears_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(welcome_credits=5)
    assert "❌ Отмена" in texts_for(Msg.CHAT_CANCEL)
    assert "❌ Болдырмау" in texts_for(Msg.CHAT_CANCEL)

    async with session_factory() as session, session.begin():
        await _register_user(session, telegram_id=5008, language=Language.RU, settings=settings)

        state = AsyncMock()
        message = MagicMock()
        message.from_user = MagicMock(id=5008, username="chat_user")
        message.answer = AsyncMock()

        await on_chat_cancel(message, session, state, settings)

        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
        args, kwargs = message.answer.await_args
        assert args[0] == t(Msg.CHAT_CANCELLED, Language.RU)
        assert ChatStates.waiting_message.state is not None
