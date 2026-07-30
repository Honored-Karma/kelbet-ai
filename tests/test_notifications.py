from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings
from kelbet.db.models.generation import GenerationJob
from kelbet.db.models.notification import NotificationOutbox
from kelbet.domain.enums import Language
from kelbet.repositories.catalog import CatalogRepository
from kelbet.repositories.notification import NotificationRepository
from kelbet.repositories.user import UserRepository
from kelbet.services.notification import NotificationDispatcher
from kelbet.services.registration import RegistrationService


class RecordingSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, Language, UUID, str]] = []

    async def send_generation_ready(
        self,
        *,
        telegram_id: int,
        language: Language,
        generation_id: UUID,
        modality: str,
    ) -> None:
        self.calls.append((telegram_id, language, generation_id, modality))
        if self.fail:
            raise OSError("telegram unavailable")


async def _setup_job(
    session: AsyncSession,
    *,
    telegram_id: int,
    notify: bool = True,
) -> tuple[UUID, UUID]:
    settings = Settings(welcome_credits=5)
    await RegistrationService(session, settings=settings).register_with_language(
        telegram_id=telegram_id,
        username="notify_user",
        language=Language.RU,
    )
    await seed_catalog(session)
    user = await UserRepository(session).get_by_telegram_id(telegram_id)
    model = await CatalogRepository(session).get_by_slug("mock-image")
    assert user is not None
    assert model is not None
    user.notify_generation_ready = notify
    job = GenerationJob(
        user_id=user.id,
        model_id=model.id,
        modality="image",
        status="succeeded",
        idempotency_key=f"notify-{telegram_id}",
        request_hash="a" * 64,
        prompt_redacted=True,
        params={},
        user_credit_price=5,
        provider="mock",
        provider_model_id="mock-image-v1",
        progress_pct=100,
        attempt_count=1,
        max_attempts=3,
        correlation_id=uuid4(),
    )
    session.add(job)
    await session.flush()
    return user.id, job.id


@pytest.mark.asyncio
async def test_notification_outbox_deduplicates_and_dispatches(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        user_id, generation_id = await _setup_job(session, telegram_id=8201)
        repository = NotificationRepository(session)
        assert await repository.enqueue_generation_ready(
            user_id=user_id,
            generation_id=generation_id,
            now=now,
        )
        assert not await repository.enqueue_generation_ready(
            user_id=user_id,
            generation_id=generation_id,
            now=now,
        )
        assert await repository.count_for_generation(generation_id) == 1

        sender = RecordingSender()
        assert await NotificationDispatcher(session, sender).dispatch_due(now=now) == 1
        assert sender.calls == [(8201, Language.RU, generation_id, "image")]
        outbox = (await session.execute(select(NotificationOutbox))).scalar_one()
        assert outbox.status == "sent"
        assert outbox.attempts == 1
        assert outbox.sent_at == now


@pytest.mark.asyncio
async def test_notification_preference_disables_enqueue(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        user_id, generation_id = await _setup_job(
            session,
            telegram_id=8202,
            notify=False,
        )
        inserted = await NotificationRepository(session).enqueue_generation_ready(
            user_id=user_id,
            generation_id=generation_id,
            now=datetime.now(UTC),
        )
        assert inserted is False


@pytest.mark.asyncio
async def test_notification_failure_is_retried_then_dead(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    settings = Settings(notification_max_attempts=1)
    async with session_factory() as session, session.begin():
        user_id, generation_id = await _setup_job(session, telegram_id=8203)
        await NotificationRepository(session).enqueue_generation_ready(
            user_id=user_id,
            generation_id=generation_id,
            now=now,
        )
        sender = RecordingSender(fail=True)
        assert (
            await NotificationDispatcher(session, sender, settings).dispatch_due(
                now=now
            )
            == 0
        )
        outbox = (await session.execute(select(NotificationOutbox))).scalar_one()
        assert outbox.status == "dead"
        assert outbox.attempts == 1
        assert outbox.last_error == "OSError"
