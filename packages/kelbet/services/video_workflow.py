"""Shared vocabulary for the Veo extended (long video) workflow.

The generation runner and the stuck sweeper both have to recognise an extended
job and agree on how long it is allowed to live. Keeping that knowledge in one
module is deliberate: when the sweeper carries its own idea of a video deadline
it will time out a perfectly healthy multi-step job halfway through the chain,
release the reservation, and leave the user with a cancelled premium render.
"""

from __future__ import annotations

from kelbet.config import Settings
from kelbet.db.models.generation import GenerationJob

EXTENDED_WORKFLOW_TYPE = "veo_extend"

#: Cumulative durations the chain checkpoints at. Veo 3.1 returns one merged
#: clip per extension and each call adds +7s of new footage, so the reachable
#: totals are 8 -> 15 -> 22 -> 29 rather than multiples of eight.
EXTENDED_DURATIONS: tuple[int, ...] = (8, 15, 22, 29)


def extended_workflow(job: GenerationJob) -> dict[str, object] | None:
    """Return the extended-workflow descriptor for a job, or None when absent."""

    workflow = (job.routing_snapshot or {}).get("workflow")
    if isinstance(workflow, dict) and workflow.get("type") == EXTENDED_WORKFLOW_TYPE:
        return workflow
    return None


def is_extended_workflow(job: GenerationJob) -> bool:
    """True when the job must run through the multi-step extension chain."""

    return extended_workflow(job) is not None


def extended_durations(job: GenerationJob) -> list[int]:
    """Checkpoints the chain must reach, or [] when the target is not supported."""

    target = int((job.params or {}).get("duration_sec") or 8)
    if target not in EXTENDED_DURATIONS:
        return []
    return [duration for duration in EXTENDED_DURATIONS if duration <= target]


def job_timeout_seconds(settings: Settings, job: GenerationJob) -> int:
    """Whole-job deadline in seconds, honouring the extended workflow budget.

    An extended job spends several provider round trips inside a single
    generation record, so it is measured against the extended total budget
    instead of the single-shot video timeout.
    """

    if is_extended_workflow(job):
        return settings.veo_extended_total_timeout_seconds
    if job.modality == "video":
        return settings.runway_video_timeout_seconds
    if job.modality in {"image", "image_edit", "upscale"}:
        return settings.runway_image_timeout_seconds
    return settings.text_timeout_seconds
