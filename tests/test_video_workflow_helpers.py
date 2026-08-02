"""Pure unit tests for the shared Veo extended-workflow helpers.

These need no database: they pin the contract that the generation runner and the
stuck sweeper both depend on.
"""

from __future__ import annotations

import pytest

from kelbet.config import get_settings
from kelbet.db.models.generation import GenerationJob
from kelbet.services.video_workflow import (
    extended_durations,
    is_extended_workflow,
    job_timeout_seconds,
)


def _job(
    *,
    modality: str = "video",
    workflow: dict[str, object] | None = None,
    duration_sec: int | None = None,
) -> GenerationJob:
    routing_snapshot: dict[str, object] = {}
    if workflow is not None:
        routing_snapshot["workflow"] = workflow
    params: dict[str, object] = {}
    if duration_sec is not None:
        params["duration_sec"] = duration_sec
    return GenerationJob(
        modality=modality,
        routing_snapshot=routing_snapshot,
        params=params,
    )


def test_plain_video_job_is_not_extended() -> None:
    assert is_extended_workflow(_job()) is False


def test_extended_job_detected_by_workflow_type() -> None:
    assert is_extended_workflow(_job(workflow={"type": "veo_extend"})) is True


def test_foreign_workflow_type_is_not_extended() -> None:
    assert is_extended_workflow(_job(workflow={"type": "runway_chain"})) is False


def test_missing_routing_snapshot_is_not_extended() -> None:
    job = GenerationJob(modality="video", routing_snapshot=None, params=None)
    assert is_extended_workflow(job) is False


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (8, [8]),
        (15, [8, 15]),
        (22, [8, 15, 22]),
        (29, [8, 15, 22, 29]),
    ],
)
def test_extended_durations_build_cumulative_chain(target: int, expected: list[int]) -> None:
    """Veo returns one merged clip per call and each extension adds +7 seconds."""

    job = _job(workflow={"type": "veo_extend"}, duration_sec=target)
    assert extended_durations(job) == expected


@pytest.mark.parametrize("target", [5, 10, 16, 30, 60])
def test_unsupported_target_yields_no_chain(target: int) -> None:
    job = _job(workflow={"type": "veo_extend"}, duration_sec=target)
    assert extended_durations(job) == []


def test_extended_job_uses_extended_budget_not_single_shot_video_timeout() -> None:
    """Regression: the sweeper reaped healthy long renders at the Runway deadline."""

    settings = get_settings().model_copy(
        update={
            "runway_video_timeout_seconds": 1800,
            "veo_extended_total_timeout_seconds": 3600,
        }
    )
    extended = _job(workflow={"type": "veo_extend"}, duration_sec=29)
    plain = _job()

    assert job_timeout_seconds(settings, extended) == 3600
    assert job_timeout_seconds(settings, plain) == 1800


def test_non_video_modalities_keep_their_own_budgets() -> None:
    settings = get_settings().model_copy(
        update={
            "runway_image_timeout_seconds": 600,
            "text_timeout_seconds": 120,
        }
    )

    assert job_timeout_seconds(settings, _job(modality="image")) == 600
    assert job_timeout_seconds(settings, _job(modality="image_edit")) == 600
    assert job_timeout_seconds(settings, _job(modality="upscale")) == 600
    assert job_timeout_seconds(settings, _job(modality="text")) == 120
