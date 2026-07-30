"""Create / cancel / read generation jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models.asset import GenerationAsset
from kelbet.db.models.catalog import CatalogModel
from kelbet.db.models.credit_reservation import CreditReservation
from kelbet.db.models.generation import GenerationJob
from kelbet.domain.enums import AssetRole, AssetStatus, GenerationStatus
from kelbet.domain.exceptions import (
    ActiveGenerationLimitError,
    AssetNotFoundError,
    GenerationConflictError,
    GenerationNotFoundError,
    QuoteNotFoundError,
    UploadValidationError,
    WalletNotFoundError,
)
from kelbet.queue import GenerationQueue
from kelbet.repositories.asset import AssetRepository
from kelbet.repositories.catalog import CatalogRepository
from kelbet.repositories.generation import GenerationRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.catalog import FeatureFlagService, QuoteService
from kelbet.services.generation_sm import apply_transition
from kelbet.services.wallet import WalletService


@dataclass(frozen=True, slots=True)
class GenerationDTO:
    id: UUID
    status: GenerationStatus
    modality: str
    model_slug: str | None
    user_credit_price: int
    progress_pct: int
    progress_stage: str | None
    error_code: str | None
    cancelable: bool
    reservation_id: UUID | None
    created_at: datetime
    output_asset_ids: list[UUID]
    preview_asset_id: UUID | None = None
    preview_content_type: str | None = None
    eta_seconds: int | None = None
    estimated_remaining_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class GenerationDraftDTO:
    source_generation_id: UUID
    mode: Literal["repeat", "remix", "upscale"]
    model_slug: str | None
    modality: str
    prompt: str
    params: dict[str, Any]
    input_asset_ids: list[UUID]
    unavailable_asset_ids: list[UUID]
    missing_input_assets: int
    model_available: bool
    replacement_slug: str | None


def _request_hash(
    *,
    model_slug: str,
    params: dict[str, Any],
    input_asset_ids: list[UUID],
    prompt: str,
) -> str:
    canonical = {
        "model_slug": model_slug,
        "params": params,
        "input_asset_ids": [str(x) for x in input_asset_ids],
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_len": len(prompt),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class GenerationService:
    def __init__(
        self,
        session: AsyncSession,
        queue: GenerationQueue,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._queue = queue
        self._settings = settings or get_settings()
        self._jobs = GenerationRepository(session)
        self._assets = AssetRepository(session)
        self._catalog = CatalogRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet_svc = WalletService(session)
        self._quotes = QuoteService(session, self._settings)

    async def create(
        self,
        *,
        user_id: UUID,
        telegram_id: int,
        idempotency_key: str,
        quote_id: UUID,
        prompt: str,
        input_asset_ids: list[UUID] | None = None,
        correlation_id: UUID | None = None,
        now: datetime | None = None,
    ) -> GenerationDTO:
        current = now or datetime.now(UTC)
        existing = await self._jobs.get_by_idempotency(
            user_id=user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return await self._to_dto(existing)

        active = await self._jobs.count_active_for_user(user_id)
        if active >= self._settings.max_active_generations_per_user:
            raise ActiveGenerationLimitError(
                f"User {user_id} has {active} active generations "
                f"(limit {self._settings.max_active_generations_per_user})"
            )

        quote = await self._quotes.get_valid_quote(quote_id, user_id=user_id, now=current)
        model = await self._catalog.get_by_slug(quote.model_slug)
        if model is None:
            raise QuoteNotFoundError(f"Model for quote {quote_id} missing")
        if model.modality == "video":
            active_video = await self._jobs.count_active_for_user(
                user_id,
                modality="video",
            )
            if active_video >= self._settings.max_active_video_generations_per_user:
                raise ActiveGenerationLimitError(
                    f"User {user_id} has {active_video} active video generations "
                    f"(limit {self._settings.max_active_video_generations_per_user})"
                )

        text = prompt.strip()
        requirements = model.input_requirements or {}
        prompt_requirement = str(requirements.get("prompt") or "required")
        if prompt_requirement == "required" and not text:
            raise UploadValidationError("prompt is required")
        if prompt_requirement == "forbidden" and text:
            raise UploadValidationError("This model does not accept a prompt")

        asset_ids = input_asset_ids or []
        if len(asset_ids) != len(set(asset_ids)):
            raise UploadValidationError("Duplicate input assets are not allowed")

        source_image = str(requirements.get("source_image") or "forbidden")
        max_input_assets = int(
            requirements.get("max_input_assets")
            or (1 if source_image in {"optional", "required"} else 0)
        )
        if source_image == "required" and not asset_ids:
            raise UploadValidationError("A source image is required for this model")
        if source_image == "forbidden" and asset_ids:
            raise UploadValidationError("This model does not accept source images")
        if len(asset_ids) > max_input_assets:
            raise UploadValidationError(
                f"This model accepts at most {max_input_assets} source image(s)"
            )

        max_prompt_chars = int((model.capabilities or {}).get("max_prompt_chars") or 8000)
        if len(text) > max_prompt_chars:
            raise UploadValidationError(
                f"Prompt exceeds the model limit of {max_prompt_chars} characters"
            )

        accepted_mime = {str(value) for value in requirements.get("accepted_mime", [])}
        max_input_bytes = int(requirements.get("max_input_bytes") or 0)
        max_input_width = int(requirements.get("max_input_width") or 0)
        max_input_height = int(requirements.get("max_input_height") or 0)
        require_known_dimensions = bool(requirements.get("require_known_dimensions"))
        for asset_id in asset_ids:
            asset = await self._assets.get_by_id(asset_id)
            if asset is None or asset.user_id != user_id:
                raise AssetNotFoundError(f"Asset {asset_id} not found")
            if (
                asset.status != AssetStatus.READY.value
                or asset.deleted_at is not None
                or (asset.expires_at is not None and asset.expires_at <= current)
            ):
                raise UploadValidationError(f"Asset {asset_id} is not ready")
            if asset.role not in {AssetRole.INPUT.value, AssetRole.OUTPUT.value}:
                raise UploadValidationError(f"Asset {asset_id} cannot be used as a reference")
            if accepted_mime and asset.content_type not in accepted_mime:
                raise UploadValidationError(f"Asset {asset_id} has unsupported content type")
            if max_input_bytes and asset.byte_size > max_input_bytes:
                raise UploadValidationError(f"Asset {asset_id} exceeds the size limit")
            if require_known_dimensions and (asset.width is None or asset.height is None):
                raise UploadValidationError(f"Asset {asset_id} dimensions could not be verified")
            if max_input_width and asset.width is not None and asset.width > max_input_width:
                raise UploadValidationError(
                    f"Asset {asset_id} exceeds the maximum width of {max_input_width}px"
                )
            if max_input_height and asset.height is not None and asset.height > max_input_height:
                raise UploadValidationError(
                    f"Asset {asset_id} exceeds the maximum height of {max_input_height}px"
                )

        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {user_id} not found")

        req_hash = _request_hash(
            model_slug=model.slug,
            params=quote.params,
            input_asset_ids=asset_ids,
            prompt=text,
        )
        job = await self._jobs.create(
            user_id=user_id,
            model_id=model.id,
            modality=model.modality,
            status=GenerationStatus.CREATED.value,
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            prompt_redacted=True,
            params=quote.params,
            input_asset_ids=asset_ids or None,
            quote_id=quote.quote_id,
            user_credit_price=quote.user_credit_price,
            provider=model.provider,
            provider_model_id=model.provider_model_id,
            progress_pct=0,
            progress_stage="created",
            attempt_count=0,
            max_attempts=3,
            correlation_id=correlation_id or uuid4(),
            prompt=text,
        )

        reservation = await self._wallet_svc.reserve(
            wallet.id,
            quote.user_credit_price,
            f"reserve:gen:{job.id}",
            user_id=user_id,
            quote_snapshot={
                "quote_id": str(quote.quote_id),
                "model_slug": model.slug,
                "user_credit_price": quote.user_credit_price,
                "params": quote.params,
            },
            now=current,
        )
        job.reservation_id = reservation.reservation_id
        res_row = await self._session.execute(
            select(CreditReservation)
            .where(CreditReservation.id == reservation.reservation_id)
            .with_for_update()
        )
        cred = res_row.scalar_one()
        cred.generation_id = job.id
        await self._session.flush()

        apply_transition(job, GenerationStatus.QUEUED, now=current, progress_stage="queued")
        await self._session.flush()
        await self._queue.enqueue(job.id, modality=model.modality)
        return await self._to_dto(job, model_slug=model.slug)

    async def get(self, *, user_id: UUID, generation_id: UUID) -> GenerationDTO:
        job = await self._jobs.get_by_id(generation_id)
        if job is None or job.user_id != user_id:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")
        return await self._to_dto(job)

    async def get_draft(
        self,
        *,
        user_id: UUID,
        telegram_id: int,
        generation_id: UUID,
        mode: Literal["repeat", "remix", "upscale"] = "repeat",
        now: datetime | None = None,
    ) -> GenerationDraftDTO:
        current = now or datetime.now(UTC)
        job = await self._jobs.get_by_id(generation_id)
        if job is None or job.user_id != user_id:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")

        model = await self._catalog.get_by_id(job.model_id)
        model_available = bool(model is not None and model.enabled and model.deprecated_at is None)
        if model_available and model is not None and model.feature_flag:
            model_available = await FeatureFlagService(self._session).is_enabled(
                model.feature_flag,
                telegram_id=telegram_id,
            )

        candidate_asset_ids: list[UUID]
        if mode in {"remix", "upscale"}:
            outputs = await self._session.execute(
                select(GenerationAsset.id)
                .where(
                    GenerationAsset.generation_id == job.id,
                    GenerationAsset.role == AssetRole.OUTPUT.value,
                )
                .order_by(GenerationAsset.created_at, GenerationAsset.id)
            )
            candidate_asset_ids = list(outputs.scalars().all())
        else:
            candidate_asset_ids = list(job.input_asset_ids or [])

        valid_input_ids: list[UUID] = []
        unavailable_asset_ids: list[UUID] = []
        for asset_id in candidate_asset_ids:
            asset = await self._assets.get_by_id(asset_id)
            if (
                asset is None
                or asset.user_id != user_id
                or asset.role not in {AssetRole.INPUT.value, AssetRole.OUTPUT.value}
                or asset.status != AssetStatus.READY.value
                or asset.deleted_at is not None
                or (asset.expires_at is not None and asset.expires_at <= current)
            ):
                unavailable_asset_ids.append(asset_id)
                continue
            valid_input_ids.append(asset.id)
            if mode in {"remix", "upscale"}:
                break

        missing_input_assets = len(unavailable_asset_ids)
        if mode in {"remix", "upscale"} and not valid_input_ids:
            missing_input_assets = max(1, missing_input_assets)

        return GenerationDraftDTO(
            source_generation_id=job.id,
            mode=mode,
            model_slug=model.slug if model is not None else None,
            modality=job.modality,
            prompt=job.prompt or "",
            params=dict(job.params or {}),
            input_asset_ids=valid_input_ids,
            unavailable_asset_ids=unavailable_asset_ids,
            missing_input_assets=missing_input_assets,
            model_available=model_available,
            replacement_slug=model.replacement_slug if model is not None else None,
        )

    async def list_history(
        self, *, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[GenerationDTO]:
        current = datetime.now(UTC)
        result = await self._session.execute(
            select(GenerationJob, CatalogModel.slug)
            .join(CatalogModel, CatalogModel.id == GenerationJob.model_id)
            .where(GenerationJob.user_id == user_id)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        job_rows = list(result.all())
        if not job_rows:
            return []

        generation_ids = [job.id for job, _ in job_rows]
        asset_result = await self._session.execute(
            select(GenerationAsset)
            .where(
                GenerationAsset.generation_id.in_(generation_ids),
                GenerationAsset.user_id == user_id,
                GenerationAsset.role.in_([AssetRole.THUMB.value, AssetRole.OUTPUT.value]),
                GenerationAsset.status == AssetStatus.READY.value,
                GenerationAsset.deleted_at.is_(None),
                or_(
                    GenerationAsset.expires_at.is_(None),
                    GenerationAsset.expires_at > current,
                ),
            )
            .order_by(
                GenerationAsset.generation_id,
                GenerationAsset.created_at,
                GenerationAsset.id,
            )
        )
        output_ids: dict[UUID, list[UUID]] = {}
        previews: dict[UUID, GenerationAsset] = {}
        for asset in asset_result.scalars().all():
            if asset.generation_id is None:
                continue
            if asset.role == AssetRole.OUTPUT.value:
                output_ids.setdefault(asset.generation_id, []).append(asset.id)
                previews.setdefault(asset.generation_id, asset)
            elif asset.role == AssetRole.THUMB.value:
                previews[asset.generation_id] = asset

        items: list[GenerationDTO] = []
        for job, slug in job_rows:
            status = GenerationStatus(job.status)
            cancelable = (
                status
                in {
                    GenerationStatus.CREATED,
                    GenerationStatus.QUEUED,
                    GenerationStatus.SUBMITTING,
                    GenerationStatus.RUNNING,
                }
                and job.cancel_requested_at is None
            )
            preview = previews.get(job.id)
            items.append(
                GenerationDTO(
                    id=job.id,
                    status=status,
                    modality=job.modality,
                    model_slug=slug,
                    user_credit_price=job.user_credit_price,
                    progress_pct=job.progress_pct,
                    progress_stage=job.progress_stage,
                    error_code=job.error_code,
                    cancelable=cancelable,
                    reservation_id=job.reservation_id,
                    created_at=job.created_at,
                    output_asset_ids=output_ids.get(job.id, []),
                    preview_asset_id=preview.id if preview is not None else None,
                    preview_content_type=(preview.content_type if preview is not None else None),
                )
            )
        return items

    async def cancel(
        self, *, user_id: UUID, generation_id: UUID, now: datetime | None = None
    ) -> GenerationDTO:
        current = now or datetime.now(UTC)
        job = await self._jobs.get_by_id_for_update(generation_id)
        if job is None or job.user_id != user_id:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")

        status = GenerationStatus(job.status)
        if status in {
            GenerationStatus.SUCCEEDED,
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
            GenerationStatus.TIMED_OUT,
            GenerationStatus.DEAD_LETTER,
        }:
            raise GenerationConflictError(f"Generation {generation_id} already terminal")

        job.cancel_requested_at = current
        if status in {GenerationStatus.CREATED, GenerationStatus.QUEUED}:
            apply_transition(
                job,
                GenerationStatus.CANCELLED,
                now=current,
                progress_stage="cancelled",
                error_code="cancelled_by_user",
                error_class="user",
            )
            if job.reservation_id is not None:
                await self._wallet_svc.release(job.reservation_id, now=current)
        await self._session.flush()
        if status in {GenerationStatus.SUBMITTING, GenerationStatus.RUNNING}:
            await self._queue.enqueue(job.id, modality=job.modality)
        return await self._to_dto(job)

    async def _to_dto(self, job: GenerationJob, *, model_slug: str | None = None) -> GenerationDTO:
        model = await self._catalog.get_by_id(job.model_id)
        slug = model_slug or (model.slug if model is not None else None)
        eta_seconds: int | None = None
        estimated_remaining_seconds: int | None = None
        if model is not None:
            ui = (model.capabilities or {}).get("ui")
            ui = ui if isinstance(ui, dict) else {}
            raw_eta = ui.get("eta_seconds")
            if isinstance(raw_eta, int) and raw_eta > 0:
                eta_seconds = raw_eta
                status_for_eta = GenerationStatus(job.status)
                if status_for_eta in {
                    GenerationStatus.SUCCEEDED,
                    GenerationStatus.FAILED,
                    GenerationStatus.CANCELLED,
                    GenerationStatus.TIMED_OUT,
                    GenerationStatus.DEAD_LETTER,
                }:
                    estimated_remaining_seconds = 0
                elif job.started_at is None:
                    estimated_remaining_seconds = eta_seconds
                else:
                    elapsed = max(
                        0,
                        int((datetime.now(UTC) - job.started_at).total_seconds()),
                    )
                    if elapsed <= eta_seconds:
                        estimated_remaining_seconds = eta_seconds - elapsed
        assets = await self._session.execute(
            select(GenerationAsset.id).where(
                GenerationAsset.generation_id == job.id,
                GenerationAsset.role == "output",
                GenerationAsset.status == AssetStatus.READY.value,
            )
        )
        output_ids = list(assets.scalars().all())
        status = GenerationStatus(job.status)
        cancelable = (
            status
            in {
                GenerationStatus.CREATED,
                GenerationStatus.QUEUED,
                GenerationStatus.SUBMITTING,
                GenerationStatus.RUNNING,
            }
            and job.cancel_requested_at is None
        )
        return GenerationDTO(
            id=job.id,
            status=status,
            modality=job.modality,
            model_slug=slug,
            user_credit_price=job.user_credit_price,
            progress_pct=job.progress_pct,
            progress_stage=job.progress_stage,
            error_code=job.error_code,
            cancelable=cancelable,
            reservation_id=job.reservation_id,
            created_at=job.created_at,
            output_asset_ids=output_ids,
            eta_seconds=eta_seconds,
            estimated_remaining_seconds=estimated_remaining_seconds,
        )
