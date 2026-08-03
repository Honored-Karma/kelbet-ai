"""Recurring plan grants.

Two independent guarantees stop a replayed renewal from handing out a second period
of credits:

1. ``subscription_grants`` has UNIQUE(subscription_id, period_index), so a duplicate
   insert fails at the storage layer no matter what the caller believes.
2. The wallet credit uses the ledger idempotency key ``plan_grant:{sub}:{period}``,
   so even a grant row lost to a partial rollback cannot double-credit.

Either alone would be sufficient; both are cheap, and money bugs are not the place to
economise on redundancy.

Feature gating lives at the call site via the ``subscriptions`` feature flag, matching
how ``veo_extended`` is handled. This service does not silently no-op when the flag is
off — a caller that reaches it has already decided to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import (
    SubscriptionGrant,
    SubscriptionPlan,
    User,
    UserSubscription,
    Wallet,
)
from kelbet.domain.enums import Plan, SubscriptionStatus, TxReason
from kelbet.domain.exceptions import KelbetError, WalletNotFoundError
from kelbet.observability import get_metrics
from kelbet.services.wallet import WalletService

#: DB feature flag that gates every subscription surface.
SUBSCRIPTIONS_FLAG = "subscriptions"


class SubscriptionPlanNotFoundError(KelbetError):
    """Raised when a plan slug is unknown or disabled."""


class SubscriptionNotFoundError(KelbetError):
    """Raised when a user has no subscription."""


def grant_idempotency_key(subscription_id: UUID, period_index: int) -> str:
    return f"plan_grant:{subscription_id}:{period_index}"


def period_end(start: datetime, period_days: int) -> datetime:
    """Fixed-length periods, deliberately not calendar months.

    A 30-day period has no clamping edge cases (no "31st of February" question) and
    makes the credit rate predictable for the buyer. When Telegram Stars recurring
    subscriptions are wired up, this must follow Telegram's own cycle instead.
    """
    if period_days <= 0:
        msg = "period_days must be positive"
        raise ValueError(msg)
    return start + timedelta(days=period_days)


@dataclass(frozen=True, slots=True)
class GrantOutcome:
    subscription_id: UUID
    period_index: int
    credits: int
    applied: bool
    balance: int | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionState:
    subscription_id: UUID
    plan_slug: str
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    current_period_index: int
    cancel_at_period_end: bool


def _record(operation: str, *, applied: bool) -> None:
    get_metrics().incr(
        "subscription.operation",
        tags={"operation": operation, "outcome": "applied" if applied else "idempotent"},
    )


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._wallets = WalletService(session)

    async def _plan_by_slug(self, slug: str) -> SubscriptionPlan:
        result = await self._session.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.slug == slug,
                SubscriptionPlan.enabled.is_(True),
            )
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise SubscriptionPlanNotFoundError(f"Plan {slug} is unknown or disabled")
        return plan

    async def _subscription_for_update(self, user_id: UUID) -> UserSubscription | None:
        result = await self._session.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _wallet_id(self, user_id: UUID) -> UUID:
        result = await self._session.execute(select(Wallet.id).where(Wallet.user_id == user_id))
        wallet_id = result.scalar_one_or_none()
        if wallet_id is None:
            raise WalletNotFoundError(f"User {user_id} has no wallet")
        return wallet_id

    async def _set_user_plan(self, user_id: UUID, plan_key: str) -> None:
        await self._session.execute(update(User).where(User.id == user_id).values(plan=plan_key))

    def _state(self, subscription: UserSubscription, plan_slug: str) -> SubscriptionState:
        return SubscriptionState(
            subscription_id=subscription.id,
            plan_slug=plan_slug,
            status=SubscriptionStatus(subscription.status),
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            current_period_index=subscription.current_period_index,
            cancel_at_period_end=subscription.cancel_at_period_end,
        )

    async def _grant(
        self,
        subscription: UserSubscription,
        *,
        period_index: int,
        credits: int,
        now: datetime,
    ) -> GrantOutcome:
        """Credit one period. Safe to call twice for the same period index."""
        existing = await self._session.execute(
            select(SubscriptionGrant).where(
                SubscriptionGrant.subscription_id == subscription.id,
                SubscriptionGrant.period_index == period_index,
            )
        )
        if existing.scalar_one_or_none() is not None:
            _record("grant", applied=False)
            return GrantOutcome(
                subscription_id=subscription.id,
                period_index=period_index,
                credits=credits,
                applied=False,
            )

        grant = SubscriptionGrant(
            subscription_id=subscription.id,
            period_index=period_index,
            credits=credits,
            granted_at=now,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(grant)
                await self._session.flush()
        except IntegrityError:
            # Lost the race against a concurrent renewal; the other writer credited.
            _record("grant", applied=False)
            return GrantOutcome(
                subscription_id=subscription.id,
                period_index=period_index,
                credits=credits,
                applied=False,
            )

        wallet_id = await self._wallet_id(subscription.user_id)
        credit = await self._wallets.credit(
            wallet_id,
            credits,
            TxReason.PLAN_GRANT,
            grant_idempotency_key(subscription.id, period_index),
            meta={
                "subscription_id": str(subscription.id),
                "period_index": period_index,
                "source": "subscription_grant",
            },
        )
        grant.ledger_transaction_id = credit.transaction_id
        await self._session.flush()

        _record("grant", applied=credit.applied)
        return GrantOutcome(
            subscription_id=subscription.id,
            period_index=period_index,
            credits=credits,
            applied=credit.applied,
            balance=credit.balance,
        )

    async def activate(
        self,
        user_id: UUID,
        plan_slug: str,
        *,
        now: datetime | None = None,
        source_payment_order_id: UUID | None = None,
    ) -> tuple[SubscriptionState, GrantOutcome]:
        """Start or switch a plan and credit the first period immediately.

        Switching plans starts a fresh period rather than pro-rating. Pro-rating a
        credit balance has no honest answer once credits are already spent, and a
        clean restart is the option a buyer can verify for themselves.
        """
        moment = now or datetime.now(UTC)
        plan = await self._plan_by_slug(plan_slug)
        subscription = await self._subscription_for_update(user_id)

        if subscription is None:
            subscription = UserSubscription(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE.value,
                started_at=moment,
                current_period_start=moment,
                current_period_end=period_end(moment, plan.period_days),
                current_period_index=0,
                cancel_at_period_end=False,
                source_payment_order_id=source_payment_order_id,
            )
            self._session.add(subscription)
            await self._session.flush()
            _record("activate", applied=True)
        else:
            subscription.plan_id = plan.id
            subscription.status = SubscriptionStatus.ACTIVE.value
            subscription.current_period_start = moment
            subscription.current_period_end = period_end(moment, plan.period_days)
            subscription.current_period_index += 1
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None
            subscription.expired_at = None
            if source_payment_order_id is not None:
                subscription.source_payment_order_id = source_payment_order_id
            await self._session.flush()
            _record("switch", applied=True)

        await self._set_user_plan(user_id, plan.plan_key)
        outcome = await self._grant(
            subscription,
            period_index=subscription.current_period_index,
            credits=plan.credits_per_period,
            now=moment,
        )
        return self._state(subscription, plan.slug), outcome

    async def cancel(
        self,
        user_id: UUID,
        *,
        now: datetime | None = None,
    ) -> SubscriptionState:
        """Stop renewing, keep the paid period. Reversible until it ends."""
        moment = now or datetime.now(UTC)
        subscription = await self._subscription_for_update(user_id)
        if subscription is None:
            raise SubscriptionNotFoundError(f"User {user_id} has no subscription")

        if subscription.status == SubscriptionStatus.EXPIRED.value:
            _record("cancel", applied=False)
            return self._state(subscription, subscription.plan.slug)

        already = subscription.cancel_at_period_end
        subscription.cancel_at_period_end = True
        subscription.status = SubscriptionStatus.CANCELLING.value
        subscription.cancelled_at = subscription.cancelled_at or moment
        await self._session.flush()
        _record("cancel", applied=not already)
        return self._state(subscription, subscription.plan.slug)

    async def resume(self, user_id: UUID) -> SubscriptionState:
        """Undo a pending cancellation while the paid period is still running."""
        subscription = await self._subscription_for_update(user_id)
        if subscription is None:
            raise SubscriptionNotFoundError(f"User {user_id} has no subscription")
        if subscription.status == SubscriptionStatus.EXPIRED.value:
            raise SubscriptionNotFoundError(f"Subscription for {user_id} already expired")

        already_active = not subscription.cancel_at_period_end
        subscription.cancel_at_period_end = False
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.cancelled_at = None
        await self._session.flush()
        _record("resume", applied=not already_active)
        return self._state(subscription, subscription.plan.slug)

    async def process_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[GrantOutcome]:
        """Renew or expire every subscription whose period has elapsed.

        Uses SKIP LOCKED so several workers can share the queue without blocking each
        other or double-crediting.
        """
        moment = now or datetime.now(UTC)
        result = await self._session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.current_period_end <= moment,
                UserSubscription.status.in_(
                    (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.CANCELLING.value)
                ),
            )
            .order_by(UserSubscription.current_period_end)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        due = list(result.scalars().all())

        outcomes: list[GrantOutcome] = []
        for subscription in due:
            if subscription.cancel_at_period_end:
                subscription.status = SubscriptionStatus.EXPIRED.value
                subscription.expired_at = moment
                await self._set_user_plan(subscription.user_id, Plan.FREE.value)
                await self._session.flush()
                _record("expire", applied=True)
                continue

            plan = subscription.plan
            subscription.current_period_start = subscription.current_period_end
            subscription.current_period_end = period_end(
                subscription.current_period_start, plan.period_days
            )
            subscription.current_period_index += 1
            await self._session.flush()

            outcomes.append(
                await self._grant(
                    subscription,
                    period_index=subscription.current_period_index,
                    credits=plan.credits_per_period,
                    now=moment,
                )
            )
        return outcomes
