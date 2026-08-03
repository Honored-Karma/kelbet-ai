"""Recurring plans, billed by Telegram.

Telegram owns the billing clock. ``createInvoiceLink`` with
``subscription_period=2592000`` hands it the schedule; every 30 days Telegram charges the
user and delivers another ``successful_payment`` carrying the **original**
``invoice_payload`` with a **new** ``telegram_payment_charge_id``. Two things follow.

A period is credited if and only if Telegram collected money for it. ``apply_charge`` is
the only path that grants, and ``process_due`` grants nothing at all — it only expires.
The earlier design renewed on a local clock and credited on that schedule, which would
have handed a subscriber credits every 30 days for ever off a single payment.

``current_period_end`` is whatever Telegram reported, never computed locally. Local
arithmetic would drift away from the clock that actually takes the money, and the user
would either lose paid days or gain free ones.

Three independent guarantees stop a replayed charge from handing out a second period:

1. The row lock the money path takes on the subscription, so two deliveries serialise
   instead of both reading "not credited yet".
2. ``subscription_grants`` has UNIQUE(subscription_id, period_index) *and* UNIQUE(charge_id).
   The first defends against a replayed renewal; the second against a redelivered update,
   which is the case Telegram actually produces.
3. The wallet credit uses the ledger idempotency key ``plan_grant:{sub}:{period}``, so even
   a grant row lost to a partial rollback cannot double-credit.

Any one would usually be enough; money bugs are not the place to economise on redundancy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import (
    SubscriptionGrant,
    SubscriptionPlan,
    User,
    UserSubscription,
    Wallet,
)
from kelbet.domain.enums import Language, Plan, SubscriptionStatus, TxReason
from kelbet.domain.exceptions import (
    KelbetError,
    PaymentUnavailableError,
    WalletNotFoundError,
)
from kelbet.observability import get_metrics
from kelbet.services.wallet import WalletService

#: DB feature flag that gates every subscription surface.
SUBSCRIPTIONS_FLAG = "subscriptions"

#: Prefix that marks an invoice payload as belonging to a subscription rather than a
#: one-off credit pack. Telegram delivers both through the same payment updates, so the
#: handlers route on this without a database round trip.
SUBSCRIPTION_PAYLOAD_PREFIX = "kelbet-sub"

STARS_CURRENCY = "XTR"

#: Telegram: "Currently, it must always be 2592000 (30 days) if specified."
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
#: Telegram: "Subscription price must no exceed 10000 Telegram Stars."
MAX_SUBSCRIPTION_STARS = 10_000


def is_subscription_payload(invoice_payload: str) -> bool:
    return invoice_payload.startswith(f"{SUBSCRIPTION_PAYLOAD_PREFIX}:")


class SubscriptionPlanNotFoundError(KelbetError):
    """Raised when a plan slug is unknown or disabled."""


class SubscriptionNotFoundError(KelbetError):
    """Raised when a user has no subscription."""


class SubscriptionValidationError(KelbetError):
    """Raised when a checkout request is well-formed but not allowed."""


def grant_idempotency_key(subscription_id: UUID, period_index: int) -> str:
    return f"plan_grant:{subscription_id}:{period_index}"


def period_end(start: datetime, period_days: int) -> datetime:
    """Fixed-length periods, deliberately not calendar months.

    A 30-day period has no clamping edge cases (no "31st of February" question) and makes
    the credit rate predictable for the buyer.

    This is now a **fallback**, not the schedule. Telegram owns the billing clock and
    reports the real deadline in `subscription_expiration_date`; that value is authoritative
    because it is the moment the next charge actually happens. This function supplies a
    deadline only when Telegram omits the field, since a subscription with no deadline would
    never expire and the user would keep a paid tier for free.
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
    renewal_failed: bool = False


@dataclass(frozen=True, slots=True)
class SubscriptionCheckout:
    """Everything needed to build a recurring invoice link, and nothing more."""

    subscription_id: UUID
    invoice_payload: str
    currency: str
    stars: int
    credits_per_period: int
    plan_slug: str
    plan_name: str
    plan_description: str
    subscription_period_seconds: int


@dataclass(frozen=True, slots=True)
class PreCheckoutDecision:
    ok: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ChargeOutcome:
    """Result of applying one Telegram charge.

    `applied` separates a real grant from an idempotent replay; `credits` reports the
    period's grant either way, so a replayed update can still answer the user correctly
    instead of claiming zero.
    """

    applied: bool
    subscription_id: UUID | None
    plan_key: str | None
    plan_name: str
    credits: int
    balance: int | None
    period_end: datetime | None
    is_first: bool = False
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CancelRequest:
    """What the caller must tell Telegram in order to stop renewal."""

    subscription_id: UUID
    telegram_id: int
    root_charge_id: str | None
    access_until: datetime


def _record(operation: str, *, applied: bool) -> None:
    get_metrics().incr(
        "subscription.operation",
        tags={"operation": operation, "outcome": "applied" if applied else "idempotent"},
    )


class SubscriptionService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or Settings()
        self._wallets = WalletService(session)

    def _assert_enabled(self) -> None:
        if not self._settings.subscriptions_enabled:
            raise PaymentUnavailableError("Subscriptions are not enabled")

    async def _by_payload(
        self, invoice_payload: str, *, for_update: bool = False
    ) -> UserSubscription | None:
        statement = select(UserSubscription).where(
            UserSubscription.invoice_payload == invoice_payload
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _balance(self, user_id: UUID) -> int | None:
        result = await self._session.execute(
            select(Wallet.balance).where(Wallet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    def _checkout(
        self,
        subscription: UserSubscription,
        plan: SubscriptionPlan,
        language: Language,
    ) -> SubscriptionCheckout:
        assert subscription.invoice_payload is not None
        localized = _localized(plan.localization, language)
        return SubscriptionCheckout(
            subscription_id=subscription.id,
            invoice_payload=subscription.invoice_payload,
            currency=STARS_CURRENCY,
            stars=plan.stars,
            credits_per_period=plan.credits_per_period,
            plan_slug=plan.slug,
            plan_name=str(localized.get("name") or plan.slug),
            plan_description=str(localized.get("description") or ""),
            subscription_period_seconds=SUBSCRIPTION_PERIOD_SECONDS,
        )

    def _charge_error(
        self, subscription: UserSubscription | None, error_code: str
    ) -> ChargeOutcome:
        return ChargeOutcome(
            applied=False,
            subscription_id=subscription.id if subscription is not None else None,
            plan_key=None,
            plan_name="",
            credits=0,
            balance=None,
            period_end=None,
            error_code=error_code,
        )

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
            renewal_failed=subscription.renewal_failed_at is not None,
        )

    async def _grant(
        self,
        subscription: UserSubscription,
        *,
        period_index: int,
        credits: int,
        now: datetime,
        charge_id: str | None = None,
    ) -> GrantOutcome:
        """Credit one period. Safe to call twice for the same period index or charge.

        Three independent mechanisms have to be defeated before a period could be credited
        twice, and they fail in different ways on purpose: the row lock the caller holds on
        the subscription, the unique constraints here, and the wallet ledger's own
        idempotency key. `period_index` catches a replayed renewal; `charge_id` catches a
        redelivered Telegram update, which is the case that actually occurs in production.
        """
        conditions = [
            SubscriptionGrant.subscription_id == subscription.id,
            SubscriptionGrant.period_index == period_index,
        ]
        existing = await self._session.execute(select(SubscriptionGrant).where(*conditions))
        replay = existing.scalar_one_or_none()
        if replay is None and charge_id is not None:
            by_charge = await self._session.execute(
                select(SubscriptionGrant).where(SubscriptionGrant.charge_id == charge_id)
            )
            replay = by_charge.scalar_one_or_none()
        if replay is not None:
            _record("grant", applied=False)
            return GrantOutcome(
                subscription_id=subscription.id,
                period_index=replay.period_index,
                credits=replay.credits,
                applied=False,
            )

        grant = SubscriptionGrant(
            subscription_id=subscription.id,
            period_index=period_index,
            credits=credits,
            granted_at=now,
            charge_id=charge_id,
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

    async def start_checkout(
        self,
        user_id: UUID,
        plan_slug: str,
        *,
        language: Language,
        terms_accepted: bool,
        accepted_terms_version: str | None = None,
        now: datetime | None = None,
    ) -> SubscriptionCheckout:
        """Reserve the identity Telegram will echo back, and return link parameters.

        No money moves and no period is credited. The row exists so that the payload
        Telegram returns on every renewal already resolves to a known user and plan.
        """
        self._assert_enabled()
        if not terms_accepted:
            raise SubscriptionValidationError("Terms must be accepted before subscribing")
        if accepted_terms_version is not None and (
            accepted_terms_version.strip() != self._settings.payment_terms_version.strip()
        ):
            raise SubscriptionValidationError("Accepted payment terms are no longer current")
        if accepted_terms_version is None and self._settings.app_env.lower() == "production":
            raise SubscriptionValidationError("Current payment terms version is required")

        moment = now or datetime.now(UTC)
        plan = await self._plan_by_slug(plan_slug)
        if plan.stars > MAX_SUBSCRIPTION_STARS:
            # Telegram would reject the invoice link outright. Fail here, where the reason
            # is legible, rather than as an opaque provider error.
            raise SubscriptionValidationError("Plan price exceeds the Telegram Stars limit")

        subscription = await self._subscription_for_update(user_id)
        live = {
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.CANCELLING.value,
            SubscriptionStatus.PAYMENT_FAILED.value,
        }
        if subscription is not None and subscription.status in live:
            # One row per user, and Telegram would happily bill two overlapping
            # subscriptions. Switching therefore means cancelling first.
            raise SubscriptionValidationError("Cancel the current subscription before switching")

        if subscription is not None and subscription.status == SubscriptionStatus.PENDING.value:
            if subscription.plan_id == plan.id:
                # A second tap on the same button. Reuse the payload so the user cannot end
                # up with two invoice links that both bill.
                _record("checkout", applied=False)
                return self._checkout(subscription, plan, language)
            subscription.plan_id = plan.id

        payload = f"{SUBSCRIPTION_PAYLOAD_PREFIX}:{uuid4().hex}"
        if subscription is None:
            subscription = UserSubscription(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionStatus.PENDING.value,
                started_at=moment,
                # Placeholder bounds: the row is NOT NULL and CHECK-ordered, and Telegram
                # supplies the real deadline with the first charge. `pending` is excluded
                # from the expiry sweep, so these dates are never acted upon.
                current_period_start=moment,
                current_period_end=period_end(moment, plan.period_days),
                current_period_index=0,
                cancel_at_period_end=False,
                invoice_payload=payload,
            )
            self._session.add(subscription)
        else:
            # Reusing an expired or superseded row keeps one subscription per user. The old
            # Telegram subscription is dead, so its payload must not be reused.
            subscription.status = SubscriptionStatus.PENDING.value
            subscription.invoice_payload = payload
            subscription.root_charge_id = None
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None
            subscription.expired_at = None
            subscription.renewal_failed_at = None
        await self._session.flush()
        _record("checkout", applied=True)
        return self._checkout(subscription, plan, language)

    async def validate_pre_checkout(
        self,
        *,
        telegram_id: int,
        invoice_payload: str,
        currency: str,
        total_amount: int,
    ) -> PreCheckoutDecision:
        """Approve or reject Telegram's pre-checkout query for a subscription.

        A subscription payload must never reach `PaymentService.validate_pre_checkout`:
        there is no `payment_orders` row behind it, so that path answers `order_not_found`
        and Telegram refuses a perfectly good payment. Routing on the payload prefix is
        what keeps the two apart.

        Unlike a one-off order there is no pre-checkout claim to record — Telegram may open
        the confirmation more than once before the user pays, and rejecting the second
        attempt would strand them.
        """
        subscription = await self._by_payload(invoice_payload)
        if subscription is None:
            return PreCheckoutDecision(ok=False, error_code="subscription_not_found")
        user = await self._session.get(User, subscription.user_id)
        if user is None or user.telegram_id != telegram_id:
            return PreCheckoutDecision(ok=False, error_code="buyer_mismatch")
        if currency != STARS_CURRENCY:
            return PreCheckoutDecision(ok=False, error_code="currency_mismatch")
        plan = await self._session.get(SubscriptionPlan, subscription.plan_id)
        if plan is None or not plan.enabled:
            return PreCheckoutDecision(ok=False, error_code="plan_unavailable")
        if total_amount != plan.stars:
            return PreCheckoutDecision(ok=False, error_code="amount_mismatch")
        if subscription.status == SubscriptionStatus.EXPIRED.value:
            return PreCheckoutDecision(ok=False, error_code="subscription_expired")
        return PreCheckoutDecision(ok=True)

    async def apply_charge(
        self,
        *,
        telegram_id: int,
        invoice_payload: str,
        currency: str,
        total_amount: int,
        charge_id: str,
        expires_at: datetime | None,
        language: Language = Language.RU,
        now: datetime | None = None,
    ) -> ChargeOutcome:
        """Credit one paid period. Safe to call repeatedly with the same charge id.

        This is the only path that grants a renewal. The expiry sweep deliberately grants
        nothing, so a period is credited if and only if Telegram actually collected money
        for it.
        """
        moment = now or datetime.now(UTC)
        subscription = await self._by_payload(invoice_payload, for_update=True)
        if subscription is None:
            _record("charge_rejected", applied=False)
            return self._charge_error(None, "subscription_not_found")

        user = await self._session.get(User, subscription.user_id)
        plan = await self._session.get(SubscriptionPlan, subscription.plan_id)
        if user is None or plan is None:
            _record("charge_rejected", applied=False)
            return self._charge_error(subscription, "subscription_orphaned")
        if user.telegram_id != telegram_id:
            _record("charge_rejected", applied=False)
            return self._charge_error(subscription, "buyer_mismatch")
        if currency != STARS_CURRENCY:
            _record("charge_rejected", applied=False)
            return self._charge_error(subscription, "currency_mismatch")
        if total_amount != plan.stars:
            _record("charge_rejected", applied=False)
            return self._charge_error(subscription, "amount_mismatch")

        # Whether this is the opening charge is decided from our own records, never from
        # Telegram's optional `is_first_recurring` flag: an absent optional field must not
        # be able to turn a renewal into a first payment.
        is_first = subscription.root_charge_id is None
        deadline = expires_at or period_end(moment, plan.period_days)

        if is_first:
            subscription.root_charge_id = charge_id
            subscription.started_at = moment
            period_index = subscription.current_period_index
        else:
            period_index = subscription.current_period_index + 1

        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.current_period_start = moment
        subscription.current_period_end = deadline
        subscription.current_period_index = period_index
        subscription.renewal_failed_at = None
        subscription.expired_at = None
        # A charge arriving after a cancellation means the user re-enabled the subscription
        # from Telegram's own UI.
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        await self._session.flush()

        outcome = await self._grant(
            subscription,
            period_index=period_index,
            credits=plan.credits_per_period,
            now=moment,
            charge_id=charge_id,
        )
        if not outcome.applied:
            # A redelivered update. The state above is idempotent, so nothing is undone;
            # the period simply was not credited a second time.
            _record("charge_replay", applied=False)
        await self._set_user_plan(subscription.user_id, plan.plan_key)
        await self._session.flush()

        balance = await self._balance(subscription.user_id)
        _record("charge_first" if is_first else "charge_renewal", applied=outcome.applied)
        return ChargeOutcome(
            applied=outcome.applied,
            subscription_id=subscription.id,
            plan_key=plan.plan_key,
            plan_name=_localized_name(plan, language),
            credits=outcome.credits,
            balance=balance,
            period_end=subscription.current_period_end,
            is_first=is_first,
        )

    async def apply_telegram_state(
        self,
        *,
        invoice_payload: str,
        state: str,
        now: datetime | None = None,
    ) -> bool:
        """Record a `BotSubscriptionUpdated` state change.

        Telegram reports `canceled` when the user cancels from its own UI, `active` when
        they re-enable, and `failed` when a renewal could not be collected. None of these
        revoke access: the paid period runs to `current_period_end` regardless, which is
        what Telegram guarantees and therefore what is honoured here.
        """
        moment = now or datetime.now(UTC)
        subscription = await self._by_payload(invoice_payload, for_update=True)
        if subscription is None:
            return False
        if state == "canceled":
            subscription.cancel_at_period_end = True
            subscription.cancelled_at = subscription.cancelled_at or moment
            if subscription.status == SubscriptionStatus.ACTIVE.value:
                subscription.status = SubscriptionStatus.CANCELLING.value
        elif state == "active":
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None
            subscription.renewal_failed_at = None
            if subscription.status in {
                SubscriptionStatus.CANCELLING.value,
                SubscriptionStatus.PAYMENT_FAILED.value,
            }:
                subscription.status = SubscriptionStatus.ACTIVE.value
        elif state == "failed":
            subscription.renewal_failed_at = moment
            subscription.status = SubscriptionStatus.PAYMENT_FAILED.value
        else:
            return False
        await self._session.flush()
        _record(f"telegram_{state}", applied=True)
        return True

    async def request_cancel(
        self,
        user_id: UUID,
        *,
        now: datetime | None = None,
    ) -> CancelRequest:
        """Switch off renewal locally and report what Telegram must be told.

        Local state is written first and the gateway call is left to the caller. If the
        Telegram call fails the user still sees the cancellation they asked for and it can
        be retried; the opposite order risks stopping the billing while our records still
        claim it is running.
        """
        state = await self.cancel(user_id, now=now)
        subscription = await self._subscription_for_update(user_id)
        assert subscription is not None  # cancel() would have raised
        user = await self._session.get(User, user_id)
        if user is None:
            raise SubscriptionNotFoundError(f"User {user_id} not found")
        return CancelRequest(
            subscription_id=state.subscription_id,
            telegram_id=user.telegram_id,
            root_charge_id=subscription.root_charge_id,
            access_until=state.current_period_end,
        )

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

        if subscription.status == SubscriptionStatus.PENDING.value:
            # Never charged, so there is no paid period to run down. Retire it at once,
            # which also frees the one-subscription-per-user slot for a different plan.
            subscription.status = SubscriptionStatus.EXPIRED.value
            subscription.expired_at = moment
            subscription.cancel_at_period_end = False
            await self._session.flush()
            _record("cancel_pending", applied=True)
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
    ) -> int:
        """Expire every subscription whose paid period has run out. Returns how many.

        **This grants nothing.** It used to: the period was renewed locally and the next
        period's credits handed out on that schedule, which meant a subscriber would have
        received credits every 30 days for ever off a single payment. Telegram owns the
        billing clock, so a period is credited if and only if Telegram collected money for
        it — and that happens in `apply_charge`, driven by a real charge.

        This sweep is therefore the counterweight to billing rather than part of it: when
        Telegram stops charging, only this takes the tier away. `current_period_end` is the
        deadline Telegram itself reported, so a user keeps their plan for exactly as long as
        they paid for — including after cancelling, and including after a failed renewal.

        `skip_locked` lets several workers share the queue without blocking each other or
        acting on the same row twice.
        """
        moment = now or datetime.now(UTC)
        result = await self._session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.current_period_end <= moment,
                UserSubscription.status.in_(
                    (
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.CANCELLING.value,
                        SubscriptionStatus.PAYMENT_FAILED.value,
                    )
                ),
            )
            .order_by(UserSubscription.current_period_end)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        expired = 0
        for subscription in result.scalars().all():
            subscription.status = SubscriptionStatus.EXPIRED.value
            subscription.expired_at = moment
            plan = subscription.plan
            user = await self._session.get(User, subscription.user_id)
            # Downgrade only if the user is still on the tier this subscription granted. If
            # they have since moved to another one, a late sweep must not undo it.
            if user is not None and user.plan == plan.plan_key:
                await self._set_user_plan(subscription.user_id, Plan.FREE.value)
            await self._session.flush()
            _record("expire", applied=True)
            expired += 1
        return expired

    async def list_plans(self, language: Language) -> list[dict[str, Any]]:
        """Enabled tiers, cheapest first, localized for display.

        Returns an empty list when subscriptions are gated off, so a caller can render the
        screen unconditionally instead of branching on the flag.
        """
        if not self._settings.subscriptions_enabled:
            return []
        result = await self._session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.enabled.is_(True))
            .order_by(SubscriptionPlan.display_order, SubscriptionPlan.slug)
        )
        plans = []
        for plan in result.scalars():
            localized = _localized(plan.localization, language)
            plans.append(
                {
                    "slug": plan.slug,
                    "plan_key": plan.plan_key,
                    "name": str(localized.get("name") or plan.slug),
                    "description": str(localized.get("description") or ""),
                    "credits_per_period": plan.credits_per_period,
                    "stars": plan.stars,
                    "price_kzt": plan.price_kzt,
                    "period_days": plan.period_days,
                    "referral_percent": plan.referral_percent,
                }
            )
        return plans

    async def get_state(self, user_id: UUID) -> SubscriptionState | None:
        """The user's subscription, or None when they have none or it has expired."""
        result = await self._session.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None or subscription.status == SubscriptionStatus.EXPIRED.value:
            return None
        return self._state(subscription, subscription.plan.slug)

    async def plan_name(self, user_id: UUID, language: Language) -> str:
        result = await self._session.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return ""
        return _localized_name(subscription.plan, language)


def _localized(localization: dict[str, Any], language: Language) -> dict[str, Any]:
    value = localization.get(language.value) or localization.get(Language.RU.value) or {}
    return value if isinstance(value, dict) else {}


def _localized_name(plan: SubscriptionPlan, language: Language) -> str:
    return str(_localized(plan.localization, language).get("name") or plan.slug)


async def process_due_subscriptions(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    """Expire subscriptions whose paid period has run out.

    One transaction for the batch, matching how the service claims rows with SKIP LOCKED.
    A failure rolls back only work that had not been committed, and the next tick re-claims
    the same rows because their deadline has not moved.
    """
    async with session_factory() as session, session.begin():
        return await SubscriptionService(session, settings).process_due(now=now, limit=limit)
