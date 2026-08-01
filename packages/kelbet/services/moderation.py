from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models import ModerationDecision, UserConsent
from kelbet.domain.enums import ModerationMode, ModerationOutcome
from kelbet.domain.exceptions import (
    ConsentRequiredError,
    IdempotencyConflictError,
    ModerationRateLimitError,
    ModerationRejectedError,
)
from kelbet.moderation import (
    ModerationProvider,
    ModerationProviderError,
    OpenAIModerationProvider,
    RulesModerationProvider,
)
from kelbet.observability import get_metrics
from kelbet.repositories.moderation import ModerationRepository

ModerationContext = Literal["generation", "chat", "prompt_assistant"]


@dataclass(frozen=True, slots=True)
class ModerationDecisionDTO:
    id: UUID
    outcome: ModerationOutcome
    reason_codes: tuple[str, ...]
    policy_version: str
    provider: str
    replayed: bool


def _input_hash(*, text: str, asset_ids: list[UUID], context: str, policy_version: str) -> str:
    payload = json.dumps(
        {
            "text": text,
            "asset_ids": sorted(str(item) for item in asset_ids),
            "context": context,
            "policy_version": policy_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _consent_hash(asset_ids: list[UUID], version: str) -> str:
    value = ":".join([version, *(sorted(str(item) for item in asset_ids))])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ModerationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        external_provider: ModerationProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._repo = ModerationRepository(session)
        self._rules = RulesModerationProvider()
        self._external = external_provider or self._build_external_provider()

    def _build_external_provider(self) -> ModerationProvider | None:
        if self._settings.moderation_external_provider != "openai":
            return None
        return OpenAIModerationProvider(
            api_key=self._settings.openai_moderation_api_key,
            base_url=self._settings.openai_moderation_base_url,
            model=self._settings.openai_moderation_model,
            timeout_seconds=self._settings.openai_moderation_timeout_seconds,
        )

    async def evaluate_text(
        self,
        *,
        user_id: UUID,
        text: str,
        context: ModerationContext,
        idempotency_key: str,
        language: str,
        asset_ids: list[UUID] | None = None,
        now: datetime | None = None,
    ) -> tuple[ModerationDecisionDTO, ModerationDecision]:
        current = now or datetime.now(UTC)
        assets = asset_ids or []
        digest = _input_hash(
            text=text,
            asset_ids=assets,
            context=context,
            policy_version=self._settings.moderation_policy_version,
        )
        existing = await self._repo.get_decision(
            user_id=user_id, context=context, idempotency_key=idempotency_key
        )
        if existing is not None:
            if existing.input_hash != digest:
                raise IdempotencyConflictError("Moderation idempotency payload changed")
            dto = self._dto(existing, replayed=True)
            self._raise_if_blocked(dto, language=language)
            return dto, existing

        mode = ModerationMode(self._settings.moderation_mode)
        reasons: set[str] = set()
        provider = "off" if mode is ModerationMode.OFF else "rules"
        provider_model: str | None = None
        provider_request_id: str | None = None
        error_code: str | None = None
        rate_limited = False
        content_violation = False

        if mode is not ModerationMode.OFF:
            recent_requests = await self._repo.count_recent_requests(
                user_id, since=current - timedelta(minutes=1)
            )
            if recent_requests >= self._settings.moderation_max_requests_per_minute:
                reasons.add("moderation_rate_limit")
                rate_limited = True

            rules = await self._rules.moderate_text(text)
            reasons.update(rules.categories)
            content_violation = bool(rules.categories)
            provider_model = rules.model

            if self._external is not None:
                try:
                    external = await self._external.moderate_text(text)
                    provider = external.provider
                    provider_model = external.model
                    provider_request_id = external.request_id
                    reasons.update(external.categories)
                    if external.flagged and not external.categories:
                        reasons.add("external_flagged")
                    content_violation = content_violation or external.flagged
                except ModerationProviderError as exc:
                    error_code = exc.code
                    reasons.add("provider_unavailable")

            prior_violations = await self._repo.count_recent_violations(
                user_id,
                hours=self._settings.moderation_violation_window_hours,
                now=current,
            )
            if (
                content_violation
                and prior_violations >= self._settings.moderation_repeat_violation_threshold
            ):
                reasons.add("repeat_violation")

        if mode is ModerationMode.OFF or not reasons:
            outcome = ModerationOutcome.ALLOW
        elif rate_limited:
            outcome = ModerationOutcome.BLOCK
        elif mode is ModerationMode.REPORT or (
            error_code is not None
            and not content_violation
            and self._settings.moderation_external_failure_policy == "open"
        ):
            outcome = ModerationOutcome.REPORT
        else:
            outcome = ModerationOutcome.BLOCK

        decision = await self._repo.create_decision(
            user_id=user_id,
            generation_id=None,
            asset_ids=assets,
            context=context,
            idempotency_key=idempotency_key,
            input_hash=digest,
            mode=mode.value,
            outcome=outcome.value,
            reason_codes=sorted(reasons),
            policy_version=self._settings.moderation_policy_version,
            provider=provider,
            provider_model=provider_model,
            provider_request_id=provider_request_id,
            error_code=error_code,
            review_status="open",
        )
        get_metrics().incr(
            "moderation.decision",
            tags={"outcome": outcome.value, "context": context, "provider": provider},
        )
        dto = self._dto(decision, replayed=False)
        if rate_limited:
            raise ModerationRateLimitError(language=language, reason_codes=dto.reason_codes)
        self._raise_if_blocked(dto, language=language)
        return dto, decision

    async def require_photo_rights(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        asset_ids: list[UUID],
        confirmed: bool,
        version: str | None,
        language: str,
        now: datetime | None = None,
    ) -> UserConsent:
        current = now or datetime.now(UTC)
        required_version = self._settings.photo_rights_consent_version
        existing = await self._repo.get_consent(
            user_id=user_id,
            consent_type="photo_rights",
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.policy_version != version or _consent_hash(
                existing.asset_ids, existing.policy_version
            ) != _consent_hash(asset_ids, version or ""):
                raise IdempotencyConflictError("Consent idempotency payload changed")
            return existing
        if not confirmed or version != required_version:
            raise ConsentRequiredError(language=language, required_version=required_version)
        return await self._repo.create_consent(
            user_id=user_id,
            generation_id=None,
            consent_type="photo_rights",
            policy_version=required_version,
            asset_ids=asset_ids,
            idempotency_key=idempotency_key,
            confirmed_at=current,
        )

    async def bind_generation(
        self,
        *,
        decision: ModerationDecision,
        consent: UserConsent | None,
        generation_id: UUID,
    ) -> None:
        await self._repo.bind_generation(decision, generation_id)
        if consent is not None:
            await self._repo.bind_consent_generation(consent, generation_id)

    @staticmethod
    def _dto(row: ModerationDecision, *, replayed: bool) -> ModerationDecisionDTO:
        return ModerationDecisionDTO(
            id=row.id,
            outcome=ModerationOutcome(row.outcome),
            reason_codes=tuple(row.reason_codes),
            policy_version=row.policy_version,
            provider=row.provider,
            replayed=replayed,
        )

    @staticmethod
    def _raise_if_blocked(dto: ModerationDecisionDTO, *, language: str) -> None:
        if dto.outcome is ModerationOutcome.BLOCK:
            raise ModerationRejectedError(language=language, reason_codes=dto.reason_codes)
