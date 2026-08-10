from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.services.telegram_update_inbox import TelegramUpdateInboxService


def extract_critical_update(update: Update) -> tuple[str, dict[str, Any]] | None:
    """Return only fields required to replay a money-moving update."""

    message = update.message
    if message is not None and message.successful_payment is not None and message.from_user:
        payment = message.successful_payment
        return (
            "successful_payment",
            {
                "telegram_id": message.from_user.id,
                "chat_id": message.chat.id,
                "message_id": message.message_id,
                "message_date": int(message.date.timestamp()),
                "invoice_payload": payment.invoice_payload,
                "currency": payment.currency,
                "total_amount": payment.total_amount,
                "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                "provider_payment_charge_id": payment.provider_payment_charge_id,
                "subscription_expiration_date": payment.subscription_expiration_date,
            },
        )
    subscription = update.subscription
    if subscription is not None:
        return (
            "subscription_state",
            {
                "telegram_id": subscription.user.id,
                "invoice_payload": subscription.invoice_payload,
                "state": subscription.state,
            },
        )
    return None


class TelegramUpdateInboxMiddleware(BaseMiddleware):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update) or data.get("durable_replay"):
            return await handler(event, data)
        extracted = extract_critical_update(event)
        if extracted is None:
            return await handler(event, data)
        event_type, payload = extracted
        async with self._session_factory() as session, session.begin():
            should_process = await TelegramUpdateInboxService(session).claim_delivery(
                update_id=event.update_id,
                event_type=event_type,
                payload=payload,
                stale_after_seconds=self._settings.telegram_update_inbox_stale_seconds,
                max_attempts=self._settings.telegram_update_inbox_max_attempts,
            )
        if not should_process:
            return None
        try:
            result = await handler(event, data)
        except Exception:
            async with self._session_factory() as session, session.begin():
                await TelegramUpdateInboxService(session).mark_failed(event.update_id)
            raise
        async with self._session_factory() as session, session.begin():
            await TelegramUpdateInboxService(session).mark_processed(event.update_id)
        return result
