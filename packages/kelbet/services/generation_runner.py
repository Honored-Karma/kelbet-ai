"""Process generation jobs: sync finalize or async accept → poll → capture/release."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.pricing import compute_user_credit_price
from kelbet.config import Settings, get_settings
from kelbet.db.models.asset import GenerationAsset
from kelbet.db.models.generation import GenerationAttempt, GenerationJob
from kelbet.domain.enums import (
    AssetRole,
    AssetStatus,
    AttemptStatus,
    GenerationStatus,
    RetentionClass,
)
from kelbet.domain.exceptions import GenerationNotFoundError
from kelbet.providers.base import GenerationProvider, GenerationProviderResult, GenerationRequest
from kelbet.providers.factory import resolve_provider
from kelbet.repositories.asset import AssetRepository
from kelbet.repositories.catalog import CatalogRepository
from kelbet.repositories.generation import GenerationRepository
from kelbet.repositories.notification import NotificationRepository
from kelbet.services.generation_sm import apply_transition
from kelbet.services.wallet import WalletService
from kelbet.storage import ObjectStorage, build_output_object_key, image_dimensions
from kelbet.storage.memory import MemoryObjectStorage
from kelbet.storage.s3 import S3ObjectStorage

logger = logging.getLogger(__name__)


def _token(meta: dict[str, object] | None, key: str) -> int | None:
    if not meta:
        return None
    value = meta.get(key)
    return value if isinstance(value, int) else None


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
        }

        if result.status == "failed":
            fallback_status = await self._try_video_fallback(
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
        }

        if result.status == "failed":
            fallback_status = await self._try_video_fallback(
                job,
                attempt,
                result,
                now=current,
            )
            if fallback_status is not None:
                return fallback_status
            return await self._fail(job, attempt, result, now=current)

        return await self._finalize_success(job, attempt, result, now=current)

    async def poll_due(self, *, now: datetime | None = None, limit: int = 20) -> list[str]:
        current = now or datetime.now(UTC)
        jobs = await self._jobs.list_due_for_poll(now=current, limit=limit)
        statuses: list[str] = []
        for job in jobs:
            status = await self.poll(job.id, now=current)
            statuses.append(status.value)
        return statuses

    async def _try_video_fallback(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
        input_keys: list[str] | None = None,
        input_urls: list[str] | None = None,
    ) -> GenerationStatus | None:
        if (
            job.modality != "video"
            or job.attempt_count >= job.max_attempts
            or not self._is_retryable_provider_failure(result)
        ):
            return None

        model = await self._catalog.get_by_id(job.model_id)
        capabilities = dict(model.capabilities or {}) if model is not None else {}
        fallback = capabilities.get("fallback")
        if not isinstance(fallback, dict):
            return None

        fallback_provider = str(fallback.get("provider") or "").strip()
        fallback_model_id = str(fallback.get("provider_model_id") or "").strip()
        if (
            not fallback_provider
            or not fallback_model_id
            or fallback_provider == job.provider
            or (fallback_provider == "google" and not self._settings.google_api_key)
        ):
            return None

        ui = capabilities.get("ui")
        ui = ui if isinstance(ui, dict) else {}
        ceiling_per_second = int(ui.get("provider_cost_ceiling_units_per_second") or 0)
        fallback_per_second = int(fallback.get("provider_cost_units_per_second") or 0)
        if (
            ceiling_per_second <= 0
            or fallback_per_second <= 0
            or fallback_per_second > ceiling_per_second
        ):
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
            meta={"status": "fallback", **(result.meta or {})},
            now=now,
        )

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
        }

        if fallback_result.status == "failed":
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
        model = await self._catalog.get_by_id(job.model_id)
        if model is None:
            return 0
        capabilities = dict(model.capabilities or {})
        duration = int((job.params or {}).get("duration_sec") or 0)
        if job.provider != model.provider:
            fallback = capabilities.get("fallback")
            if isinstance(fallback, dict) and fallback.get("provider") == job.provider:
                per_second = int(fallback.get("provider_cost_units_per_second") or 0)
                return per_second * duration
            return 0
        if model.provider_cost_units <= 0:
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
        return await self._fail(job, attempt, result, now=now)

    async def _fail(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
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
            error_class="provider",
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
            meta={"status": "failed", **(result.meta or {})},
            tokens_in=_token(result.meta, "tokens_in"),
            tokens_out=_token(result.meta, "tokens_out"),
            now=now,
        )
        await self._session.flush()
        return GenerationStatus.FAILED

    async def _finalize_success(
        self,
        job: GenerationJob,
        attempt: GenerationAttempt,
        result: GenerationProviderResult,
        *,
        now: datetime,
    ) -> GenerationStatus:
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
            meta={"status": "succeeded", **(result.meta or {})},
            tokens_in=_token(result.meta, "tokens_in"),
            tokens_out=_token(result.meta, "tokens_out"),
            now=now,
        )
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
        return GenerationStatus.SUCCEEDED
