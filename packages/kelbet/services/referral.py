from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.config import Settings, get_settings
from kelbet.db.models import ReferralAttribution, ReferralReward
from kelbet.domain.enums import PaymentReceiptStatus, PaymentStatus, ReferralRewardStatus, TxReason
from kelbet.observability import get_metrics
from kelbet.repositories.payment import PaymentRepository
from kelbet.repositories.referral import ReferralRepository
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.catalog import FeatureFlagService
from kelbet.services.wallet import WalletService

_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


@dataclass(frozen=True, slots=True)
class ReferralSummary:
    enabled: bool
    code: str | None
    link: str | None
    invited_count: int
    pending_rewards_count: int
    credited_rewards_count: int
    credited_bonus_credits: int
    inviter_bonus_credits: int
    invitee_bonus_credits: int
    minimum_purchase_stars: int
    waiting_period_hours: int


def _metric(stage: str, outcome: str) -> None:
    get_metrics().incr("referral.funnel", tags={"stage": stage, "outcome": outcome})


class ReferralService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._referrals = ReferralRepository(session)
        self._payments = PaymentRepository(session)
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet = WalletService(session)

    async def is_enabled_for(self, telegram_id: int) -> bool:
        return await FeatureFlagService(self._session).is_enabled(
            "referrals", telegram_id=telegram_id
        )

    async def get_summary(self, user_id: UUID) -> ReferralSummary:
        user = await self._users.get_by_id(user_id)
        if user is None:
            return self._empty_summary()
        bot_username = self._settings.referral_bot_username.strip().lstrip("@")
        enabled = await self.is_enabled_for(user.telegram_id)
        enabled = enabled and _BOT_USERNAME_RE.fullmatch(bot_username) is not None
        if not enabled:
            return self._empty_summary()
        code = await self._get_or_create_code(user_id)
        counts = await self._referrals.summary_for_inviter(user_id)
        return ReferralSummary(
            enabled=True,
            code=code,
            link=f"https://t.me/{bot_username}?start=ref_{code}",
            inviter_bonus_credits=max(0, self._settings.referral_inviter_bonus_credits),
            invitee_bonus_credits=max(0, self._settings.referral_invitee_bonus_credits),
            minimum_purchase_stars=max(1, self._settings.referral_minimum_purchase_stars),
            waiting_period_hours=max(0, self._settings.referral_waiting_period_hours),
            **counts,
        )

    async def attribute_new_user(
        self,
        *,
        invited_user_id: UUID,
        code: str | None,
        created_in_registration: bool = False,
        now: datetime | None = None,
    ) -> ReferralAttribution | None:
        if not created_in_registration:
            _metric("attribution", "not_new")
            return None
        invited = await self._users.get_by_id(invited_user_id)
        if invited is None or not await self.is_enabled_for(invited.telegram_id):
            _metric("attribution", "disabled")
            return None
        clean = (code or "").strip()
        if _CODE_RE.fullmatch(clean) is None:
            _metric("attribution", "invalid")
            return None
        existing = await self._referrals.get_attribution_for_invited(invited_user_id)
        if existing is not None:
            _metric("attribution", "existing")
            return existing
        referral_code = await self._referrals.get_code(clean)
        if referral_code is None:
            _metric("attribution", "unknown")
            return None
        if referral_code.user_id == invited_user_id:
            _metric("attribution", "self")
            return None
        current = now or datetime.now(UTC)
        try:
            async with self._session.begin_nested():
                attribution, _reward = await self._referrals.create_attribution(
                    code=referral_code,
                    invited_user_id=invited_user_id,
                    now=current,
                    inviter_bonus_credits=max(0, self._settings.referral_inviter_bonus_credits),
                    invitee_bonus_credits=max(0, self._settings.referral_invitee_bonus_credits),
                )
        except IntegrityError:
            existing_after_race = await self._referrals.get_attribution_for_invited(invited_user_id)
            if existing_after_race is None:
                raise
            _metric("attribution", "race_replay")
            return existing_after_race
        _metric("attribution", "created")
        return attribution

    async def observe_reconciled_purchase(
        self, order_id: UUID, *, now: datetime | None = None
    ) -> ReferralReward | None:
        current = now or datetime.now(UTC)
        order = await self._payments.get_order_by_id(order_id, for_update=True)
        if order is None or order.status != PaymentStatus.PAID.value:
            return None
        invited = await self._users.get_by_id(order.user_id)
        if invited is None or not await self.is_enabled_for(invited.telegram_id):
            return None
        attribution = await self._referrals.get_attribution_for_invited(
            order.user_id, for_update=True
        )
        if attribution is None:
            return None
        reward = await self._referrals.get_reward_for_attribution(attribution.id, for_update=True)
        if reward is None or reward.status != ReferralRewardStatus.PENDING.value:
            return reward
        receipt = await self._payments.get_receipt_by_order_id(order.id)
        if receipt is None or receipt.status != PaymentReceiptStatus.PROCESSED.value:
            return reward
        observation = await self._payments.get_observation(
            receipt.telegram_payment_charge_id, "incoming"
        )
        if observation is None:
            return reward
        first = await self._payments.get_first_paid_order_for_user(order.user_id)
        if first is None or first.id != order.id:
            return reward
        reward.payment_order_id = order.id
        if order.total_amount < max(1, self._settings.referral_minimum_purchase_stars):
            reward.status = ReferralRewardStatus.CANCELLED.value
            reward.cancelled_at = current
            reward.review_reason = "first_purchase_below_minimum"
            _metric("first_purchase", "below_minimum")
            await self._session.flush()
            return reward
        since = current - timedelta(hours=24)
        recent = await self._referrals.count_attributions_since(attribution.inviter_user_id, since)
        if recent > max(1, self._settings.referral_suspicious_daily_attribution_threshold):
            reward.status = ReferralRewardStatus.NEEDS_REVIEW.value
            reward.review_reason = "attribution_velocity"
            _metric("first_purchase", "needs_review")
            await self._session.flush()
            return reward
        reward.status = ReferralRewardStatus.ELIGIBLE.value
        reward.eligible_at = observation.occurred_at + timedelta(
            hours=max(0, self._settings.referral_waiting_period_hours)
        )
        reward.review_reason = None
        _metric("first_purchase", "eligible")
        await self._session.flush()
        return reward

    async def observe_payment_reversal(
        self, order_id: UUID, *, now: datetime | None = None
    ) -> ReferralReward | None:
        reward = await self._referrals.get_reward_for_payment(order_id, for_update=True)
        if reward is None:
            return None
        current = now or datetime.now(UTC)
        if reward.status in {
            ReferralRewardStatus.PENDING.value,
            ReferralRewardStatus.ELIGIBLE.value,
        }:
            reward.status = ReferralRewardStatus.CANCELLED.value
            reward.cancelled_at = current
            reward.review_reason = "payment_reversed_before_credit"
            _metric("reversal", "cancelled")
        elif reward.status == ReferralRewardStatus.CREDITED.value:
            reward.status = ReferralRewardStatus.NEEDS_REVIEW.value
            reward.review_reason = "payment_reversed_after_credit"
            _metric("reversal", "needs_review")
        await self._session.flush()
        return reward

    async def credit_one_due(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        reward = await self._referrals.claim_due_reward(current)
        if reward is None:
            return False
        attribution = await self._referrals.get_attribution(reward.attribution_id)
        if attribution is None:
            reward.status = ReferralRewardStatus.NEEDS_REVIEW.value
            reward.review_reason = "attribution_missing"
            return True
        invited = await self._users.get_by_id(attribution.invited_user_id)
        if invited is None or not await self.is_enabled_for(invited.telegram_id):
            return False
        order = (
            await self._payments.get_order_by_id(reward.payment_order_id, for_update=True)
            if reward.payment_order_id is not None
            else None
        )
        if order is None or order.status != PaymentStatus.PAID.value:
            reward.status = ReferralRewardStatus.CANCELLED.value
            reward.cancelled_at = current
            reward.review_reason = "payment_not_active"
            _metric("reward", "cancelled")
            return True

        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        await self._referrals.lock_inviter_day(
            attribution.inviter_user_id, day_start.date().isoformat()
        )
        credited_today = await self._referrals.count_credited_for_inviter_since(
            attribution.inviter_user_id, day_start
        )
        if credited_today >= max(1, self._settings.referral_daily_reward_limit):
            reward.eligible_at = day_start + timedelta(days=1)
            _metric("reward", "daily_limited")
            return True

        inviter_wallet = await self._wallets.get_by_user_id(attribution.inviter_user_id)
        invitee_wallet = await self._wallets.get_by_user_id(attribution.invited_user_id)
        if inviter_wallet is None or invitee_wallet is None:
            reward.status = ReferralRewardStatus.NEEDS_REVIEW.value
            reward.review_reason = "wallet_missing"
            _metric("reward", "needs_review")
            return True
        if reward.inviter_bonus_credits > 0:
            result = await self._wallet.credit(
                inviter_wallet.id,
                reward.inviter_bonus_credits,
                TxReason.REFERRAL_REWARD,
                f"referral:{reward.id}:inviter",
                meta={"referral_reward_id": str(reward.id), "role": "inviter"},
            )
            reward.inviter_ledger_transaction_id = result.transaction_id
        if reward.invitee_bonus_credits > 0:
            result = await self._wallet.credit(
                invitee_wallet.id,
                reward.invitee_bonus_credits,
                TxReason.REFERRAL_REWARD,
                f"referral:{reward.id}:invitee",
                meta={"referral_reward_id": str(reward.id), "role": "invitee"},
            )
            reward.invitee_ledger_transaction_id = result.transaction_id
        reward.status = ReferralRewardStatus.CREDITED.value
        reward.credited_at = current
        reward.review_reason = None
        _metric("reward", "credited")
        await self._session.flush()
        return True

    async def list_for_operator(
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

    async def _get_or_create_code(self, user_id: UUID) -> str:
        existing = await self._referrals.get_code_for_user(user_id)
        if existing is not None:
            return existing.code
        for _ in range(5):
            candidate = secrets.token_urlsafe(9)
            try:
                async with self._session.begin_nested():
                    row = await self._referrals.create_code(user_id=user_id, code=candidate)
                return row.code
            except IntegrityError:
                existing = await self._referrals.get_code_for_user(user_id)
                if existing is not None:
                    return existing.code
        raise RuntimeError("Could not allocate a unique referral code")

    def _empty_summary(self) -> ReferralSummary:
        return ReferralSummary(
            enabled=False,
            code=None,
            link=None,
            invited_count=0,
            pending_rewards_count=0,
            credited_rewards_count=0,
            credited_bonus_credits=0,
            inviter_bonus_credits=max(0, self._settings.referral_inviter_bonus_credits),
            invitee_bonus_credits=max(0, self._settings.referral_invitee_bonus_credits),
            minimum_purchase_stars=max(1, self._settings.referral_minimum_purchase_stars),
            waiting_period_hours=max(0, self._settings.referral_waiting_period_hours),
        )


async def process_due_referral_rewards(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> int:
    current = now or datetime.now(UTC)
    processed = 0
    for _ in range(max(1, min(limit, 100))):
        async with session_factory() as session, session.begin():
            changed = await ReferralService(session, settings).credit_one_due(now=current)
        if not changed:
            break
        processed += 1
    return processed
