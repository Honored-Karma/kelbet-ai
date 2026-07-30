"""Provider webhook intake with duplicate protection and fast worker wake-up."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.domain.enums import GenerationStatus
from kelbet.repositories.generation import GenerationRepository

_TERMINAL = {
    GenerationStatus.SUCCEEDED,
    GenerationStatus.FAILED,
    GenerationStatus.CANCELLED,
    GenerationStatus.TIMED_OUT,
    GenerationStatus.DEAD_LETTER,
}
_WAKE_EVENTS = {
    None,
    "completed",
    "succeeded",
    "failed",
    "task.succeeded",
    "task.failed",
    "video.generated",
}


@dataclass(frozen=True, slots=True)
class WebhookHandleResult:
    duplicate: bool
    generation_id: UUID | None
    status: str | None
    modality: str | None = None
    enqueue: bool = False


class WebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jobs = GenerationRepository(session)

    async def handle(
        self,
        *,
        provider: str,
        event_id: str,
        payload: dict[str, Any],
        payload_hash: str,
        now: datetime | None = None,
    ) -> WebhookHandleResult:
        current = now or datetime.now(UTC)
        data = payload.get("data")
        event_data = data if isinstance(data, dict) else {}
        provider_job_id = (
            payload.get("provider_job_id") or payload.get("id") or event_data.get("id")
        )
        generation_id_raw = payload.get("generation_id")
        generation_id: UUID | None = None
        if generation_id_raw:
            try:
                generation_id = UUID(str(generation_id_raw))
            except (TypeError, ValueError):
                generation_id = None
        elif provider_job_id:
            job = await self._jobs.get_by_provider_job(
                provider=provider,
                provider_job_id=str(provider_job_id),
            )
            if job is not None:
                generation_id = job.id

        inserted = await self._jobs.try_insert_webhook_receipt(
            provider=provider,
            event_id=event_id,
            generation_id=generation_id,
            payload_hash=payload_hash,
            now=current,
        )
        if not inserted:
            return WebhookHandleResult(
                duplicate=True,
                generation_id=generation_id,
                status=None,
            )
        if generation_id is None:
            return WebhookHandleResult(duplicate=False, generation_id=None, status=None)

        job = await self._jobs.get_by_id(generation_id)
        if job is None or job.provider != provider:
            return WebhookHandleResult(
                duplicate=False,
                generation_id=generation_id,
                status=None,
            )

        if provider_job_id and not job.provider_job_id:
            job.provider_job_id = str(provider_job_id)
        job.webhook_last_event_id = event_id
        status = GenerationStatus(job.status)
        event_type = payload.get("type")
        enqueue = event_type in _WAKE_EVENTS and status not in _TERMINAL
        if enqueue and status is GenerationStatus.RUNNING:
            job.next_poll_at = current
        await self._session.flush()
        return WebhookHandleResult(
            duplicate=False,
            generation_id=generation_id,
            status=status.value,
            modality=job.modality,
            enqueue=enqueue,
        )
