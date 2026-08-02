"""Process generation jobs: sync finalize or async accept → poll → capture/release."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.pricing import compute_user_credit_price
from kelbet.config import Settings, get_settings
from kelbet.db.models.asset import GenerationAsset
from kelbet.db.models.generation import GenerationAttempt, GenerationJob, GenerationWorkflowStep
from kelbet.domain.enums import (
    AssetRole,
    AssetStatus,
    AttemptStatus,
    GenerationStatus,
    RetentionClass,
)
from kelbet.domain.exceptions import GenerationNotFoundError
from kelbet.observability import classify_provider_failure, get_metrics
from kelbet.providers.base import (
    GenerationOutput,
    GenerationProvider,
    GenerationProviderResult,
    GenerationRequest,
)
from kelbet.providers.factory import resolve_provider
from kelbet.repositories.asset import AssetRepository
from kelbet.repositories.catalog import CatalogRepository
from kelbet.repositories.generation import GenerationRepository
from kelbet.repositories.notification import NotificationRepository
from kelbet.repositories.user import UserRepository
from kelbet.services.catalog import FeatureFlagService
from kelbet.services.generation_sm import apply_transition
from kelbet.services.template_compositor import TemplateCompositor, TemplateCompositorError
from kelbet.services.video_workflow import (
    extended_durations,
    extended_workflow,
    is_extended_workflow,
)
from kelbet.services.wallet import WalletService
from kelbet.storage import (
    ObjectStorage,
    build_output_object_key,
    build_workflow_step_object_key,
    image_dimensions,
)
from kelbet.storage.memory import MemoryObjectStorage
from kelbet.storage.s3 import S3ObjectStorage

logger = logging.getLogger(__name__)


def _record_terminal_metrics(
    job: GenerationJob,
    status: GenerationStatus,
    *,
    now: datetime,
) -> None:
    metrics = get_metrics()
    metrics.incr(
        "generation.terminal",
        tags={"status": status.value, "modality": job.modality},
    )
    if job.template_slug and status in {
        GenerationStatus.SUCCEEDED,
        GenerationStatus.FAILED,
    }:
        raw_kind = job.template_snapshot.get("kind")
        kind = raw_kind if isinstance(raw_kind, str) else "other"
        metrics.incr(
            "template.terminal",
            tags={"template": job.template_slug, "kind": kind, "outcome": status.value},
        )
    created_at = job.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    metrics.observe(
        "generation.duration_seconds",
        max(0.0, (now - created_at).total_seconds()),
        tags={"status": status.value, "modality": job.modality, "provider": job.provider},
    )


def _record_provider_failure_metrics(
    job: GenerationJob,
    result: GenerationProviderResult,
) -> None:
    raw_status = result.meta.get("http_status")
    http_status = raw_status if isinstance(raw_status, int) else None
    get_metrics().incr(
        "provider.failure",
        tags={
            "provider": job.provider,
            "classification": classify_provider_failure(result.error_code, http_status),
        },
    )


def _token(meta: dict[str, object] | None, key: str) -> int | None:
    if not meta:
        return None
    value = meta.get(key)
    return value if isinstance(value, int) else None


def _attempt_diagnostics(meta: dict[str, object] | None) -> dict[str, object]:
    if not meta:
        return {}
    safe_keys = {
        "create_path",
        "http_status",
        "provider_error",
        "provider_error_code",
        "provider_status",
    }
    return {key: value for key, value in meta.items() if key in safe_keys}


def _provider_route(job: GenerationJob) -> str:
    primary = (job.routing_snapshot or {}).get("primary")
    primary = primary if isinstance(primary, dict) else {}
    return "primary" if primary.get("provider") in {None, job.provider} else "fallback"


def _record_provider_route_metrics(
    job: GenerationJob,
    result: GenerationProviderResult,
    *,
    outcome: str,
) -> None:
    route = _provider_route(job)
    tags = {
        "provider": job.provider,
        "route": route,
        "outcome": outcome,
        "modality": job.modality,
    }
    metrics = get_metrics()
    metrics.incr("provider.route", tags=tags)
    metrics.observe("provider.route_latency_seconds", max(0, result.latency_ms) / 1000, tags=tags)
    metrics.observe(
        "provider.route_cost_units",
        max(0, result.provider_cost_units),
        tags={"provider": job.provider, "route": route, "modality": job.modality},
    )


class GenerationRunner:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        provider: GenerationProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._provider_override = provider
        self._settings = settings or get_settings()
        self._jobs = GenerationRepository(session)
        self._catalog = CatalogRepository(session)
        self._notifications = NotificationRepository(session)
        self._wallet = WalletService(session)
        self._template_compositor = TemplateCompositor()

    def _provider_for(self, job: GenerationJob) -> GenerationProvider:
        return self._provider_override or resolve_provider(
            job.provider,
            modality=job.modality,
            settings=self._settings,
        )

    def _timeout_seconds(self, modality: str) -> int:
        if modality == "video":
            return self._settings.runway_video_timeout_seconds
        if modality in {"image", "image_edit", "upscale"}:
            return self._settings.runway_image_timeout_seconds
        return 120

    def _poll_interval(self, job: GenerationJob) -> timedelta:
        base_seconds = max(5, self._settings.runway_poll_interval_seconds)
        jitter_ceiling = max(0, self._settings.runway_poll_jitter_seconds)
        jitter_seconds = job.id.int % (jitter_ceiling + 1) if jitter_ceiling else 0
        return timedelta(seconds=base_seconds + jitter_seconds)

    async def _store_output_bytes(self, *, object_key: str, data: bytes, content_type: str) -> None:
        if isinstance(self._storage, MemoryObjectStorage):
            self._storage.put_bytes(object_key, data, content_type=content_type)
            return
        if isinstance(self._storage, S3ObjectStorage):

            def _put() -> None:
                self._storage._client.put_object(  # type: ignore[attr-defined]
                    Bucket=self._storage.bucket,
                    Key=object_key,
                    Body=data,
                    ContentType=content_type,
                )

            await asyncio.to_thread(_put)
            return
        msg = f"Unsupported storage backend for server-side put: {type(self._storage)}"
        raise TypeError(msg)

    async def process(
        self, generation_id: UUID, *, now: datetime | None = None
    ) -> GenerationStatus:
        current = now or datetime.now(UTC)
        job = await self._jobs.get_by_id_for_update(generation_id)
        if job is None:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")

        status = GenerationStatus(job.status)
        if status in {
            GenerationStatus.SUCCEEDED,
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
            GenerationStatus.TIMED_OUT,
            GenerationStatus.DEAD_LETTER,
        }:
            return status

        if status is GenerationStatus.RUNNING:
            return await self.poll(generation_id, now=current)

        if job.cancel_requested_at is not None and status in {
            GenerationStatus.QUEUED,
            GenerationStatus.CREATED,
            GenerationStatus.SUBMITTING,
        }:
            return await self._cancel_held(job, now=current)

        if self._is_extended_workflow(job):
            return await self._process_extended(job, now=current)

        if status is GenerationStatus.QUEUED:
            apply_transition(
                job,
                GenerationStatus.SUBMITTING,
                now=current,
                progress_pct=10,
                progress_stage="submitting",
            )
            await self._session.flush()
            job = await self._jobs.get_by_id_for_update(generation_id)
            assert job is not None

        if job.cancel_requested_at is not None:
            return await self._cancel_held(job, now=current)

        job.attempt_count += 1
        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count,
            now=current,
        )
        provider = self._provider_for(job)

        input_keys: list[str] = []
        input_urls: list[str] = []
        if job.input_asset_ids:
            assets = AssetRepository(self._session)
            for asset_id in job.input_asset_ids:
                asset = await assets.get_by_id(asset_id)
                if (
                    asset is None
                    or asset.user_id != job.user_id
                    or asset.role not in {AssetRole.INPUT.value, AssetRole.OUTPUT.value}
                    or asset.status != AssetStatus.READY.value
                    or asset.deleted_at is not None
                    or (asset.expires_at is not None and asset.expires_at <= current)
                ):
                    return await self._fail(
                        job,
                        attempt,
                        GenerationProviderResult(
                            status="failed",
                            error_code="input_asset_unavailable",
                            error_message_safe="A reference image is no longer available",
                        ),
                        now=current,
                    )
                input_keys.append(asset.object_key)
                signed = await self._storage.create_presigned_get(
                    object_key=asset.object_key,
                    content_type=asset.content_type,
                    download_name=f"reference-{asset.id}",
                    expires_in=self._settings.s3_presign_ttl_seconds,
                )
                input_urls.append(signed.url)

        result = await provider.generate(
            GenerationRequest(
                generation_id=job.id,
                provider_model_id=job.provider_model_id,
                modality=job.modality,
                prompt=job.prompt or "",
                params=dict(job.params or {}),
                input_object_keys=input_keys,
                input_urls=input_urls,
            )
        )
        attempt.latency_ms = result.latency_ms
        attempt.provider_job_id = result.provider_job_id
        attempt.raw_response_meta = {
            "status": result.status,
            "provider": job.provider,
            "provider_model_id": job.provider_model_id,
            **_attempt_diagnostics(result.meta),
        }

        if result.status == "failed":
            _record_provider_failure_metrics(job, result)
            fallback_status = await self._try_fallback(
                job,
                attempt,
                result,
                now=current,
                input_keys=input_keys,
                input_urls=input_urls,
            )
            if fallback_status is not None:
                return fallback_status
            return await self._fail(job, attempt, result, now=current)

        if result.status == "accepted":
            job.provider_job_id = result.provider_job_id
            apply_transition(
                job,
                GenerationStatus.RUNNING,
                now=current,
                progress_pct=40,
                progress_stage="running",
            )
            job.next_poll_at = current + self._poll_interval(job)
            await self._session.flush()
            return GenerationStatus.RUNNING

        return await self._finalize_success(job, attempt, result, now=current)

    async def poll(
        self,
        generation_id: UUID,
        *,
        now: datetime | None = None,
        result_override: GenerationProviderResult | None = None,
    ) -> GenerationStatus:
        current = now or datetime.now(UTC)
        job = await self._jobs.get_by_id_for_update(generation_id)
        if job is None:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")

        status = GenerationStatus(job.status)
        if status in {
            GenerationStatus.SUCCEEDED,
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
            GenerationStatus.TIMED_OUT,
            GenerationStatus.DEAD_LETTER,
        }:
            return status

        if status is not GenerationStatus.RUNNING:
            return status

        if self._is_extended_workflow(job):
            return await self._poll_extended(job, now=current, result_override=result_override)

        if job.cancel_requested_at is not None:
            provider = self._provider_for(job)
            if job.provider_job_id:
                await provider.cancel(job.provider_job_id)
            return await self._cancel_held(job, now=current)

        started = job.started_at or job.queued_at or job.created_at
        deadline = started + timedelta(seconds=self._timeout_seconds(job.modality))
        if current >= deadline:
            provider = self._provider_for(job)
            if job.provider_job_id:
                await provider.cancel(job.provider_job_id)
            timeout_result = GenerationProviderResult(
                status="failed",
                provider_job_id=job.provider_job_id,
                error_code="provider_timeout",
                error_message_safe="Provider generation timed out",
            )
            timeout_attempt = await self._jobs.add_attempt(
                generation_id=job.id,
                attempt_no=job.attempt_count + 1,
                now=current,
            )
            job.attempt_count += 1
            timeout_attempt.provider_job_id = job.provider_job_id
            timeout_attempt.raw_response_meta = {
                "status": "failed",
                "provider": job.provider,
                "provider_model_id": job.provider_model_id,
            }
            _record_provider_failure_metrics(job, timeout_result)
            fallback_status = await self._try_fallback(
                job,
                timeout_attempt,
                timeout_result,
                now=current,
            )
            if fallback_status is not None:
                return fallback_status
            timeout_attempt.status = AttemptStatus.FAILED.value
            timeout_attempt.error_code = "provider_timeout"
            timeout_attempt.error_message_safe = "Provider generation timed out"
            timeout_attempt.finished_at = current
            _record_provider_route_metrics(job, timeout_result, outcome="failed")
            apply_transition(
                job,
                GenerationStatus.TIMED_OUT,
                now=current,
                error_code="provider_timeout",
                error_class="timeout",
                progress_stage="timed_out",
            )
            if job.reservation_id is not None:
                await self._wallet.release(job.reservation_id, now=current)
            job.next_poll_at = None
            await self._session.flush()
            _record_terminal_metrics(job, GenerationStatus.TIMED_OUT, now=current)
            return GenerationStatus.TIMED_OUT

        provider = self._provider_for(job)
        if result_override is not None:
            result = result_override
        else:
            if not job.provider_job_id:
                return await self._fail_running(
                    job,
                    GenerationProviderResult(
                        status="failed",
                        error_code="missing_provider_job_id",
                        error_message_safe="Missing provider job id",
                    ),
                    now=current,
                )
            result = await provider.get_status(job.provider_job_id)

        if result.status == "accepted":
            job.next_poll_at = current + self._poll_interval(job)
            if result.meta.get("provider_status"):
                job.progress_stage = str(result.meta["provider_status"]).lower()
            job.progress_pct = min(75, max(45, job.progress_pct + 5))
            await self._session.flush()
            return GenerationStatus.RUNNING

        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count + 1,
            now=current,
        )
        job.attempt_count += 1
        attempt.provider_job_id = result.provider_job_id or job.provider_job_id
        attempt.latency_ms = result.latency_ms
        attempt.raw_response_meta = {
            "status": result.status,
            "provider": job.provider,
            "provider_model_id": job.provider_model_id,
            **_attempt_diagnostics(result.meta),
        }

        if result.status == "failed":
            _record_provider_failure_metrics(job, result)
            fallback_status = await self._try_fallback(
                job,
                attempt,
                result,
                now=current,
            )
            if fallback_status is not None:
                return fallback_status
            return await self._fail(job, attempt, result, now=current)

        return await self._finalize_success(job, attempt, result, now=current)

    # The extended-workflow vocabulary lives in kelbet.services.video_workflow so
    # that the stuck sweeper reaches the same verdict as the runner. These thin
    # wrappers keep the existing call sites untouched.

    @staticmethod
    def _extended_workflow(job: GenerationJob) -> dict[str, object] | None:
        return extended_workflow(job)

    @classmethod
    def _is_extended_workflow(cls, job: GenerationJob) -> bool:
        return is_extended_workflow(job)

    @staticmethod
    def _extended_durations(job: GenerationJob) -> list[int]:
        return extended_durations(job)

    async def _process_extended(
        self,
        job: GenerationJob,
        *,
        now: datetime,
    ) -> GenerationStatus:
        if GenerationStatus(job.status) is GenerationStatus.QUEUED:
            apply_transition(
                job,
                GenerationStatus.SUBMITTING,
                now=now,
                progress_pct=5,
                progress_stage="workflow_preparing",
            )
        durations = self._extended_durations(job)
        if not durations or job.provider_model_id != "veo-3.1-fast-generate-preview":
            attempt = await self._jobs.add_attempt(
                generation_id=job.id,
                attempt_no=job.attempt_count + 1,
                now=now,
            )
            job.attempt_count += 1
            return await self._fail(
                job,
                attempt,
                GenerationProviderResult(
                    status="failed",
                    error_code="invalid_extended_workflow",
                    error_message_safe="Extended video configuration is invalid",
                ),
                now=now,
                error_class="configuration",
            )
        steps = await self._jobs.ensure_workflow_steps(
            generation_id=job.id,
            cumulative_durations=durations,
            now=now,
        )
        if job.cancel_requested_at is not None:
            await self._cleanup_workflow_steps(steps)
            return await self._cancel_held(job, now=now)
        pending = next((step for step in steps if step.status != "succeeded"), None)
        if pending is None:
            return await self._resume_extended_finalization(job, steps, now=now)
        return await self._start_extended_step(job, steps, pending, now=now)

    async def _start_extended_step(
        self,
        job: GenerationJob,
        steps: list[GenerationWorkflowStep],
        step: GenerationWorkflowStep,
        *,
        now: datetime,
    ) -> GenerationStatus:
        extension_video: GenerationOutput | None = None
        input_keys: list[str] = []
        input_urls: list[str] = []
        if step.step_index == 0:
            prepared = await self._prepare_input_materials(job, now=now)
            if prepared is None:
                attempt = await self._jobs.add_attempt(
                    generation_id=job.id,
                    attempt_no=job.attempt_count + 1,
                    now=now,
                )
                job.attempt_count += 1
                return await self._fail(
                    job,
                    attempt,
                    GenerationProviderResult(
                        status="failed",
                        error_code="input_asset_unavailable",
                        error_message_safe="A reference image is no longer available",
                    ),
                    now=now,
                )
            input_keys, input_urls = prepared
        else:
            previous = steps[step.step_index - 1]
            if not previous.intermediate_object_key:
                return await self._fail_extended_step(
                    job,
                    step,
                    GenerationProviderResult(
                        status="failed",
                        error_code="workflow_intermediate_missing",
                        error_message_safe="The previous video step is unavailable",
                    ),
                    now=now,
                )
            try:
                previous_bytes = await self._storage.get_object(
                    object_key=previous.intermediate_object_key
                )
            except Exception:
                logger.exception(
                    "workflow_intermediate_read_failed",
                    extra={"generation_id": str(job.id), "step_index": step.step_index},
                )
                return await self._fail_extended_step(
                    job,
                    step,
                    GenerationProviderResult(
                        status="failed",
                        error_code="workflow_intermediate_missing",
                        error_message_safe="The previous video step is unavailable",
                    ),
                    now=now,
                )
            extension_video = GenerationOutput(content_type="video/mp4", data=previous_bytes)

        job.attempt_count += 1
        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count,
            now=now,
        )
        step.status = "submitting"
        step.attempt_count += 1
        step.started_at = now
        step.finished_at = None
        step.error_code = None
        step.updated_at = now
        total_steps = len(steps)
        job.progress_stage = f"veo_extend_{step.step_index + 1}_of_{total_steps}"
        job.progress_pct = max(10, int(step.step_index / total_steps * 75))
        result = await self._provider_for(job).generate(
            GenerationRequest(
                generation_id=job.id,
                provider_model_id=job.provider_model_id,
                modality=job.modality,
                prompt=job.prompt or "",
                params={
                    **dict(job.params or {}),
                    "duration_sec": 8,
                    "resolution": "720p",
                },
                input_object_keys=input_keys,
                input_urls=input_urls,
                extension_video=extension_video,
            )
        )
        attempt.latency_ms = result.latency_ms
        attempt.provider_job_id = result.provider_job_id
        attempt.raw_response_meta = {
            "status": result.status,
            "provider": job.provider,
            "provider_model_id": job.provider_model_id,
            "workflow_step": step.step_index,
            **_attempt_diagnostics(result.meta),
        }
        if result.status == "failed":
            if (
                self._is_retryable_provider_failure(result)
                and step.attempt_count < self._settings.veo_extended_step_max_attempts
            ):
                attempt.status = AttemptStatus.FAILED.value
                attempt.error_code = result.error_code
                attempt.error_message_safe = result.error_message_safe
                attempt.finished_at = now
                step.status = "pending"
                step.error_code = result.error_code
                step.updated_at = now
                return await self._start_extended_step(job, steps, step, now=now)
            return await self._fail_extended_step(job, step, result, now=now, attempt=attempt)
        if result.status == "accepted":
            step.status = "running"
            step.provider_job_id = result.provider_job_id
            step.updated_at = now
            job.provider_job_id = result.provider_job_id
            if GenerationStatus(job.status) is GenerationStatus.SUBMITTING:
                apply_transition(job, GenerationStatus.RUNNING, now=now)
            job.next_poll_at = now + self._poll_interval(job)
            await self._session.flush()
            return GenerationStatus.RUNNING
        return await self._complete_extended_step(job, steps, step, attempt, result, now=now)

    async def _poll_extended(
        self,
        job: GenerationJob,
        *,
        now: datetime,
        result_override: GenerationProviderResult | None = None,
    ) -> GenerationStatus:
        steps = await self._jobs.list_workflow_steps(job.id, for_update=True)
        active = next((step for step in steps if step.status == "running"), None)
        if active is None:
            pending = next((step for step in steps if step.status != "succeeded"), None)
            if pending is None:
                return await self._resume_extended_finalization(job, steps, now=now)
            return await self._start_extended_step(job, steps, pending, now=now)
        if job.cancel_requested_at is not None:
            if active.provider_job_id:
                await self._provider_for(job).cancel(active.provider_job_id)
            active.status = "cancelled"
            active.finished_at = now
            active.updated_at = now
            await self._cleanup_workflow_steps(steps)
            return await self._cancel_held(job, now=now)

        total_started = job.started_at or job.queued_at or job.created_at
        total_expired = now >= total_started + timedelta(
            seconds=self._settings.veo_extended_total_timeout_seconds
        )
        step_started = active.started_at or total_started
        step_expired = now >= step_started + timedelta(
            seconds=self._settings.veo_extended_step_timeout_seconds
        )
        if total_expired or step_expired:
            if active.provider_job_id:
                await self._provider_for(job).cancel(active.provider_job_id)
            timeout_result = GenerationProviderResult(
                status="failed",
                provider_job_id=active.provider_job_id,
                error_code="workflow_total_timeout" if total_expired else "workflow_step_timeout",
                error_message_safe="Extended video generation timed out",
            )
            if (
                not total_expired
                and active.attempt_count < self._settings.veo_extended_step_max_attempts
            ):
                active.status = "pending"
                active.provider_job_id = None
                active.error_code = timeout_result.error_code
                active.updated_at = now
                return await self._start_extended_step(job, steps, active, now=now)
            return await self._fail_extended_step(job, active, timeout_result, now=now)

        if result_override is not None:
            result = result_override
        elif active.provider_job_id:
            result = await self._provider_for(job).get_status(active.provider_job_id)
        else:
            result = GenerationProviderResult(
                status="failed",
                error_code="missing_provider_job_id",
                error_message_safe="Missing provider job id",
            )
        if result.status == "accepted":
            job.next_poll_at = now + self._poll_interval(job)
            await self._session.flush()
            return GenerationStatus.RUNNING

        job.attempt_count += 1
        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count,
            now=now,
        )
        attempt.provider_job_id = result.provider_job_id or active.provider_job_id
        attempt.latency_ms = result.latency_ms
        attempt.raw_response_meta = {
            "status": result.status,
            "provider": job.provider,
            "provider_model_id": job.provider_model_id,
            "workflow_step": active.step_index,
            **_attempt_diagnostics(result.meta),
        }
        if result.status == "failed":
            if (
                self._is_retryable_provider_failure(result)
                and active.attempt_count < self._settings.veo_extended_step_max_attempts
            ):
                attempt.status = AttemptStatus.FAILED.value
                attempt.error_code = result.error_code
                attempt.error_message_safe = result.error_message_safe
                attempt.finished_at = now
                active.status = "pending"
                active.provider_job_id = None
                active.error_code = result.error_code
                active.updated_at = now
                return await self._start_extended_step(job, steps, active, now=now)
            return await self._fail_extended_step(job, active, result, now=now, attempt=attempt)
        return await self._complete_extended_step(job, steps, active, attempt, result, now=now)

    async def _resume_extended_finalization(
        self,
        job: GenerationJob,
        steps: list[GenerationWorkflowStep],
        *,
        now: datetime,
    ) -> GenerationStatus:
        final_step = steps[-1]
        if not final_step.intermediate_object_key:
            return await self._fail_extended_step(
                job,
                final_step,
                GenerationProviderResult(
                    status="failed",
                    error_code="workflow_intermediate_missing",
                    error_message_safe="The final video step is unavailable",
                ),
                now=now,
            )
        try:
            data = await self._storage.get_object(object_key=final_step.intermediate_object_key)
        except Exception:
            logger.exception(
                "workflow_finalization_resume_failed",
                extra={"generation_id": str(job.id)},
            )
            return await self._fail_extended_step(
                job,
                final_step,
                GenerationProviderResult(
                    status="failed",
                    error_code="workflow_intermediate_missing",
                    error_message_safe="The final video step is unavailable",
                ),
                now=now,
            )
        job.attempt_count += 1
        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count,
            now=now,
        )
        result = GenerationProviderResult(
            status="succeeded",
            provider_job_id=final_step.provider_job_id,
            outputs=[GenerationOutput(content_type="video/mp4", data=data)],
            meta={"workflow_recovered": True},
        )
        status = await self._finalize_success(job, attempt, result, now=now)
        await self._cleanup_workflow_steps(steps)
        return status

    async def _complete_extended_step(
        self,
        job: GenerationJob,
        steps: list[GenerationWorkflowStep],
        step: GenerationWorkflowStep,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
    ) -> GenerationStatus:
        if len(result.outputs) != 1 or result.outputs[0].content_type != "video/mp4":
            return await self._fail_extended_step(
                job,
                step,
                replace(
                    result,
                    status="failed",
                    outputs=[],
                    error_code="workflow_invalid_output",
                    error_message_safe="Extended workflow returned an invalid video",
                ),
                now=now,
                attempt=attempt,
            )
        object_key = build_workflow_step_object_key(
            user_id=job.user_id,
            generation_id=job.id,
            step_index=step.step_index,
        )
        await self._store_output_bytes(
            object_key=object_key,
            data=result.outputs[0].data,
            content_type="video/mp4",
        )
        step.status = "succeeded"
        step.provider_job_id = result.provider_job_id or step.provider_job_id
        step.intermediate_object_key = object_key
        step.finished_at = now
        step.updated_at = now
        attempt.status = AttemptStatus.SUCCEEDED.value
        attempt.finished_at = now
        completed = step.step_index + 1
        total = len(steps)
        job.progress_pct = min(79, 10 + int(completed / total * 69))
        job.progress_stage = f"veo_extend_{completed}_of_{total}"
        if completed < total:
            job.provider_job_id = None
            return await self._start_extended_step(job, steps, steps[completed], now=now)

        final_status = await self._finalize_success(job, attempt, result, now=now)
        await self._cleanup_workflow_steps(steps)
        return final_status

    async def _fail_extended_step(
        self,
        job: GenerationJob,
        step: GenerationWorkflowStep,
        result: GenerationProviderResult,
        *,
        now: datetime,
        attempt: GenerationAttempt | None = None,
    ) -> GenerationStatus:
        if attempt is None:
            job.attempt_count += 1
            attempt = await self._jobs.add_attempt(
                generation_id=job.id,
                attempt_no=job.attempt_count,
                now=now,
            )
        step.status = "failed"
        step.error_code = result.error_code
        step.finished_at = now
        step.updated_at = now
        steps = await self._jobs.list_workflow_steps(job.id, for_update=True)
        status = await self._fail(job, attempt, result, now=now)
        await self._cleanup_workflow_steps(steps)
        return status

    async def _cleanup_workflow_steps(self, steps: list[GenerationWorkflowStep]) -> None:
        for step in steps:
            if not step.intermediate_object_key:
                continue
            try:
                await self._storage.delete_object(object_key=step.intermediate_object_key)
            except Exception:
                logger.warning(
                    "workflow_intermediate_cleanup_failed generation_id=%s step_index=%s",
                    step.generation_id,
                    step.step_index,
                )

    async def poll_due(self, *, now: datetime | None = None, limit: int = 20) -> list[str]:
        current = now or datetime.now(UTC)
        jobs = await self._jobs.list_due_for_poll(now=current, limit=limit)
        statuses: list[str] = []
        for job in jobs:
            status = await self.poll(job.id, now=current)
            statuses.append(status.value)
        return statuses

    async def _try_fallback(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
        input_keys: list[str] | None = None,
        input_urls: list[str] | None = None,
    ) -> GenerationStatus | None:
        if job.attempt_count >= job.max_attempts or not self._is_retryable_provider_failure(result):
            return None

        fallback = (job.routing_snapshot or {}).get("fallback")
        capabilities: dict[str, object] = {}
        if not isinstance(fallback, dict):
            # Compatibility for jobs created before immutable routing snapshots.
            model = await self._catalog.get_by_id(job.model_id)
            capabilities = dict(model.capabilities or {}) if model is not None else {}
            fallback = capabilities.get("fallback")
        if not isinstance(fallback, dict):
            return None

        fallback_provider = str(fallback.get("provider") or "").strip()
        fallback_model_id = str(fallback.get("provider_model_id") or "").strip()
        supported_modalities = fallback.get("supported_modalities")
        if (
            not fallback_provider
            or not fallback_model_id
            or fallback_provider == job.provider
            or (fallback_provider == "google" and not self._settings.google_api_key)
            or (isinstance(supported_modalities, list) and job.modality not in supported_modalities)
        ):
            return None

        if not await self._fallback_flags_enabled(job, fallback):
            return None

        fallback_cost = self._fallback_cost_units(job, fallback)
        ceiling = self._fallback_cost_ceiling(job, fallback, capabilities)
        if ceiling <= 0 or fallback_cost <= 0 or fallback_cost > ceiling:
            logger.warning(
                "generation_fallback_blocked_cost generation_id=%s from=%s to=%s",
                job.id,
                job.provider,
                fallback_provider,
            )
            return None

        if input_keys is None or input_urls is None:
            prepared = await self._prepare_input_materials(job, now=now)
            if prepared is None:
                return None
            input_keys, input_urls = prepared

        original_provider = job.provider
        original_model_id = job.provider_model_id
        attempt.status = AttemptStatus.FAILED.value
        attempt.error_code = result.error_code
        attempt.error_message_safe = result.error_message_safe
        attempt.finished_at = datetime.now(UTC)
        attempt.raw_response_meta = {
            "status": result.status,
            "provider": original_provider,
            "provider_model_id": original_model_id,
            "fallback_to": fallback_provider,
            **_attempt_diagnostics(result.meta),
        }
        await self._jobs.add_usage(
            generation_id=job.id,
            attempt_id=attempt.id,
            provider=original_provider,
            provider_model_id=original_model_id,
            modality=job.modality,
            provider_cost_units=result.provider_cost_units,
            user_credit_price=job.user_credit_price,
            latency_ms=result.latency_ms,
            meta={"status": "fallback", **_attempt_diagnostics(result.meta)},
            now=now,
        )
        _record_provider_route_metrics(job, result, outcome="failed")

        job.provider = fallback_provider
        job.provider_model_id = fallback_model_id
        job.provider_job_id = None
        job.error_code = None
        job.error_class = None
        job.next_poll_at = None
        job.progress_stage = "fallback"
        job.progress_pct = max(job.progress_pct, 35)

        job.attempt_count += 1
        fallback_attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count,
            now=now,
        )
        fallback_provider_adapter = self._provider_for(job)
        fallback_result = await fallback_provider_adapter.generate(
            GenerationRequest(
                generation_id=job.id,
                provider_model_id=job.provider_model_id,
                modality=job.modality,
                prompt=job.prompt or "",
                params=dict(job.params or {}),
                input_object_keys=input_keys,
                input_urls=input_urls,
            )
        )
        fallback_attempt.latency_ms = fallback_result.latency_ms
        fallback_attempt.provider_job_id = fallback_result.provider_job_id
        fallback_attempt.raw_response_meta = {
            "status": fallback_result.status,
            "provider": job.provider,
            "provider_model_id": job.provider_model_id,
            "fallback_from": original_provider,
            **_attempt_diagnostics(fallback_result.meta),
        }

        if fallback_result.status == "failed":
            _record_provider_failure_metrics(job, fallback_result)
            return await self._fail(
                job,
                fallback_attempt,
                fallback_result,
                now=now,
            )
        if fallback_result.status == "accepted":
            job.provider_job_id = fallback_result.provider_job_id
            apply_transition(
                job,
                GenerationStatus.RUNNING,
                now=now,
                progress_pct=max(job.progress_pct, 45),
                progress_stage="fallback_running",
            )
            job.next_poll_at = now + self._poll_interval(job)
            job.started_at = now
            await self._session.flush()
            logger.info(
                "generation_fallback_started generation_id=%s from=%s to=%s",
                job.id,
                original_provider,
                fallback_provider,
            )
            return GenerationStatus.RUNNING
        return await self._finalize_success(
            job,
            fallback_attempt,
            fallback_result,
            now=now,
        )

    async def _fallback_flags_enabled(
        self,
        job: GenerationJob,
        fallback: dict[str, object],
    ) -> bool:
        keys = [
            str(value)
            for value in (
                fallback.get("provider_feature_flag"),
                fallback.get("feature_flag"),
            )
            if isinstance(value, str) and value
        ]
        if not keys:
            return True
        user = await UserRepository(self._session).get_by_id(job.user_id)
        if user is None:
            return False
        flags = FeatureFlagService(self._session)
        for key in keys:
            if not await flags.is_enabled(key, telegram_id=user.telegram_id):
                return False
        return True

    @staticmethod
    def _fallback_cost_units(
        job: GenerationJob,
        fallback: dict[str, object],
    ) -> int:
        per_second = fallback.get("provider_cost_units_per_second")
        if isinstance(per_second, int) and per_second > 0:
            duration = int((job.params or {}).get("duration_sec") or 0)
            return per_second * duration
        by_resolution = fallback.get("provider_cost_units_by_resolution")
        if isinstance(by_resolution, dict):
            resolution = str((job.params or {}).get("resolution") or "1k").lower()
            value = by_resolution.get(resolution)
            if isinstance(value, int):
                return value
        value = fallback.get("provider_cost_units")
        return value if isinstance(value, int) else 0

    @staticmethod
    def _fallback_cost_ceiling(
        job: GenerationJob,
        fallback: dict[str, object],
        capabilities: dict[str, object],
    ) -> int:
        ceiling = fallback.get("provider_cost_ceiling_units")
        if isinstance(ceiling, int) and ceiling > 0:
            return ceiling
        ceiling_per_second = fallback.get("provider_cost_ceiling_units_per_second")
        if not isinstance(ceiling_per_second, int):
            ui = capabilities.get("ui")
            ui = ui if isinstance(ui, dict) else {}
            ceiling_per_second = ui.get("provider_cost_ceiling_units_per_second")
        if isinstance(ceiling_per_second, int) and ceiling_per_second > 0:
            duration = int((job.params or {}).get("duration_sec") or 0)
            return ceiling_per_second * duration
        ui = capabilities.get("ui")
        ui = ui if isinstance(ui, dict) else {}
        legacy = ui.get("provider_cost_ceiling_units")
        return legacy if isinstance(legacy, int) else 0

    async def _prepare_input_materials(
        self,
        job: GenerationJob,
        *,
        now: datetime,
    ) -> tuple[list[str], list[str]] | None:
        input_keys: list[str] = []
        input_urls: list[str] = []
        if not job.input_asset_ids:
            return input_keys, input_urls
        assets = AssetRepository(self._session)
        for asset_id in job.input_asset_ids:
            asset = await assets.get_by_id(asset_id)
            if (
                asset is None
                or asset.user_id != job.user_id
                or asset.role not in {AssetRole.INPUT.value, AssetRole.OUTPUT.value}
                or asset.status != AssetStatus.READY.value
                or asset.deleted_at is not None
                or (asset.expires_at is not None and asset.expires_at <= now)
            ):
                return None
            input_keys.append(asset.object_key)
            signed = await self._storage.create_presigned_get(
                object_key=asset.object_key,
                content_type=asset.content_type,
                download_name=f"reference-{asset.id}",
                expires_in=self._settings.s3_presign_ttl_seconds,
            )
            input_urls.append(signed.url)
        return input_keys, input_urls

    @staticmethod
    def _is_retryable_provider_failure(result: GenerationProviderResult) -> bool:
        if result.error_code in {"provider_timeout", "provider_unavailable", "rate_limited"}:
            return True
        if result.error_code != "provider_http_error":
            return False
        status = result.meta.get("http_status")
        return status is None or status == 429 or (isinstance(status, int) and status >= 500)

    async def _expected_provider_cost_units(self, job: GenerationJob) -> int:
        routing = dict(job.routing_snapshot or {})
        primary = routing.get("primary")
        primary = primary if isinstance(primary, dict) else {}
        if primary.get("provider") == job.provider:
            value = primary.get("provider_cost_units")
            return value if isinstance(value, int) else 0
        fallback = routing.get("fallback")
        if isinstance(fallback, dict) and fallback.get("provider") == job.provider:
            return self._fallback_cost_units(job, fallback)

        # Compatibility for legacy jobs without a routing snapshot.
        model = await self._catalog.get_by_id(job.model_id)
        if model is None:
            return 0
        capabilities = dict(model.capabilities or {})
        if job.provider != model.provider:
            legacy_fallback = capabilities.get("fallback")
            if (
                isinstance(legacy_fallback, dict)
                and legacy_fallback.get("provider") == job.provider
            ):
                return self._fallback_cost_units(job, legacy_fallback)
            return 0
        return compute_user_credit_price(
            model.provider_cost_units,
            params=dict(job.params or {}),
            pricing_rules=dict(model.pricing_rules or {}),
        )

    async def _cancel_held(self, job: GenerationJob, *, now: datetime) -> GenerationStatus:
        apply_transition(
            job,
            GenerationStatus.CANCELLED,
            now=now,
            error_code="cancelled_by_user",
            error_class="user",
        )
        if job.reservation_id is not None:
            await self._wallet.release(job.reservation_id, now=now)
        job.next_poll_at = None
        await self._session.flush()
        _record_terminal_metrics(job, GenerationStatus.CANCELLED, now=now)
        return GenerationStatus.CANCELLED

    async def _fail_running(
        self,
        job: GenerationJob,
        result: GenerationProviderResult,
        *,
        now: datetime,
    ) -> GenerationStatus:
        attempt = await self._jobs.add_attempt(
            generation_id=job.id,
            attempt_no=job.attempt_count + 1,
            now=now,
        )
        job.attempt_count += 1
        _record_provider_failure_metrics(job, result)
        return await self._fail(job, attempt, result, now=now)

    async def _fail(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
        error_class: str = "provider",
    ) -> GenerationStatus:
        attempt.status = AttemptStatus.FAILED.value
        attempt.error_code = result.error_code
        attempt.error_message_safe = result.error_message_safe
        attempt.finished_at = datetime.now(UTC)
        apply_transition(
            job,
            GenerationStatus.FAILED,
            now=now,
            error_code=result.error_code or "provider_failed",
            error_class=error_class,
            progress_stage="failed",
        )
        if job.reservation_id is not None:
            await self._wallet.release(job.reservation_id, now=now)
        job.next_poll_at = None
        await self._jobs.add_usage(
            generation_id=job.id,
            attempt_id=attempt.id,
            provider=job.provider,
            provider_model_id=job.provider_model_id,
            modality=job.modality,
            provider_cost_units=(
                result.provider_cost_units or await self._expected_provider_cost_units(job)
            ),
            user_credit_price=job.user_credit_price,
            latency_ms=result.latency_ms,
            meta={"status": "failed", **_attempt_diagnostics(result.meta)},
            tokens_in=_token(result.meta, "tokens_in"),
            tokens_out=_token(result.meta, "tokens_out"),
            now=now,
        )
        _record_provider_route_metrics(job, result, outcome="failed")
        await self._session.flush()
        _record_terminal_metrics(job, GenerationStatus.FAILED, now=now)
        return GenerationStatus.FAILED

    async def _finalize_success(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
    ) -> GenerationStatus:
        compositor = job.template_snapshot.get("compositor")
        if self._settings.template_compositor_enabled and isinstance(compositor, str):
            try:
                composed_outputs = [
                    await self._template_compositor.compose(
                        output,
                        compositor=compositor,
                        inputs=dict(job.template_inputs or {}),
                        aspect_ratio=str(job.template_snapshot.get("aspect_ratio") or "9:16"),
                    )
                    for output in result.outputs
                ]
                result = replace(result, outputs=composed_outputs)
            except TemplateCompositorError:
                logger.exception(
                    "template_compositor_failed",
                    extra={"generation_id": str(job.id), "template": job.template_slug},
                )
                failed = replace(
                    result,
                    status="failed",
                    outputs=[],
                    error_code="template_compositor_failed",
                    error_message_safe="Template output could not be finalized",
                )
                return await self._fail(
                    job,
                    attempt,
                    failed,
                    now=now,
                    error_class="template",
                )
        apply_transition(
            job,
            GenerationStatus.FINALIZING,
            now=now,
            progress_pct=80,
            progress_stage="finalizing",
        )
        if result.provider_job_id:
            job.provider_job_id = result.provider_job_id
        await self._session.flush()

        for output in result.outputs:
            asset_id = uuid4()
            dimensions = image_dimensions(output.content_type, output.data)
            object_key = build_output_object_key(
                user_id=job.user_id,
                asset_id=asset_id,
                content_type=output.content_type,
            )
            await self._store_output_bytes(
                object_key=object_key,
                data=output.data,
                content_type=output.content_type,
            )
            self._session.add(
                GenerationAsset(
                    id=asset_id,
                    generation_id=job.id,
                    user_id=job.user_id,
                    role=AssetRole.OUTPUT.value,
                    status=AssetStatus.READY.value,
                    storage_backend=self._storage.backend_name,
                    bucket=self._storage.bucket,
                    object_key=object_key,
                    content_type=output.content_type,
                    byte_size=len(output.data),
                    declared_byte_size=len(output.data),
                    magic_ok=True,
                    visibility="private",
                    retention_class=RetentionClass.PERMANENT_OUTPUT.value,
                    width=dimensions[0] if dimensions is not None else None,
                    height=dimensions[1] if dimensions is not None else None,
                )
            )

        attempt.status = AttemptStatus.SUCCEEDED.value
        attempt.finished_at = datetime.now(UTC)
        await self._jobs.add_usage(
            generation_id=job.id,
            attempt_id=attempt.id,
            provider=job.provider,
            provider_model_id=job.provider_model_id,
            modality=job.modality,
            provider_cost_units=(
                result.provider_cost_units or await self._expected_provider_cost_units(job)
            ),
            user_credit_price=job.user_credit_price,
            latency_ms=result.latency_ms,
            meta={"status": "succeeded", **_attempt_diagnostics(result.meta)},
            tokens_in=_token(result.meta, "tokens_in"),
            tokens_out=_token(result.meta, "tokens_out"),
            now=now,
        )
        _record_provider_route_metrics(job, result, outcome="succeeded")
        if job.reservation_id is not None:
            await self._wallet.capture(
                job.reservation_id,
                meta={"generation_id": str(job.id)},
                now=now,
            )
        apply_transition(
            job,
            GenerationStatus.SUCCEEDED,
            now=now,
            progress_pct=100,
            progress_stage="done",
        )
        job.next_poll_at = None
        await self._notifications.enqueue_generation_ready(
            user_id=job.user_id,
            generation_id=job.id,
            now=now,
        )
        await self._session.flush()
        _record_terminal_metrics(job, GenerationStatus.SUCCEEDED, now=now)
        return GenerationStatus.SUCCEEDED
