from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.catalog.seed_db import seed_catalog
from kelbet.db.models import (
    CatalogModel,
    CreditReservation,
    CreditTransaction,
    GenerationAsset,
    GenerationAttempt,
    GenerationJob,
    ProviderUsage,
    User,
    Wallet,
)
from kelbet.domain.enums import (
    AssetRole,
    AssetStatus,
    AttemptStatus,
    GenerationStatus,
    Language,
    Plan,
    ReservationStatus,
    RetentionClass,
    TxReason,
    TxType,
)
from kelbet.operations import reconcile_video_jobs
from kelbet.services.wallet import capture_idempotency_key


@pytest.mark.asyncio
async def test_reconcile_one_hundred_video_jobs_and_detect_corruption(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    price = 100
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        model = (
            await session.execute(
                select(CatalogModel).where(
                    CatalogModel.slug == "runway-gemini-omni-video-fast"
                )
            )
        ).scalar_one()
        user = User(
            telegram_id=990_100,
            username="video_reconciliation",
            language=Language.RU.value,
            plan=Plan.FREE.value,
        )
        session.add(user)
        await session.flush()
        wallet = Wallet(user_id=user.id, balance=0, reserved=0, version=100)
        session.add(wallet)
        await session.flush()

        first_reservation: CreditReservation | None = None
        jobs: list[GenerationJob] = []
        attempts: list[GenerationAttempt] = []
        usages: list[ProviderUsage] = []
        assets: list[GenerationAsset] = []
        for index in range(100):
            job_id = uuid4()
            reservation_id = uuid4()
            transaction_id = uuid4()
            attempt_id = uuid4()
            remaining_balance = (99 - index) * price
            transaction = CreditTransaction(
                id=transaction_id,
                wallet_id=wallet.id,
                amount=-price,
                balance_after=remaining_balance,
                type=TxType.DEBIT.value,
                reason=TxReason.GENERATION_CAPTURE.value,
                idempotency_key=capture_idempotency_key(reservation_id),
                meta={"source": "generation_capture"},
            )
            reservation = CreditReservation(
                id=reservation_id,
                wallet_id=wallet.id,
                user_id=user.id,
                generation_id=job_id,
                amount=price,
                status=ReservationStatus.CAPTURED.value,
                idempotency_key=f"reserve:reconciliation:{index}",
                quote_snapshot={
                    "model_slug": model.slug,
                    "user_credit_price": price,
                    "params": {"duration_sec": 4},
                },
                capture_tx_id=transaction_id,
                refund_tx_id=None,
                expires_at=now + timedelta(hours=1),
                held_at=now,
                finalized_at=now,
            )
            job = GenerationJob(
                id=job_id,
                user_id=user.id,
                model_id=model.id,
                modality="video",
                status=GenerationStatus.SUCCEEDED.value,
                idempotency_key=f"reconciliation:{index}",
                request_hash=f"{index:064x}",
                prompt_redacted=True,
                params={"duration_sec": 4, "aspect_ratio": "9:16", "resolution": "720p"},
                prompt_storage_key=None,
                input_asset_ids=[],
                reservation_id=reservation_id,
                quote_id=None,
                user_credit_price=price,
                provider="runway",
                provider_model_id="gemini_omni_flash",
                provider_job_id=f"runway-reconciliation-{index}",
                progress_pct=100,
                progress_stage="done",
                error_code=None,
                error_class=None,
                attempt_count=1,
                max_attempts=3,
                queued_at=now,
                started_at=now,
                finished_at=now,
                cancel_requested_at=None,
                dead_letter_at=None,
                next_poll_at=None,
                webhook_last_event_id=None,
                correlation_id=uuid4(),
                prompt="reconciliation prompt",
            )
            attempt = GenerationAttempt(
                id=attempt_id,
                generation_id=job_id,
                attempt_no=1,
                status=AttemptStatus.SUCCEEDED.value,
                provider_request_id=None,
                provider_job_id=job.provider_job_id,
                latency_ms=10,
                error_code=None,
                error_message_safe=None,
                raw_response_meta={"status": "succeeded"},
                started_at=now,
                finished_at=now,
            )
            usage = ProviderUsage(
                generation_id=job_id,
                attempt_id=attempt_id,
                provider="runway",
                provider_model_id="gemini_omni_flash",
                modality="video",
                provider_cost_units=4_000,
                user_credit_price=price,
                latency_ms=10,
                http_status=200,
                tokens_in=None,
                tokens_out=None,
                meta={"status": "succeeded"},
                created_at=now,
            )
            asset = GenerationAsset(
                generation_id=job_id,
                user_id=user.id,
                role=AssetRole.OUTPUT.value,
                status=AssetStatus.READY.value,
                storage_backend="memory",
                bucket="kelbet-assets",
                object_key=f"outputs/reconciliation-{index}.mp4",
                content_type="video/mp4",
                byte_size=32,
                declared_byte_size=32,
                sha256=f"{index:064x}",
                magic_ok=True,
                visibility="private",
                retention_class=RetentionClass.PERMANENT_OUTPUT.value,
                expires_at=None,
                deleted_at=None,
                reject_reason=None,
                width=None,
                height=None,
            )
            session.add_all([transaction, reservation])
            jobs.append(job)
            attempts.append(attempt)
            usages.append(usage)
            assets.append(asset)
            first_reservation = first_reservation or reservation
        await session.flush()
        session.add_all(jobs)
        await session.flush()
        session.add_all([*attempts, *usages, *assets])
        await session.flush()

        report = await reconcile_video_jobs(
            session,
            since=now - timedelta(minutes=5),
            minimum_jobs=100,
            now=now + timedelta(minutes=1),
        )
        assert report.passed is True
        assert report.selected_jobs == 100
        assert report.terminal_jobs == 100
        assert report.user_credits_expected == 10_000
        assert report.user_credits_captured == 10_000
        assert report.provider_cost_units == 400_000
        assert report.issues == []

        assert first_reservation is not None
        first_reservation.status = ReservationStatus.HELD.value
        await session.flush()
        corrupted = await reconcile_video_jobs(
            session,
            since=now - timedelta(minutes=5),
            minimum_jobs=100,
            now=now + timedelta(minutes=1),
        )
        assert corrupted.passed is False
        assert "success_not_captured" in {issue.code for issue in corrupted.issues}

        jobs[0].status = GenerationStatus.RUNNING.value
        jobs[0].finished_at = None
        jobs[0].next_poll_at = now + timedelta(minutes=5)
        await session.flush()
        active_batch = await reconcile_video_jobs(
            session,
            since=now - timedelta(minutes=5),
            minimum_jobs=100,
            now=now + timedelta(minutes=1),
        )
        active_codes = {issue.code for issue in active_batch.issues}
        assert active_batch.passed is False
        assert active_batch.active_jobs == 1
        assert "non_terminal_jobs" in active_codes
        assert "active_reservation_already_finalized" in active_codes
