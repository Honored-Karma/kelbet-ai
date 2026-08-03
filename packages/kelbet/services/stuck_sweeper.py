"""Recover stuck generation jobs past their modality, submitting or claim deadlines."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models.generation import GenerationJob
from kelbet.domain.enums import GenerationStatus
from kelbet.observability import get_metrics
from kelbet.providers.factory import resolve_provider
from kelbet.repositories.generation import GenerationRepository
from kelbet.services.generation_sm import apply_transition
from kelbet.services.video_workflow import job_timeout_seconds
from kelbet.services.wallet import WalletService

logger = logging.getLogger(__name__)


class StuckSweeper:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._jobs = GenerationRepository(session)
        self._wallet = WalletService(session)

    def _timeout_seconds(self, job: GenerationJob) -> int:
        """Deadline for this job, not merely for its modality.

        An extended Veo job chains several provider calls inside one generation
        record, so it is measured against the extended budget; using the plain
        video timeout here would reap healthy long renders mid-chain.
        """

        return job_timeout_seconds(self._settings, job)

    async def sweep(self, *, now: datetime | None = None, limit: int = 50) -> list[UUID]:
        current = now or datetime.now(UTC)
        candidates = await self._jobs.list_active_for_sweep(limit=limit)
        swept: list[UUID] = []
        for job in candidates:
            status = GenerationStatus(job.status)
            anchor = job.started_at or job.queued_at or job.created_at
            modality_deadline = anchor + timedelta(seconds=self._timeout_seconds(job))
            submitting_deadline = anchor + timedelta(
                seconds=self._settings.stuck_submitting_seconds
            )

            unclaimed_deadline = anchor + timedelta(seconds=self._settings.stuck_queued_seconds)

            should_timeout = False
            if status is GenerationStatus.RUNNING:
                should_timeout = current >= modality_deadline
            elif status is GenerationStatus.SUBMITTING:
                should_timeout = current >= min(modality_deadline, submitting_deadline)
            elif status is GenerationStatus.FINALIZING:
                should_timeout = current >= modality_deadline
            elif status in {GenerationStatus.CREATED, GenerationStatus.QUEUED}:
                # No provider has been contacted yet, so the modality budget says
                # nothing here: the job is waiting to be claimed at all.
                should_timeout = current >= unclaimed_deadline

            if not should_timeout:
                continue

            # A job nobody claimed failed for a different reason than one a
            # provider sat on, and only the former means the queue is dropping
            # messages. Keeping the codes apart makes that visible in metrics
            # instead of hiding an infrastructure fault inside provider noise.
            unclaimed = status in {GenerationStatus.CREATED, GenerationStatus.QUEUED}
            error_code = "stuck_unclaimed" if unclaimed else "stuck_timeout"

            if job.provider_job_id:
                provider = resolve_provider(
                    job.provider, modality=job.modality, settings=self._settings
                )
                try:
                    await provider.cancel(job.provider_job_id)
                except Exception:  # noqa: BLE001 — best-effort cancel
                    get_metrics().incr(
                        "stuck_generation.total",
                        tags={
                            "action": "cancel_failed",
                            "modality": job.modality,
                            "previous_status": status.value,
                        },
                    )
                    logger.warning(
                        "stuck_sweeper_cancel_failed generation_id=%s",
                        job.id,
                    )

            apply_transition(
                job,
                GenerationStatus.TIMED_OUT,
                now=current,
                error_code=error_code,
                error_class="timeout",
                progress_stage="timed_out",
            )
            if job.reservation_id is not None:
                await self._wallet.release(job.reservation_id, now=current)
            job.next_poll_at = None
            swept.append(job.id)
            get_metrics().incr(
                "stuck_generation.total",
                tags={
                    "action": "timed_out",
                    "modality": job.modality,
                    "previous_status": status.value,
                },
            )
            get_metrics().incr(
                "generation.terminal",
                tags={"status": GenerationStatus.TIMED_OUT.value, "modality": job.modality},
            )
            created_at = job.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            get_metrics().observe(
                "generation.duration_seconds",
                max(0.0, (current - created_at).total_seconds()),
                tags={
                    "status": GenerationStatus.TIMED_OUT.value,
                    "modality": job.modality,
                    "provider": job.provider,
                },
            )
            logger.info(
                "stuck_sweeper_timed_out generation_id=%s modality=%s status_was=%s",
                job.id,
                job.modality,
                status.value,
            )

        if swept:
            await self._session.flush()
        return swept
