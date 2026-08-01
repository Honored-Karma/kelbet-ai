from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models import AuditEvent, ModerationDecision, User
from kelbet.domain.enums import (
    GenerationStatus,
    ModerationReviewStatus,
    OperatorRole,
    ReservationStatus,
)
from kelbet.domain.exceptions import (
    AdminActionConflictError,
    CatalogModelNotFoundError,
    GenerationNotFoundError,
    GenerationTemplateNotFoundError,
    ModerationDecisionNotFoundError,
    PaymentProductNotFoundError,
    PaymentRefundNotFoundError,
    UserNotFoundError,
)
from kelbet.ops.grant_credits import REFERENCE_PATTERN, grant_credits
from kelbet.repositories.admin import AdminRepository
from kelbet.repositories.catalog import (
    CatalogRepository,
    FeatureFlagRepository,
    GenerationTemplateRepository,
)
from kelbet.repositories.generation import GenerationRepository
from kelbet.repositories.moderation import ModerationRepository
from kelbet.repositories.payment import PaymentRepository
from kelbet.repositories.referral import ReferralRepository
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.payment_refund import PaymentRefundService
from kelbet.services.wallet import WalletService

_SAFE_RECONCILIATION_DETAIL_KEYS = frozenset(
    {
        "direction",
        "amount",
        "telegram_amount",
        "receipt_amount",
        "classification",
        "telegram_exposes_explicit_chargeback_type",
        "ledger_transaction_id",
        "error_code",
    }
)


def _safe_reconciliation_details(details: Mapping[str, object] | None) -> dict[str, object]:
    if not details:
        return {}
    return {
        key: value
        for key, value in details.items()
        if key in _SAFE_RECONCILIATION_DETAIL_KEYS
        and (value is None or isinstance(value, str | int | float | bool))
    }


@dataclass(frozen=True, slots=True)
class OperatorContext:
    user_id: UUID
    telegram_id: int
    username: str | None
    role: OperatorRole
    bootstrap: bool

    @property
    def can_write(self) -> bool:
        return self.role is OperatorRole.ADMIN


def _request_hash(operator: OperatorContext, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"operator_user_id": str(operator.user_id), **payload},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_reason_reference(reason: str, reference: str) -> tuple[str, str]:
    clean_reason = reason.strip()
    clean_reference = reference.strip()
    if not REFERENCE_PATTERN.fullmatch(clean_reason):
        raise ValueError("Reason must be a 3-64 character safe code")
    if not REFERENCE_PATTERN.fullmatch(clean_reference):
        raise ValueError("Reference must be a 3-64 character safe code")
    return clean_reason, clean_reference


class AdminService:
    def __init__(
        self,
        session: AsyncSession,
        operator: OperatorContext,
        *,
        correlation_id: UUID,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._operator = operator
        self._correlation_id = correlation_id
        self._settings = settings or get_settings()
        self._admin = AdminRepository(session)
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._generations = GenerationRepository(session)
        self._payments = PaymentRepository(session)
        self._moderation = ModerationRepository(session)
        self._catalog = CatalogRepository(session)
        self._flags = FeatureFlagRepository(session)
        self._templates = GenerationTemplateRepository(session)
        self._referrals = ReferralRepository(session)

    async def _start_action(
        self,
        action_id: UUID,
        payload: dict[str, object],
    ) -> tuple[str, AuditEvent | None]:
        digest = _request_hash(self._operator, payload)
        await self._admin.lock_action(action_id)
        existing = await self._admin.get_audit_by_action_id(action_id)
        if existing is not None and existing.request_hash != digest:
            raise AdminActionConflictError("Action ID was already used for another request")
        return digest, existing

    async def _audit(
        self,
        *,
        action_id: UUID,
        request_hash: str,
        action: str,
        object_type: str,
        object_id: str,
        before: Mapping[str, object],
        after: Mapping[str, object],
        reason: str,
        reference: str,
    ) -> AuditEvent:
        return await self._admin.append_audit(
            action_id=action_id,
            request_hash=request_hash,
            operator_user_id=self._operator.user_id,
            operator_role=self._operator.role.value,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_data=dict(before),
            after_data=dict(after),
            reason=reason,
            reference=reference,
            correlation_id=self._correlation_id,
        )

    async def search_users(self, query: str, *, limit: int) -> list[dict[str, object]]:
        users = await self._users.search(query, limit=limit)
        return [self._user_summary(user) for user in users]

    async def get_user(self, user_id: UUID) -> dict[str, object]:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        wallet = await self._wallets.get_by_user_id(user.id)
        return {
            **self._user_summary(user),
            "language": user.language,
            "plan": user.plan,
            "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
            "blocked_reason": user.blocked_reason,
            "created_at": user.created_at.isoformat(),
            "wallet": (
                {
                    "id": str(wallet.id),
                    "balance": wallet.balance,
                    "reserved": wallet.reserved,
                    "available": wallet.available,
                    "version": wallet.version,
                }
                if wallet is not None
                else None
            ),
        }

    async def list_ledger(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[dict[str, object]]:
        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is None:
            raise UserNotFoundError(f"Wallet for user {user_id} not found")
        rows = await self._wallets.list_transactions(wallet.id, limit=limit, offset=offset)
        return [
            {
                "id": str(row.id),
                "type": row.type,
                "reason": row.reason,
                "amount": row.amount,
                "balance_after": row.balance_after,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    async def list_generations(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[dict[str, object]]:
        if await self._users.get_by_id(user_id) is None:
            raise UserNotFoundError(f"User {user_id} not found")
        rows = await self._generations.list_for_operator(user_id, limit=limit, offset=offset)
        return [
            {
                "id": str(row.id),
                "status": row.status,
                "modality": row.modality,
                "provider": row.provider,
                "provider_model_id": row.provider_model_id,
                "error_code": row.error_code,
                "error_class": row.error_class,
                "attempt_count": row.attempt_count,
                "user_credit_price": row.user_credit_price,
                "reservation_id": str(row.reservation_id) if row.reservation_id else None,
                "correlation_id": str(row.correlation_id),
                "created_at": row.created_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in rows
        ]

    async def list_payments(self, user_id: UUID, *, limit: int, offset: int) -> dict[str, object]:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        orders = await self._payments.list_orders_for_user(user_id, limit=limit, offset=offset)
        receipts = await self._payments.list_receipts_for_user(
            user_id, user.telegram_id, limit=limit
        )
        return {
            "orders": [
                {
                    "id": str(row.id),
                    "status": row.status,
                    "product_slug": str(row.product_snapshot.get("slug") or "unknown"),
                    "credits": row.credits,
                    "currency": row.currency,
                    "total_amount": row.total_amount,
                    "created_at": row.created_at.isoformat(),
                    "paid_at": row.paid_at.isoformat() if row.paid_at else None,
                    "refunded_at": row.refunded_at.isoformat() if row.refunded_at else None,
                }
                for row in orders
            ],
            "receipts": [
                {
                    "id": str(row.id),
                    "order_id": str(row.order_id) if row.order_id else None,
                    "status": row.status,
                    "currency": row.currency,
                    "total_amount": row.total_amount,
                    "error_code": row.error_code,
                    "created_at": row.created_at.isoformat(),
                    "processed_at": row.processed_at.isoformat() if row.processed_at else None,
                }
                for row in receipts
            ],
        }

    async def list_payment_reconciliation(
        self, *, status: str | None, limit: int, offset: int
    ) -> dict[str, object]:
        refunds = await self._payments.list_refunds(limit=limit, offset=offset)
        issues = await self._payments.list_issues(status=status, limit=limit, offset=offset)
        latest = await self._payments.latest_reconciliation_run()
        return {
            "refunds": [
                {
                    "id": str(row.id),
                    "order_id": str(row.order_id),
                    "status": row.status,
                    "stars_amount": row.stars_amount,
                    "credits_amount": row.credits_amount,
                    "attempt_count": row.attempt_count,
                    "last_error_code": row.last_error_code,
                    "external_refunded_at": (
                        row.external_refunded_at.isoformat() if row.external_refunded_at else None
                    ),
                    "ledger_transaction_id": (
                        str(row.ledger_transaction_id) if row.ledger_transaction_id else None
                    ),
                    "requested_at": row.requested_at.isoformat(),
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in refunds
            ],
            "issues": [
                {
                    "id": str(row.id),
                    "kind": row.kind,
                    "status": row.status,
                    "severity": row.severity,
                    "order_id": str(row.order_id) if row.order_id else None,
                    "refund_id": str(row.refund_id) if row.refund_id else None,
                    "details": _safe_reconciliation_details(row.details),
                    "first_seen_at": row.first_seen_at.isoformat(),
                    "last_seen_at": row.last_seen_at.isoformat(),
                    "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                }
                for row in issues
            ],
            "latest_run": (
                {
                    "id": str(latest.id),
                    "status": latest.status,
                    "fetched_count": latest.fetched_count,
                    "issue_count": latest.issue_count,
                    "started_at": latest.started_at.isoformat(),
                    "finished_at": latest.finished_at.isoformat() if latest.finished_at else None,
                    "error_code": latest.error_code,
                }
                if latest is not None
                else None
            ),
        }

    async def list_referrals(
        self, *, status: str | None, limit: int, offset: int
    ) -> list[dict[str, object]]:
        rows = await self._referrals.list_for_operator(status=status, limit=limit, offset=offset)
        return [
            {
                "id": str(reward.id),
                "status": reward.status,
                "inviter_user_id": str(attribution.inviter_user_id),
                "invited_user_id": str(attribution.invited_user_id),
                "payment_order_id": (
                    str(reward.payment_order_id) if reward.payment_order_id else None
                ),
                "inviter_bonus_credits": reward.inviter_bonus_credits,
                "invitee_bonus_credits": reward.invitee_bonus_credits,
                "eligible_at": reward.eligible_at.isoformat() if reward.eligible_at else None,
                "credited_at": reward.credited_at.isoformat() if reward.credited_at else None,
                "review_reason": reward.review_reason,
                "created_at": reward.created_at.isoformat(),
            }
            for reward, attribution in rows
        ]

    async def request_payment_refund(
        self,
        *,
        order_id: UUID,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "payment.refund.request",
            "order_id": str(order_id),
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        order = await self._payments.get_order_by_id(order_id)
        before = {"status": order.status if order is not None else "missing"}
        result = await PaymentRefundService(self._session, self._settings).request_refund(
            order_id=order_id,
            operator_user_id=self._operator.user_id,
            operator_reference=reference,
            reason=reason,
        )
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="payment.refund.request",
            object_type="payment_refund",
            object_id=str(result.id),
            before=before,
            after={
                "status": result.status.value,
                "order_id": str(result.order_id),
                "stars_amount": result.stars_amount,
                "credits_amount": result.credits_amount,
                "attempt_count": result.attempt_count,
                "error_code": result.last_error_code,
            },
            reason=reason,
            reference=reference,
        )

    async def retry_payment_refund(
        self,
        *,
        refund_id: UUID,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "payment.refund.retry",
            "refund_id": str(refund_id),
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        refund = await self._payments.get_refund_by_id(refund_id)
        if refund is None:
            raise PaymentRefundNotFoundError(f"Payment refund {refund_id} not found")
        before = {
            "status": refund.status,
            "attempt_count": refund.attempt_count,
            "error_code": refund.last_error_code,
        }
        result = await PaymentRefundService(self._session, self._settings).retry_refund(refund_id)
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="payment.refund.retry",
            object_type="payment_refund",
            object_id=str(result.id),
            before=before,
            after={
                "status": result.status.value,
                "attempt_count": result.attempt_count,
                "error_code": result.last_error_code,
            },
            reason=reason,
            reference=reference,
        )

    async def list_controls(self) -> dict[str, object]:
        models = await self._catalog.list_all()
        flags = await self._flags.list_all()
        products = await self._payments.list_products_for_operator()
        templates = await self._templates.list_all()
        recent_usage = await self._generations.list_recent_usage(
            since=datetime.now(UTC) - timedelta(minutes=15)
        )
        flag_by_key = {row.key: row for row in flags}

        def provider_health(
            provider: str,
            modality: str,
            *,
            configured: bool,
            flag_keys: tuple[str, ...],
        ) -> dict[str, object]:
            selected = [
                row
                for row in recent_usage
                if row.provider == provider
                and (
                    modality == "media"
                    or row.modality == modality
                    or (modality == "image" and row.modality == "image_edit")
                )
            ]
            succeeded = sum(1 for row in selected if (row.meta or {}).get("status") == "succeeded")
            failed = sum(
                1 for row in selected if (row.meta or {}).get("status") in {"failed", "fallback"}
            )
            selected_flags = [flag_by_key.get(key) for key in flag_keys]
            enabled = all(row is not None and row.enabled for row in selected_flags)

            def is_canary(row: object) -> bool:
                payload = getattr(row, "payload", None)
                return isinstance(payload, dict) and bool(payload.get("telegram_ids"))

            canary = any(is_canary(row) for row in selected_flags)
            if not enabled:
                status = "disabled"
            elif not configured:
                status = "unconfigured"
            elif failed >= 3 and failed > succeeded:
                status = "degraded"
            elif succeeded:
                status = "healthy"
            else:
                status = "ready"
            return {
                "provider": provider,
                "modality": modality,
                "configured": configured,
                "enabled": enabled,
                "canary": canary,
                "status": status,
                "recent_successes": succeeded,
                "recent_failures": failed,
                "last_attempt_at": selected[0].created_at.isoformat() if selected else None,
            }

        return {
            "models": [
                {
                    "slug": row.slug,
                    "modality": row.modality,
                    "provider": row.provider,
                    "enabled": row.enabled,
                    "feature_flag": row.feature_flag,
                    "user_credit_price": row.user_credit_price,
                }
                for row in models
            ],
            "feature_flags": [
                {"key": row.key, "enabled": row.enabled}
                for row in sorted(flags, key=lambda item: item.key)
            ],
            "provider_health": [
                provider_health(
                    "runway",
                    "media",
                    configured=bool(self._settings.runway_api_key),
                    flag_keys=("runway_media",),
                ),
                provider_health(
                    "google",
                    "image",
                    configured=bool(self._settings.google_api_key),
                    flag_keys=("google_image", "image_fallback"),
                ),
                provider_health(
                    "google",
                    "video",
                    configured=bool(self._settings.google_api_key),
                    flag_keys=("google_video",),
                ),
            ],
            "payment_products": [
                {
                    "slug": row.slug,
                    "credits": row.credits,
                    "stars": row.stars,
                    "enabled": row.enabled,
                }
                for row in products
            ],
            "templates": [
                {
                    "slug": row.slug,
                    "version": row.version,
                    "kind": row.kind,
                    "enabled": row.enabled,
                    "display_order": row.display_order,
                    "localization": row.localization,
                }
                for row in templates
            ],
        }

    async def list_audit(self, *, limit: int, offset: int) -> list[dict[str, object]]:
        rows = await self._admin.list_audit(limit=limit, offset=offset)
        return [self.audit_payload(row) for row in rows]

    async def list_moderation_queue(
        self, *, review_status: ModerationReviewStatus, limit: int, offset: int
    ) -> list[dict[str, object]]:
        rows = await self._moderation.list_queue(
            review_status=review_status,
            limit=limit,
            offset=offset,
        )
        return [self._moderation_payload(row) for row in rows]

    async def review_moderation_decision(
        self,
        *,
        decision_id: UUID,
        review_outcome: str,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "moderation.review",
            "decision_id": str(decision_id),
            "review_outcome": review_outcome,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        decision = await self._moderation.get_for_update(decision_id)
        if decision is None:
            raise ModerationDecisionNotFoundError(f"Moderation decision {decision_id} not found")
        before = {
            "review_status": decision.review_status,
            "review_outcome": decision.review_outcome,
        }
        decision.review_status = ModerationReviewStatus.REVIEWED.value
        decision.review_outcome = review_outcome
        decision.reviewed_by_user_id = self._operator.user_id
        decision.reviewed_at = datetime.now(UTC)
        await self._session.flush()
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="moderation.review",
            object_type="moderation_decision",
            object_id=str(decision_id),
            before=before,
            after={
                "review_status": decision.review_status,
                "review_outcome": decision.review_outcome,
            },
            reason=reason,
            reference=reference,
        )

    async def grant(
        self,
        *,
        user_id: UUID,
        amount: int,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "wallet.grant",
            "user_id": str(user_id),
            "amount": amount,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        user = await self._users.get_by_id_for_update(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        result = await grant_credits(
            self._session,
            telegram_id=user.telegram_id,
            amount=amount,
            reference=reference,
            idempotency_key=f"admin-grant:{action_id}",
            source="admin_api",
            operator_user_id=self._operator.user_id,
        )
        before = {"balance": result.balance_before}
        after = {
            "applied": result.applied,
            "amount": amount,
            "balance": result.balance_after,
            "reserved": result.reserved,
            "transaction_id": str(result.transaction_id) if result.transaction_id else None,
        }
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="wallet.grant",
            object_type="user_wallet",
            object_id=str(user_id),
            before=before,
            after=after,
            reason=reason,
            reference=reference,
        )

    async def refund_generation(
        self,
        *,
        generation_id: UUID,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "generation.refund",
            "generation_id": str(generation_id),
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        job = await self._generations.get_by_id_for_update(generation_id)
        if job is None:
            raise GenerationNotFoundError(f"Generation {generation_id} not found")
        if job.status != GenerationStatus.SUCCEEDED.value or job.reservation_id is None:
            raise AdminActionConflictError("Only a succeeded captured generation can be refunded")
        reservation = await self._wallets.get_reservation_by_id(job.reservation_id)
        if reservation is None or reservation.status != ReservationStatus.CAPTURED.value:
            raise AdminActionConflictError("Generation reservation is not captured")
        before = {
            "generation_status": job.status,
            "reservation_status": reservation.status,
            "refunded": reservation.refund_tx_id is not None,
        }
        result = await WalletService(self._session).refund(
            reservation.id,
            meta={
                "source": "admin_api",
                "operator_user_id": str(self._operator.user_id),
                "reference": reference,
            },
        )
        after = {
            "applied": result.applied,
            "generation_status": job.status,
            "reservation_status": result.status.value,
            "refunded": result.refund_tx_id is not None,
            "refund_transaction_id": (str(result.refund_tx_id) if result.refund_tx_id else None),
            "balance": result.balance,
        }
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="generation.refund",
            object_type="generation",
            object_id=str(generation_id),
            before=before,
            after=after,
            reason=reason,
            reference=reference,
        )

    async def set_user_blocked(
        self,
        *,
        user_id: UUID,
        blocked: bool,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        action = "user.block" if blocked else "user.unblock"
        payload: dict[str, object] = {
            "action": action,
            "user_id": str(user_id),
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        user = await self._users.get_by_id_for_update(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        before = {"blocked": user.is_blocked, "blocked_reason": user.blocked_reason}
        applied = user.is_blocked != blocked
        user.is_blocked = blocked
        user.blocked_at = datetime.now(UTC) if blocked else None
        user.blocked_reason = reason if blocked else None
        await self._session.flush()
        after = {
            "applied": applied,
            "blocked": user.is_blocked,
            "blocked_reason": user.blocked_reason,
        }
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action=action,
            object_type="user",
            object_id=str(user_id),
            before=before,
            after=after,
            reason=reason,
            reference=reference,
        )

    async def set_model_enabled(
        self,
        *,
        slug: str,
        enabled: bool,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "catalog.set_enabled",
            "slug": slug,
            "enabled": enabled,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        model = await self._catalog.get_by_slug_for_update(slug)
        if model is None:
            raise CatalogModelNotFoundError(f"Model {slug} not found")
        before = {"enabled": model.enabled}
        applied = model.enabled != enabled
        model.enabled = enabled
        await self._session.flush()
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="catalog.set_enabled",
            object_type="catalog_model",
            object_id=slug,
            before=before,
            after={"applied": applied, "enabled": model.enabled},
            reason=reason,
            reference=reference,
        )

    async def set_feature_flag_enabled(
        self,
        *,
        key: str,
        enabled: bool,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "feature_flag.set_enabled",
            "key": key,
            "enabled": enabled,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        flag = await self._flags.get_for_update(key)
        if flag is None:
            raise AdminActionConflictError("Unknown feature flag")
        before = {"enabled": flag.enabled}
        applied = flag.enabled != enabled
        flag.enabled = enabled
        await self._session.flush()
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="feature_flag.set_enabled",
            object_type="feature_flag",
            object_id=key,
            before=before,
            after={"applied": applied, "enabled": flag.enabled},
            reason=reason,
            reference=reference,
        )

    async def set_template_config(
        self,
        *,
        slug: str,
        enabled: bool,
        display_order: int,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "generation_template.configure",
            "slug": slug,
            "enabled": enabled,
            "display_order": display_order,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        template = await self._templates.get_by_slug_for_update(slug)
        if template is None:
            raise GenerationTemplateNotFoundError(f"Template {slug} not found")
        before = {
            "enabled": template.enabled,
            "display_order": template.display_order,
        }
        applied = before != {
            "enabled": enabled,
            "display_order": display_order,
        }
        template.enabled = enabled
        template.display_order = display_order
        await self._session.flush()
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="generation_template.configure",
            object_type="generation_template",
            object_id=slug,
            before=before,
            after={
                "applied": applied,
                "enabled": template.enabled,
                "display_order": template.display_order,
            },
            reason=reason,
            reference=reference,
        )

    async def set_payment_product_enabled(
        self,
        *,
        slug: str,
        enabled: bool,
        reason: str,
        reference: str,
        action_id: UUID,
    ) -> AuditEvent:
        reason, reference = _safe_reason_reference(reason, reference)
        payload: dict[str, object] = {
            "action": "payment_product.set_enabled",
            "slug": slug,
            "enabled": enabled,
            "reason": reason,
            "reference": reference,
        }
        digest, existing = await self._start_action(action_id, payload)
        if existing is not None:
            return existing
        product = await self._payments.get_product_by_slug_any(slug)
        if product is None:
            raise PaymentProductNotFoundError(f"Payment product {slug} not found")
        before = {"enabled": product.enabled}
        applied = product.enabled != enabled
        product.enabled = enabled
        await self._session.flush()
        return await self._audit(
            action_id=action_id,
            request_hash=digest,
            action="payment_product.set_enabled",
            object_type="payment_product",
            object_id=slug,
            before=before,
            after={"applied": applied, "enabled": product.enabled},
            reason=reason,
            reference=reference,
        )

    @staticmethod
    def _user_summary(user: User) -> dict[str, object]:
        return {
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.username,
            "is_blocked": user.is_blocked,
        }

    @staticmethod
    def _moderation_payload(row: ModerationDecision) -> dict[str, object]:
        """Return only bounded investigation metadata; raw input never exists here."""
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "generation_id": str(row.generation_id) if row.generation_id else None,
            "asset_ids": [str(asset_id) for asset_id in row.asset_ids],
            "context": row.context,
            "input_hash": row.input_hash,
            "mode": row.mode,
            "outcome": row.outcome,
            "reason_codes": row.reason_codes,
            "policy_version": row.policy_version,
            "provider": row.provider,
            "provider_model": row.provider_model,
            "error_code": row.error_code,
            "review_status": row.review_status,
            "review_outcome": row.review_outcome,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def audit_payload(row: AuditEvent) -> dict[str, object]:
        return {
            "id": str(row.id),
            "action_id": str(row.action_id),
            "operator_user_id": str(row.operator_user_id),
            "operator_role": row.operator_role,
            "action": row.action,
            "object_type": row.object_type,
            "object_id": row.object_id,
            "before": row.before_data,
            "after": row.after_data,
            "reason": row.reason,
            "reference": row.reference,
            "correlation_id": str(row.correlation_id),
            "created_at": row.created_at.isoformat(),
        }
