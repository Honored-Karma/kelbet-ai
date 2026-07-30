"""Transactional generation status transitions."""

from __future__ import annotations

from datetime import UTC, datetime

from kelbet.db.models.generation import GenerationJob
from kelbet.domain.enums import GenerationStatus
from kelbet.domain.exceptions import InvalidGenerationTransitionError

_ALLOWED: dict[GenerationStatus, frozenset[GenerationStatus]] = {
    GenerationStatus.CREATED: frozenset(
        {GenerationStatus.QUEUED, GenerationStatus.CANCELLED}
    ),
    GenerationStatus.QUEUED: frozenset(
        {GenerationStatus.SUBMITTING, GenerationStatus.CANCELLED}
    ),
    GenerationStatus.SUBMITTING: frozenset(
        {
            GenerationStatus.RUNNING,
            GenerationStatus.FINALIZING,
            GenerationStatus.QUEUED,
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
        }
    ),
    GenerationStatus.RUNNING: frozenset(
        {
            GenerationStatus.RUNNING,
            GenerationStatus.FINALIZING,
            GenerationStatus.QUEUED,
            GenerationStatus.FAILED,
            GenerationStatus.TIMED_OUT,
            GenerationStatus.CANCELLED,
        }
    ),
    GenerationStatus.FINALIZING: frozenset(
        {
            GenerationStatus.SUCCEEDED,
            GenerationStatus.FAILED,
            GenerationStatus.DEAD_LETTER,
        }
    ),
    GenerationStatus.SUCCEEDED: frozenset(),
    GenerationStatus.FAILED: frozenset(),
    GenerationStatus.CANCELLED: frozenset(),
    GenerationStatus.TIMED_OUT: frozenset(),
    GenerationStatus.DEAD_LETTER: frozenset(),
}


def assert_transition(job: GenerationJob, to: GenerationStatus) -> None:
    current = GenerationStatus(job.status)
    if to not in _ALLOWED[current]:
        raise InvalidGenerationTransitionError(f"Cannot transition {current} -> {to}")


def apply_transition(
    job: GenerationJob,
    to: GenerationStatus,
    *,
    now: datetime | None = None,
    progress_pct: int | None = None,
    progress_stage: str | None = None,
    error_code: str | None = None,
    error_class: str | None = None,
) -> None:
    assert_transition(job, to)
    current = now or datetime.now(UTC)
    job.status = to.value
    if progress_pct is not None:
        job.progress_pct = progress_pct
    if progress_stage is not None:
        job.progress_stage = progress_stage
    if error_code is not None:
        job.error_code = error_code
    if error_class is not None:
        job.error_class = error_class

    if to is GenerationStatus.QUEUED and job.queued_at is None:
        job.queued_at = current
    if to is GenerationStatus.SUBMITTING and job.started_at is None:
        job.started_at = current
    if to in {
        GenerationStatus.SUCCEEDED,
        GenerationStatus.FAILED,
        GenerationStatus.CANCELLED,
        GenerationStatus.TIMED_OUT,
        GenerationStatus.DEAD_LETTER,
    }:
        job.finished_at = current
        if to is GenerationStatus.SUCCEEDED:
            job.progress_pct = 100
            job.progress_stage = "done"
    if to is GenerationStatus.DEAD_LETTER:
        job.dead_letter_at = current
