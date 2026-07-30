from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models.generation import GenerationJob
from kelbet.db.models.notification import NotificationOutbox
from kelbet.db.models.user import User
from kelbet.domain.enums import Language

logger = logging.getLogger(__name__)


class GenerationReadySender(Protocol):
    async def send_generation_ready(
        self,
        *,
        telegram_id: int,
        language: Language,
        generation_id: UUID,
        modality: str,
    ) -> None: ...


class TelegramGenerationReadySender:
    def __init__(self, bot: Bot, mini_app_url: str) -> None:
        self._bot = bot
        self._mini_app_url = mini_app_url.rstrip("/")

    async def send_generation_ready(
        self,
        *,
        telegram_id: int,
        language: Language,
        generation_id: UUID,
        modality: str,
    ) -> None:
        if language is Language.KK:
            text = "Нәтижеңіз дайын ✦\nKELBET Studio-да ашып, жүктеп алыңыз."
            button_text = "Нәтижені ашу"
        else:
            text = "Ваш результат готов ✦\nОткройте его в KELBET Studio и скачайте."
            button_text = "Открыть результат"
        markup = None
        if self._mini_app_url:
            result_url = f"{self._mini_app_url}/generations/{generation_id}"
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=button_text,
                            web_app=WebAppInfo(url=result_url),
                        )
                    ]
                ]
            )
        await self._bot.send_message(
            telegram_id,
            text,
            reply_markup=markup,
        )


class NotificationDispatcher:
    def __init__(
        self,
        session: AsyncSession,
        sender: GenerationReadySender,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._sender = sender
        self._settings = settings or get_settings()

    async def dispatch_due(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> int:
        current = now or datetime.now(UTC)
        batch_size = limit or self._settings.notification_batch_size
        result = await self._session.execute(
            select(
                NotificationOutbox,
                User.telegram_id,
                User.language,
                GenerationJob.modality,
            )
            .join(User, User.id == NotificationOutbox.user_id)
            .join(
                GenerationJob,
                GenerationJob.id == NotificationOutbox.generation_id,
            )
            .where(
                NotificationOutbox.status == "pending",
                NotificationOutbox.next_attempt_at <= current,
            )
            .order_by(
                NotificationOutbox.next_attempt_at,
                NotificationOutbox.created_at,
            )
            .limit(batch_size)
            .with_for_update(of=NotificationOutbox, skip_locked=True)
        )
        rows = list(result.all())
        sent = 0
        for outbox, telegram_id, language, modality in rows:
            outbox.claimed_at = current
            outbox.attempts += 1
            try:
                await self._sender.send_generation_ready(
                    telegram_id=telegram_id,
                    language=Language(language),
                    generation_id=outbox.generation_id,
                    modality=modality,
                )
            except Exception as exc:
                outbox.last_error = type(exc).__name__[:512]
                outbox.claimed_at = None
                if outbox.attempts >= self._settings.notification_max_attempts:
                    outbox.status = "dead"
                else:
                    delay_seconds = min(
                        3600,
                        60 * (2 ** (outbox.attempts - 1)),
                    )
                    outbox.next_attempt_at = current + timedelta(
                        seconds=delay_seconds
                    )
                logger.warning(
                    "notification_send_failed event=%s attempts=%s error=%s",
                    outbox.event_type,
                    outbox.attempts,
                    type(exc).__name__,
                )
                continue

            outbox.status = "sent"
            outbox.sent_at = current
            outbox.claimed_at = None
            outbox.last_error = None
            sent += 1
        await self._session.flush()
        return sent
