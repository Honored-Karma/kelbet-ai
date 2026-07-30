from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models.generation import (
    GenerationAttempt,
    GenerationJob,
    ProviderUsage,
    WebhookReceipt,
)
from kelbet.domain.enums import AttemptStatus, GenerationStatus


class GenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, generation_id: UUID) -> GenerationJob | None:
        result = await self._session.execute(
            select(GenerationJob).where(GenerationJob.id == generation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, generation_id: UUID) -> GenerationJob | None:
        result = await self._session.execute(
            select(GenerationJob).where(GenerationJob.id == generation_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> GenerationJob | None:
        result = await self._session.execute(
            select(GenerationJob).where(
                GenerationJob.user_id == user_id,
                GenerationJob.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[GenerationJob]:
        result = await self._session.execute(
            select(GenerationJob)
            .where(GenerationJob.user_id == user_id)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> GenerationJob:
        job = GenerationJob(**kwargs)
        self._session.add(job)
        await self._session.flush()
        return job

    async def add_attempt(
        self,
        *,
        generation_id: UUID,
        attempt_no: int,
        now: datetime | None = None,
    ) -> GenerationAttempt:
        attempt = GenerationAttempt(
            generation_id=generation_id,
            attempt_no=attempt_no,
            status=AttemptStatus.STARTED.value,
            started_at=now or datetime.now(UTC),
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def add_usage(
        self,
        *,
        generation_id: UUID,
        attempt_id: UUID | None,
        provider: str,
        provider_model_id: str,
        modality: str,
        provider_cost_units: int,
        user_credit_price: int,
        latency_ms: int | None,
        meta: dict[str, Any] | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        now: datetime | None = None,
    ) -> ProviderUsage:
        row = ProviderUsage(
            id=uuid4(),
            generation_id=generation_id,
            attempt_id=attempt_id,
            provider=provider,
            provider_model_id=provider_model_id,
            modality=modality,
            provider_cost_units=provider_cost_units,
            user_credit_price=user_credit_price,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            meta=meta,
            created_at=now or datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def try_insert_webhook_receipt(
        self,
        *,
        provider: str,
        event_id: str,
        generation_id: UUID | None,
        payload_hash: str,
        now: datetime | None = None,
    ) -> bool:
        """Return True if newly inserted; False if duplicate."""
        statement = (
            pg_insert(WebhookReceipt)
            .values(
                id=uuid4(),
                provider=provider,
                event_id=event_id,
                generation_id=generation_id,
                payload_hash=payload_hash,
                processed_at=now or datetime.now(UTC),
            )
            .on_conflict_do_nothing(
                index_elements=[WebhookReceipt.provider, WebhookReceipt.event_id]
            )
            .returning(WebhookReceipt.id)
        )
        inserted = await self._session.execute(statement)
        return inserted.scalar_one_or_none() is not None

    async def list_due_for_poll(
        self, *, now: datetime | None = None, limit: int = 20
    ) -> list[GenerationJob]:
        current = now or datetime.now(UTC)
        result = await self._session.execute(
            select(GenerationJob)
            .where(
                GenerationJob.status == GenerationStatus.RUNNING.value,
                GenerationJob.next_poll_at.is_not(None),
                GenerationJob.next_poll_at <= current,
            )
            .order_by(GenerationJob.next_poll_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def list_active_for_sweep(self, *, limit: int = 50) -> list[GenerationJob]:
        result = await self._session.execute(
            select(GenerationJob)
            .where(
                GenerationJob.status.in_(
                    [
                        GenerationStatus.SUBMITTING.value,
                        GenerationStatus.RUNNING.value,
                        GenerationStatus.FINALIZING.value,
                    ]
                )
            )
            .order_by(GenerationJob.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def count_active_for_user(
        self,
        user_id: UUID,
        *,
        modality: str | None = None,
    ) -> int:
        filters = [
            GenerationJob.user_id == user_id,
            GenerationJob.status.in_(
                [
                    GenerationStatus.CREATED.value,
                    GenerationStatus.QUEUED.value,
                    GenerationStatus.SUBMITTING.value,
                    GenerationStatus.RUNNING.value,
                    GenerationStatus.FINALIZING.value,
                ]
            ),
        ]
        if modality is not None:
            filters.append(GenerationJob.modality == modality)
        result = await self._session.execute(select(GenerationJob.id).where(*filters))
        return len(list(result.scalars().all()))

    async def get_by_provider_job(
        self, *, provider: str, provider_job_id: str
    ) -> GenerationJob | None:
        result = await self._session.execute(
            select(GenerationJob).where(
                GenerationJob.provider == provider,
                GenerationJob.provider_job_id == provider_job_id,
            )
        )
        return result.scalar_one_or_none()
