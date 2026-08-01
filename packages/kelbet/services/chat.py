from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.chat import ChatMessage, ChatProvider
from kelbet.chat.mock import build_system_message
from kelbet.config import Settings, get_settings
from kelbet.domain.enums import Language, TxReason
from kelbet.domain.exceptions import (
    ChatMessageTooLongError,
    ChatProviderError,
    InsufficientCreditsError,
    UserBlockedError,
    UserNotFoundError,
    WalletNotFoundError,
)
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.moderation import ModerationService
from kelbet.services.wallet import CreditResult, WalletService

logger = logging.getLogger(__name__)


def chat_idempotency_key(request_id: str) -> str:
    return f"chat:{request_id}"


@dataclass(frozen=True, slots=True)
class ChatAskResult:
    answer: str
    balance: int
    language: Language
    debit_applied: bool
    provider: str
    model: str
    latency_ms: int


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        provider: ChatProvider,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings or get_settings()
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet_service = WalletService(session)

    async def ask(
        self,
        *,
        telegram_id: int,
        message: str,
        request_id: str,
    ) -> ChatAskResult:
        text = message.strip()
        if not text:
            msg = "Empty chat message"
            raise ValueError(msg)

        max_chars = self._settings.chat_max_input_chars
        if len(text) > max_chars:
            raise ChatMessageTooLongError(f"Message length {len(text)} exceeds limit {max_chars}")

        user = await self._users.get_by_telegram_id_for_update(telegram_id)
        if user is None:
            raise UserNotFoundError(f"User telegram_id={telegram_id} not found")
        if user.is_blocked:
            raise UserBlockedError(f"User {user.id} is blocked")

        await ModerationService(self._session, self._settings).evaluate_text(
            user_id=user.id,
            text=text,
            context="chat",
            idempotency_key=request_id,
            language=user.language,
        )

        language = Language(user.language)
        wallet = await self._wallets.get_by_user_id(user.id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {user.id} not found")

        cost = self._settings.chat_credit_cost
        available = wallet.balance - wallet.reserved
        if available < cost:
            raise InsufficientCreditsError(f"Need {cost}, have {available}")

        messages = [
            build_system_message(),
            ChatMessage(role="user", content=text),
        ]

        try:
            completion = await self._provider.complete(
                messages=messages,
                request_id=request_id,
            )
        except ChatProviderError:
            logger.warning(
                "chat_ask_failed provider=%s model=%s status=provider_error",
                self._provider.name,
                self._provider.model,
            )
            raise

        debit: CreditResult = await self._wallet_service.debit(
            wallet.id,
            cost,
            TxReason.AI_CHAT,
            chat_idempotency_key(request_id),
            meta={
                "source": "ai_chat",
                "provider": completion.provider,
                "model": completion.model,
                "request_id": request_id,
            },
        )

        logger.info(
            "chat_ask_ok provider=%s model=%s latency_ms=%s status=ok debit_applied=%s",
            completion.provider,
            completion.model,
            completion.latency_ms,
            debit.applied,
        )

        return ChatAskResult(
            answer=completion.content,
            balance=debit.balance,
            language=language,
            debit_applied=debit.applied,
            provider=completion.provider,
            model=completion.model,
            latency_ms=completion.latency_ms,
        )
