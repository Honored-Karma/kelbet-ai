from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram import Bot
from aiogram.types import Update
from apps.bot.middlewares.telegram_update_inbox import (
    TelegramUpdateInboxMiddleware,
    extract_critical_update,
)
from apps.worker.main import replay_telegram_payment_updates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import TelegramUpdateInbox
from kelbet.services.telegram_update_inbox import (
    ClaimedTelegramUpdate,
    TelegramUpdateInboxService,
)


def _payment_update(update_id: int = 101) -> Update:
    return Update.model_validate(
        {
            "update_id": update_id,
            "message": {
                "message_id": 55,
                "date": 1_786_300_000,
                "chat": {"id": 777_001, "type": "private"},
                "from": {
                    "id": 777_001,
                    "is_bot": False,
                    "first_name": "Private name",
                    "username": "private_username",
                },
                "text": "must never be stored",
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 50,
                    "invoice_payload": "kelbet:order",
                    "telegram_payment_charge_id": "tg-charge",
                    "provider_payment_charge_id": "provider-charge",
                },
            },
        }
    )


def test_payment_extraction_is_minimal_and_privacy_bounded() -> None:
    extracted = extract_critical_update(_payment_update())

    assert extracted is not None
    event_type, payload = extracted
    assert event_type == "successful_payment"
    assert payload["telegram_id"] == 777_001
    assert payload["telegram_payment_charge_id"] == "tg-charge"
    serialized = str(payload)
    assert "Private name" not in serialized
    assert "private_username" not in serialized
    assert "must never be stored" not in serialized


def test_subscription_extraction_omits_user_profile_fields() -> None:
    update = Update.model_validate(
        {
            "update_id": 102,
            "subscription": {
                "user": {
                    "id": 777_002,
                    "is_bot": False,
                    "first_name": "Private name",
                    "username": "private_username",
                },
                "invoice_payload": "kelbet-sub:subscription",
                "state": "failed",
            },
        }
    )

    assert extract_critical_update(update) == (
        "subscription_state",
        {
            "telegram_id": 777_002,
            "invoice_payload": "kelbet-sub:subscription",
            "state": "failed",
        },
    )


@pytest.mark.asyncio
async def test_middleware_persists_before_handler_and_deduplicates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        telegram_update_inbox_stale_seconds=120,
        telegram_update_inbox_max_attempts=5,
    )
    middleware = TelegramUpdateInboxMiddleware(session_factory, settings)
    update = _payment_update()
    calls = 0

    async def handler(event: object, data: dict[str, Any]) -> str:
        del event, data
        nonlocal calls
        calls += 1
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(TelegramUpdateInbox).where(
                        TelegramUpdateInbox.update_id == update.update_id
                    )
                )
            ).scalar_one()
            assert row.status == "processing"
        return "handled"

    assert await middleware(handler, update, {}) == "handled"
    assert await middleware(handler, update, {}) is None
    assert calls == 1
    async with session_factory() as session:
        row = (
            await session.execute(
                select(TelegramUpdateInbox).where(TelegramUpdateInbox.update_id == update.update_id)
            )
        ).scalar_one()
        assert row.status == "processed"
        assert row.processed_at is not None


@pytest.mark.asyncio
async def test_failed_and_abandoned_updates_are_claimed_for_replay(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    started = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    payload = {"telegram_id": 1, "invoice_payload": "kelbet:order"}
    async with session_factory() as session, session.begin():
        service = TelegramUpdateInboxService(session)
        assert await service.claim_delivery(
            update_id=201,
            event_type="successful_payment",
            payload=payload,
            stale_after_seconds=120,
            max_attempts=5,
            now=started,
        )
        await service.mark_failed(201, now=started)
        assert await service.claim_delivery(
            update_id=202,
            event_type="subscription_state",
            payload=payload,
            stale_after_seconds=120,
            max_attempts=5,
            now=started,
        )

    async with session_factory() as session, session.begin():
        claimed = await TelegramUpdateInboxService(session).claim_due(
            limit=10,
            stale_after_seconds=120,
            max_attempts=5,
            now=started + timedelta(seconds=121),
        )

    assert [item.update_id for item in claimed] == [201, 202]
    assert all(item.attempt_count == 2 for item in claimed)


@pytest.mark.asyncio
async def test_worker_closes_success_and_reschedules_failure(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = datetime.now(UTC) - timedelta(minutes=10)
    async with session_factory() as session, session.begin():
        service = TelegramUpdateInboxService(session)
        for update_id in (301, 302):
            assert await service.claim_delivery(
                update_id=update_id,
                event_type="successful_payment",
                payload={"telegram_id": update_id, "invoice_payload": "kelbet:order"},
                stale_after_seconds=120,
                max_attempts=5,
                now=started,
            )
            await service.mark_failed(update_id, now=started)

    async def fake_replay(item: ClaimedTelegramUpdate, **kwargs: object) -> None:
        del kwargs
        if item.update_id == 302:
            raise RuntimeError("simulated handler failure")

    monkeypatch.setattr("apps.worker.main._replay_telegram_update", fake_replay)
    bot = Bot(token="999:CI-TOKEN")
    try:
        count = await replay_telegram_payment_updates(
            {
                "bot": bot,
                "session_factory": session_factory,
                "settings": Settings(
                    telegram_update_inbox_batch_size=10,
                    telegram_update_inbox_stale_seconds=120,
                    telegram_update_inbox_max_attempts=5,
                ),
            }
        )
    finally:
        await bot.session.close()

    assert count == 1
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TelegramUpdateInbox)
                    .where(TelegramUpdateInbox.update_id.in_([301, 302]))
                    .order_by(TelegramUpdateInbox.update_id)
                )
            )
            .scalars()
            .all()
        )
    assert rows[0].status == "processed"
    assert rows[1].status == "failed"
    assert rows[1].last_error_code == "replay_error"
    assert rows[1].next_attempt_at is not None
