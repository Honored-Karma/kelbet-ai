"""Recurring Telegram Stars subscriptions.

Telegram, not this service, owns the billing clock. `createInvoiceLink` with
`subscription_period=2592000` hands the schedule to Telegram; every 30 days Telegram
charges the user and delivers another `successful_payment` carrying the **original**
`invoice_payload` and a **new** `telegram_payment_charge_id`. Two consequences shape
everything below.

First, a subscription cannot reuse `payment_orders`. That table's payload is unique per
single charge and a partial index allows one processed receipt per order, so the first
renewal would be classified as a duplicate charge requiring a refund. Subscriptions get
their own identity row plus an append-only `subscription_periods` log instead.

Second, granting a period's credits must be exactly-once against redelivery. Telegram
retries updates, and the bot can see the same payment twice. Three independent defences
apply, and a double grant has to defeat all three: the row lock taken on the subscription,
the unique constraint on `subscription_periods.charge_id`, and the wallet ledger's own
idempotency key derived from that same charge id.

What this service deliberately does **not** do is compute expiry dates. `period_end` is
whatever Telegram reported in `subscription_expiration_date`; local arithmetic would drift
away from the clock that actually takes the money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings
from kelbet.db.models import Subscription, SubscriptionPeriod, SubscriptionPlan
from kelbet.domain.enums import Language, Plan, SubscriptionStatus, TxReason
from kelbet.domain.exceptions import (
    IdempotencyConflictError,
    PaymentUnavailableError,
    PaymentValidationError,
    UserNotFoundError,
    WalletNotFoundError,
)
from kelbet.observability import get_metrics
from kelbet.repositories.subscription import SubscriptionRepository
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.payment import payment_new_purchase_allowed
from kelbet.services.wallet import WalletService
from kelbet.subscriptions import (
    MAX_SUBSCRIPTION_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
)

STARS_CURRENCY = "XTR"

SUBSCRIPTION_PAYLOAD_PREFIX = "kelbet-sub"


def is_subscription_payload(invoice_payload: str) -> bool:
    """Route an incoming payment without a database round trip.

    One-off packs use the `kelbet:` prefix and subscriptions `kelbet-sub:`, so the
    successful-payment handler can tell which service owns a charge from the payload alone.
    """
    return invoice_payload.startswith(f"{SUBSCRIPTION_PAYLOAD_PREFIX}:")


def _metric(event: str, outcome: str) -> None:
    get_metrics().incr("subscription.event", tags={"event": event, "outcome": outcome})


@dataclass(frozen=True, slots=True)
class SubscriptionPlanDTO:
    slug: str
    plan: Plan
    name: str
    description: str
    monthly_credits: int
    stars: int
    kzt_price: int | None


@dataclass(frozen=True, slots=True)
class SubscriptionCheckoutDTO:
    """Everything needed to build a recurring invoice link, and nothing more."""

    subscription_id: UUID
    invoice_payload: str
    currency: str
    stars: int
    monthly_credits: int
    plan_slug: str
    plan_name: str
    plan_description: str
    subscription_period_seconds: int
    terms_url: str
    refund_policy_url: str


@dataclass(frozen=True, slots=True)
class SubscriptionStateDTO:
    status: SubscriptionStatus
    plan: Plan
    plan_slug: str
    plan_name: str
    monthly_credits: int
    stars: int
    current_period_end: datetime | None
    cancel_at_period_end: bool
    renewal_count: int
    renewal_failed: bool


@dataclass(frozen=True, slots=True)
class SubscriptionPreCheckoutResult:
    ok: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionChargeResult:
    """Outcome of applying one Telegram charge.

    `applied` distinguishes a real grant from an idempotent replay. `credits` reports the
    grant belonging to this charge either way, so a replay can still answer the user
    correctly rather than reporting zero.
    """

    applied: bool
    subscription_id: UUID | None
    plan: Plan | None
    credits: int
    balance: int | None
    period_end: datetime | None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionCancelResult:
    """What the caller needs in order to tell Telegram to stop renewing."""

    subscription_id: UUID
    telegram_id: int
    root_charge_id: str | None
    current_period_end: datetime | None


class SubscriptionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._subscriptions = SubscriptionRepository(session)
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet_service = WalletService(session)

    # ---------------------------------------------------------------- availability

    def _assert_available(self) -> None:
        if not self._settings.subscriptions_enabled:
            raise PaymentUnavailableError("Subscriptions are not enabled")

    async def list_plans(
        self, language: Language, *, telegram_id: int | None = None
    ) -> list[SubscriptionPlanDTO]:
        """Tiers on offer. Empty when subscriptions or Stars purchases are gated off.

        Returning an empty list rather than raising keeps the caller simple: a profile
        screen asks for the tiers unconditionally and renders nothing when there are none.
        """
        if not self._settings.subscriptions_enabled:
            return []
        if telegram_id is not None and not payment_new_purchase_allowed(
            self._settings, telegram_id
        ):
            return []
        return [self._plan_dto(plan, language) for plan in await self._subscriptions.list_plans()]

    async def get_state(self, user_id: UUID, language: Language) -> SubscriptionStateDTO | None:
        subscription = await self._subscriptions.get_live_for_user(user_id)
        if subscription is None:
            return None
        return self._state_dto(subscription, language)

    # ------------------------------------------------------------------- checkout

    async def start_checkout(
        self,
        *,
        user_id: UUID,
        plan_slug: str,
        idempotency_key: str,
        terms_accepted: bool,
        language: Language,
        accepted_terms_version: str | None = None,
        now: datetime | None = None,
    ) -> SubscriptionCheckoutDTO:
        """Reserve the identity for a subscription and return invoice-link parameters.

        No money moves here and no period is created. The row exists so that the payload
        Telegram will echo back on every renewal already resolves to a known plan and user.
        """
        self._assert_available()
        if not terms_accepted:
            raise PaymentValidationError("Terms must be accepted before subscribing")
        if not idempotency_key or len(idempotency_key) > 128:
            raise PaymentValidationError("Invalid subscription idempotency key")

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        if not payment_new_purchase_allowed(self._settings, user.telegram_id):
            raise PaymentUnavailableError("Telegram Stars payments are not available for this user")
        if accepted_terms_version is not None and (
            accepted_terms_version.strip() != self._settings.payment_terms_version.strip()
        ):
            raise PaymentValidationError("Accepted payment terms are no longer current")
        if accepted_terms_version is None and self._settings.app_env.lower() == "production":
            raise PaymentValidationError("Current payment terms version is required")
        await self._users.assert_paid_operations_allowed(user_id)

        plan = await self._subscriptions.get_plan_by_slug(plan_slug)
        if plan is None or not plan.enabled:
            raise PaymentValidationError(f"Unknown subscription plan {plan_slug}")
        if plan.stars > MAX_SUBSCRIPTION_STARS:
            # Telegram would reject the invoice link. Fail here, where the message is clear,
            # rather than at the API boundary with a provider error.
            raise PaymentValidationError("Subscription price exceeds the Telegram Stars limit")

        existing = await self._subscriptions.get_live_for_user(user_id, for_update=True)
        if existing is not None:
            if existing.plan_id != plan.id:
                # Changing tiers means cancelling the running one first. Two concurrent
                # subscriptions would bill the user twice for overlapping periods.
                raise PaymentValidationError("Cancel the current subscription before switching")
            if existing.status != SubscriptionStatus.PENDING.value:
                raise PaymentValidationError("Subscription is already active")
            _metric("checkout", "reused")
            return self._checkout_dto(existing, plan, language)

        current = now or datetime.now(UTC)
        subscription = Subscription(
            id=uuid4(),
            user_id=user_id,
            plan_id=plan.id,
            status=SubscriptionStatus.PENDING.value,
            plan_snapshot=self._snapshot(plan),
            invoice_payload=f"{SUBSCRIPTION_PAYLOAD_PREFIX}:{uuid4().hex}",
            terms_version=self._settings.payment_terms_version,
            terms_accepted_at=current,
            cancel_at_period_end=False,
            renewal_count=0,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(subscription)
                await self._session.flush()
        except IntegrityError:
            # Lost the race for the one-live-subscription index against a concurrent tap.
            existing = await self._subscriptions.get_live_for_user(user_id)
            if existing is None:
                raise
            if existing.plan_id != plan.id:
                raise IdempotencyConflictError("A different subscription is already live") from None
            _metric("checkout", "raced")
            return self._checkout_dto(existing, plan, language)

        _metric("checkout", "created")
        return self._checkout_dto(subscription, plan, language)

    async def validate_pre_checkout(
        self,
        *,
        telegram_id: int,
        invoice_payload: str,
        currency: str,
        total_amount: int,
    ) -> SubscriptionPreCheckoutResult:
        """Approve or reject Telegram's pre-checkout query for a subscription.

        A subscription payload must never reach `PaymentService.validate_pre_checkout`:
        there is no `payment_orders` row behind it, so that path would answer
        `order_not_found` and Telegram would refuse a perfectly good payment. Routing on
        the payload prefix is what keeps the two apart.

        Unlike a one-off order there is no pre-checkout claim to record. Telegram may open
        the confirmation more than once before the user pays, and rejecting the second
        attempt would strand them.
        """
        subscription = await self._subscriptions.get_by_payload(invoice_payload)
        if subscription is None:
            return SubscriptionPreCheckoutResult(ok=False, error_code="subscription_not_found")
        user = await self._users.get_by_id(subscription.user_id)
        if user is None or user.telegram_id != telegram_id:
            return SubscriptionPreCheckoutResult(ok=False, error_code="buyer_mismatch")
        if not payment_new_purchase_allowed(self._settings, telegram_id):
            return SubscriptionPreCheckoutResult(ok=False, error_code="payments_unavailable")
        if currency != STARS_CURRENCY:
            return SubscriptionPreCheckoutResult(ok=False, error_code="currency_mismatch")
        if total_amount != int(subscription.plan_snapshot["stars"]):
            return SubscriptionPreCheckoutResult(ok=False, error_code="amount_mismatch")
        if subscription.status == SubscriptionStatus.EXPIRED.value:
            return SubscriptionPreCheckoutResult(ok=False, error_code="subscription_expired")
        return SubscriptionPreCheckoutResult(ok=True)

    # ---------------------------------------------------------------------- money

    async def apply_successful_payment(
        self,
        *,
        telegram_id: int,
        invoice_payload: str,
        currency: str,
        total_amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None,
        subscription_expiration_date: datetime | None,
        is_first_recurring: bool = False,
        now: datetime | None = None,
    ) -> SubscriptionChargeResult:
        """Grant one paid period. Safe to call repeatedly with the same charge id.

        Ordering matters: the subscription row is locked first, so two deliveries of the
        same charge serialise instead of both reading "no period yet" and both granting.
        """
        current = now or datetime.now(UTC)

        subscription = await self._subscriptions.get_by_payload(invoice_payload, for_update=True)
        if subscription is None:
            _metric("charge", "unknown_payload")
            return self._charge_failure(None, "subscription_not_found")

        plan = await self._subscriptions.get_plan_by_id(subscription.plan_id)
        user = await self._users.get_by_id(subscription.user_id)
        if user is None or plan is None:
            _metric("charge", "orphaned")
            return self._charge_failure(subscription, "subscription_orphaned")
        if user.telegram_id != telegram_id:
            _metric("charge", "buyer_mismatch")
            return self._charge_failure(subscription, "buyer_mismatch")
        if currency != STARS_CURRENCY:
            _metric("charge", "currency_mismatch")
            return self._charge_failure(subscription, "currency_mismatch")

        # The snapshot, not the plan row, is the agreed price. A repriced plan must not
        # retroactively make an existing subscriber's charge look wrong.
        agreed_stars = int(subscription.plan_snapshot["stars"])
        agreed_credits = int(subscription.plan_snapshot["monthly_credits"])
        if total_amount != agreed_stars:
            _metric("charge", "amount_mismatch")
            return self._charge_failure(subscription, "amount_mismatch")

        replay = await self._subscriptions.get_period_by_charge_id(telegram_payment_charge_id)
        if replay is not None:
            wallet = await self._wallets.get_by_user_id(subscription.user_id)
            _metric("charge", "replay")
            return SubscriptionChargeResult(
                applied=False,
                subscription_id=subscription.id,
                plan=Plan(plan.plan),
                credits=replay.credits_granted,
                balance=wallet.balance if wallet is not None else None,
                period_end=replay.period_end,
            )

        wallet = await self._wallets.get_by_user_id(subscription.user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {subscription.user_id} not found")

        # Whether this is the opening charge is decided by our own records, not by
        # Telegram's `is_first_recurring` flag and not by `renewal_count`. The flag is
        # absent on renewals but we cannot depend on an optional field to classify money,
        # and `renewal_count` is still 0 during the first period, so testing it would make
        # every later charge look like a first one — losing the renewal count and failing
        # to notice that a cancelled subscription had been re-enabled.
        is_first = subscription.root_charge_id is None
        if is_first_recurring != is_first:
            # Our records and Telegram's flag disagree. Ours wins, but a persistent
            # disagreement means one of the two assumptions is wrong and is worth seeing.
            _metric("charge", "first_flag_disagreement")
        period = SubscriptionPeriod(
            id=uuid4(),
            subscription_id=subscription.id,
            charge_id=telegram_payment_charge_id,
            provider_charge_id=provider_payment_charge_id or None,
            stars_amount=total_amount,
            credits_granted=agreed_credits,
            is_first=is_first,
            period_start=current,
            period_end=subscription_expiration_date,
            created_at=current,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(period)
                await self._session.flush()
        except IntegrityError:
            # The unique charge id fired: another delivery beat us between the lookup and
            # the insert. Treat it as the replay it is.
            existing_period = await self._subscriptions.get_period_by_charge_id(
                telegram_payment_charge_id
            )
            if existing_period is None:
                raise
            _metric("charge", "replay")
            return SubscriptionChargeResult(
                applied=False,
                subscription_id=subscription.id,
                plan=Plan(plan.plan),
                credits=existing_period.credits_granted,
                balance=wallet.balance,
                period_end=existing_period.period_end,
            )

        credit = await self._wallet_service.credit(
            wallet.id,
            agreed_credits,
            TxReason.PLAN_GRANT,
            f"subscription:{telegram_payment_charge_id}",
            meta={
                "subscription_id": str(subscription.id),
                "plan": plan.plan,
                "plan_slug": plan.slug,
                "stars": total_amount,
                "telegram_payment_charge_id": telegram_payment_charge_id,
                "is_first_period": is_first,
            },
        )
        period.ledger_transaction_id = credit.transaction_id

        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.current_period_start = current
        subscription.current_period_end = subscription_expiration_date
        subscription.renewal_failed_at = None
        subscription.expired_at = None
        if is_first:
            subscription.root_charge_id = telegram_payment_charge_id
        else:
            subscription.renewal_count += 1
        # A cancelled subscription that charges again means the user re-enabled it.
        if subscription.cancel_at_period_end and not is_first:
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None

        user.plan = plan.plan
        await self._session.flush()
        _metric("charge", "first" if is_first else "renewal")
        return SubscriptionChargeResult(
            applied=credit.applied,
            subscription_id=subscription.id,
            plan=Plan(plan.plan),
            credits=agreed_credits,
            balance=credit.balance,
            period_end=subscription.current_period_end,
        )

    # --------------------------------------------------------------- state changes

    async def apply_telegram_state(
        self,
        *,
        invoice_payload: str,
        state: str,
        now: datetime | None = None,
    ) -> bool:
        """Record a `BotSubscriptionUpdated` state change.

        Telegram reports `canceled` when the *user* cancels from its own UI, `active` when
        they re-enable, and `failed` when a renewal could not be collected. None of these
        revoke access: the paid period runs to `current_period_end` regardless, which is
        what Telegram guarantees and therefore what we honour.
        """
        current = now or datetime.now(UTC)
        subscription = await self._subscriptions.get_by_payload(invoice_payload, for_update=True)
        if subscription is None:
            _metric("telegram_state", "unknown_payload")
            return False
        if state == "canceled":
            subscription.cancel_at_period_end = True
            subscription.cancelled_at = subscription.cancelled_at or current
            if subscription.status == SubscriptionStatus.ACTIVE.value:
                subscription.status = SubscriptionStatus.CANCELLED.value
        elif state == "active":
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None
            subscription.renewal_failed_at = None
            if subscription.status in {
                SubscriptionStatus.CANCELLED.value,
                SubscriptionStatus.PAYMENT_FAILED.value,
            }:
                subscription.status = SubscriptionStatus.ACTIVE.value
        elif state == "failed":
            subscription.renewal_failed_at = current
            subscription.status = SubscriptionStatus.PAYMENT_FAILED.value
        else:
            _metric("telegram_state", "unknown_state")
            return False
        await self._session.flush()
        _metric("telegram_state", state)
        return True

    async def request_cancel(
        self,
        *,
        user_id: UUID,
        now: datetime | None = None,
    ) -> SubscriptionCancelResult:
        """Switch off renewal locally and report what Telegram needs to be told.

        The local state is written first and the gateway call is left to the caller on
        purpose. If the Telegram call fails, the user still sees the cancellation they
        asked for and the reconciliation path can retry the remote side; the opposite
        order risks stopping the billing while our records still claim it is running.
        """
        current = now or datetime.now(UTC)
        subscription = await self._subscriptions.get_live_for_user(user_id, for_update=True)
        if subscription is None:
            raise PaymentValidationError("No active subscription to cancel")
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")

        subscription.cancel_at_period_end = True
        subscription.cancelled_at = subscription.cancelled_at or current
        if subscription.status == SubscriptionStatus.ACTIVE.value:
            subscription.status = SubscriptionStatus.CANCELLED.value
        elif subscription.status == SubscriptionStatus.PENDING.value:
            # Never charged, so there is no period to run out. Retire it immediately,
            # which also frees the one-live-subscription slot.
            subscription.status = SubscriptionStatus.EXPIRED.value
            subscription.expired_at = current
        await self._session.flush()
        _metric("cancel", "requested")
        return SubscriptionCancelResult(
            subscription_id=subscription.id,
            telegram_id=user.telegram_id,
            root_charge_id=subscription.root_charge_id,
            current_period_end=subscription.current_period_end,
        )

    async def expire_one_due(self, *, now: datetime | None = None) -> bool:
        """Retire one subscription whose paid period has ended. Returns whether it acted.

        This is the only place a plan is downgraded. It is driven by `current_period_end`,
        the date Telegram gave us, so a user keeps their tier for exactly as long as they
        paid for it — including after cancelling.
        """
        current = now or datetime.now(UTC)
        subscription = await self._subscriptions.claim_expired(current)
        if subscription is None:
            return False
        subscription.status = SubscriptionStatus.EXPIRED.value
        subscription.expired_at = current
        user = await self._users.get_by_id_for_update(subscription.user_id)
        # Downgrade only if the user is still on the tier this subscription granted. If
        # they have since moved to another tier, a late-arriving expiry must not undo it.
        if user is not None and user.plan == str(subscription.plan_snapshot.get("plan")):
            user.plan = Plan.FREE.value
        await self._session.flush()
        _metric("expire", "expired")
        return True

    # ------------------------------------------------------------------------ DTOs

    def _snapshot(self, plan: SubscriptionPlan) -> dict[str, Any]:
        return {
            "slug": plan.slug,
            "plan": plan.plan,
            "monthly_credits": plan.monthly_credits,
            "stars": plan.stars,
            "kzt_price": plan.kzt_price,
            "localization": plan.localization,
        }

    def _plan_dto(self, plan: SubscriptionPlan, language: Language) -> SubscriptionPlanDTO:
        localized = _localized(plan.localization, language)
        return SubscriptionPlanDTO(
            slug=plan.slug,
            plan=Plan(plan.plan),
            name=str(localized.get("name") or plan.slug),
            description=str(localized.get("description") or ""),
            monthly_credits=plan.monthly_credits,
            stars=plan.stars,
            kzt_price=plan.kzt_price,
        )

    def _checkout_dto(
        self,
        subscription: Subscription,
        plan: SubscriptionPlan,
        language: Language,
    ) -> SubscriptionCheckoutDTO:
        snapshot = subscription.plan_snapshot
        localization = snapshot.get("localization")
        localized = _localized(localization if isinstance(localization, dict) else {}, language)
        return SubscriptionCheckoutDTO(
            subscription_id=subscription.id,
            invoice_payload=subscription.invoice_payload,
            currency=STARS_CURRENCY,
            stars=int(snapshot["stars"]),
            monthly_credits=int(snapshot["monthly_credits"]),
            plan_slug=str(snapshot.get("slug") or plan.slug),
            plan_name=str(localized.get("name") or plan.slug),
            plan_description=str(localized.get("description") or ""),
            subscription_period_seconds=SUBSCRIPTION_PERIOD_SECONDS,
            terms_url=self._settings.payment_terms_url,
            refund_policy_url=self._settings.payment_refund_policy_url,
        )

    def _state_dto(self, subscription: Subscription, language: Language) -> SubscriptionStateDTO:
        snapshot = subscription.plan_snapshot
        localization = snapshot.get("localization")
        localized = _localized(localization if isinstance(localization, dict) else {}, language)
        return SubscriptionStateDTO(
            status=SubscriptionStatus(subscription.status),
            plan=Plan(str(snapshot["plan"])),
            plan_slug=str(snapshot.get("slug") or ""),
            plan_name=str(localized.get("name") or snapshot.get("slug") or ""),
            monthly_credits=int(snapshot["monthly_credits"]),
            stars=int(snapshot["stars"]),
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            renewal_count=subscription.renewal_count,
            renewal_failed=subscription.renewal_failed_at is not None,
        )

    def _charge_failure(
        self,
        subscription: Subscription | None,
        error_code: str,
    ) -> SubscriptionChargeResult:
        return SubscriptionChargeResult(
            applied=False,
            subscription_id=subscription.id if subscription is not None else None,
            plan=None,
            credits=0,
            balance=None,
            period_end=None,
            error_code=error_code,
        )


def _localized(localization: dict[str, Any], language: Language) -> dict[str, Any]:
    value = localization.get(language.value) or localization.get(Language.RU.value) or {}
    return value if isinstance(value, dict) else {}


async def process_due_subscriptions(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    """Expire subscriptions whose paid period has run out.

    One transaction per subscription, matching the refund and referral workers. A batch in
    a single transaction would mean one bad row rolls back the downgrades that already
    succeeded, and would hold every claimed row's lock for the whole batch.
    """
    current = now or datetime.now(UTC)
    processed = 0
    for _ in range(max(1, min(limit, 500))):
        async with session_factory() as session, session.begin():
            changed = await SubscriptionService(session, settings).expire_one_due(now=current)
        if not changed:
            break
        processed += 1
    return processed
