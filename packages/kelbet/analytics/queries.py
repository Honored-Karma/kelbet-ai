"""Product and unit-economics analytics computed from the operational tables.

## Why there is no events table

The obvious way to build analytics is an append-only event log plus instrumentation
at every interesting call site. This module deliberately does not do that, for three
reasons that all point the same way.

First, an event log only knows what happened after it shipped. Every number would
start at zero on deploy day, and the question a funder actually asks — "what has this
product done so far" — would stay unanswerable for weeks. Everything below is
computed from rows the product has been writing since July, so the history exists
already.

Second, the write path here moves money. Adding an insert to `POST /generations` and
to the payment handlers buys reporting at the cost of a new way for a paid request to
fail. That trade is bad while the same numbers are already derivable.

Third, the tables happen to be unusually well suited to it. `provider_usage` records
`provider_cost_units` next to `user_credit_price` for every attempt, so the margin on
delivery is a `SUM` rather than a reconstruction, and `auth_sessions` is minted only
by the Mini App auth exchange, which makes it an honest "opened the app" signal.

An event log becomes the right next step once these numbers show *which* step leaks —
at that point the instrumentation is narrow and purposeful rather than speculative.

## The two margins, and why one number is not enough

Credits are sold in packs and spent on generations, so a single "margin" figure hides
which half of the business is healthy:

* **Pack margin** — cash Telegram pays out for Stars, against the credit liability
  those Stars created. This is the margin the payment catalog is priced for.
* **Delivery margin** — the credit liability actually consumed, against the cash paid
  to providers for it. A SKU priced below its provider cost shows up here and nowhere
  else, and it is the failure that scales with usage.

Both are reported. `credits_charged * CREDIT_COST_UNITS` is the budget a generation
was allowed to spend; `provider_cost_units` is what it did spend.

## Definitions that could otherwise be argued about

`funnel` is **cohort-based**: the base is users who registered inside the window, and
each later step counts those same users whenever they reached it. A period funnel —
everything that happened in the window regardless of when the user arrived — reads
higher and means less, because a user who registered in March and paid today would
be counted as a conversion of today's traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.seeds import CREDIT_COST_UNITS
from kelbet.db.models import (
    AuthSession,
    GenerationJob,
    PaymentOrder,
    PaymentRefund,
    ProviderUsage,
    User,
)
from kelbet.domain.enums import GenerationStatus
from kelbet.payments.seeds import CREDIT_COST_USD, STAR_PAYOUT_USD

#: `provider_cost_units` and every other cost unit in the project is USD fixed point.
COST_UNITS_PER_USD = 10_000


def _usd(cost_units: int) -> float:
    return round(cost_units / COST_UNITS_PER_USD, 4)


def _ratio(part: int, whole: int) -> float:
    """Share of `whole`, as a fraction. Zero base means zero, never a division error."""
    if whole <= 0:
        return 0.0
    return round(part / whole, 4)


@dataclass(frozen=True, slots=True)
class FunnelStep:
    key: str
    users: int
    #: Share of the cohort base, so the whole funnel reads against one denominator.
    of_cohort: float
    #: Share of the previous step, which is where a leak is actually visible.
    of_previous: float


@dataclass(frozen=True, slots=True)
class CohortFunnel:
    cohort_users: int
    steps: list[FunnelStep]

    @property
    def activation_rate(self) -> float:
        """Registered users who got at least one finished generation."""
        for step in self.steps:
            if step.key == "generation_succeeded":
                return step.of_cohort
        return 0.0

    @property
    def paid_conversion_rate(self) -> float:
        for step in self.steps:
            if step.key == "payment_succeeded":
                return step.of_cohort
        return 0.0


@dataclass(frozen=True, slots=True)
class UsageSummary:
    active_users: int
    new_users: int
    generations_started: int
    generations_succeeded: int
    generations_failed: int
    credits_spent: int

    @property
    def success_rate(self) -> float:
        return _ratio(self.generations_succeeded, self.generations_started)


@dataclass(frozen=True, slots=True)
class RevenueSummary:
    orders_paid: int
    paying_users: int
    stars_collected: int
    credits_sold: int
    stars_refunded: int
    credits_refunded: int

    @property
    def gross_usd(self) -> float:
        return round(self.stars_collected * STAR_PAYOUT_USD, 4)

    @property
    def refunded_usd(self) -> float:
        return round(self.stars_refunded * STAR_PAYOUT_USD, 4)

    @property
    def net_usd(self) -> float:
        return round(self.gross_usd - self.refunded_usd, 4)

    @property
    def credit_liability_usd(self) -> float:
        """Provider cash the sold credits entitle their buyers to spend."""
        net_credits = max(0, self.credits_sold - self.credits_refunded)
        return round(net_credits * CREDIT_COST_USD, 4)

    @property
    def pack_margin(self) -> float:
        """Cash in, less the provider spend those credits can command."""
        if self.net_usd <= 0:
            return 0.0
        return round((self.net_usd - self.credit_liability_usd) / self.net_usd, 4)

    @property
    def arpu_usd(self) -> float:
        if self.paying_users <= 0:
            return 0.0
        return round(self.net_usd / self.paying_users, 4)


@dataclass(frozen=True, slots=True)
class ProviderEconomics:
    provider: str
    provider_model_id: str
    modality: str
    generations: int
    provider_cost_units: int
    credits_charged: int
    avg_latency_ms: int | None

    @property
    def provider_cost_usd(self) -> float:
        return _usd(self.provider_cost_units)

    @property
    def charged_budget_units(self) -> int:
        """What the charged credits were allowed to spend, in provider cost units."""
        return self.credits_charged * CREDIT_COST_UNITS

    @property
    def delivery_margin(self) -> float:
        """Share of the charged budget not consumed by the provider.

        Negative means the route is sold below what it costs to serve — the one
        failure that grows with every additional user.
        """
        budget = self.charged_budget_units
        if budget <= 0:
            return 0.0
        return round((budget - self.provider_cost_units) / budget, 4)


@dataclass(frozen=True, slots=True)
class RetentionPoint:
    day: int
    cohort_users: int
    returned_users: int

    @property
    def rate(self) -> float:
        return _ratio(self.returned_users, self.cohort_users)


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    since: datetime
    until: datetime
    usage: UsageSummary
    funnel: CohortFunnel
    revenue: RevenueSummary
    providers: list[ProviderEconomics]
    retention: list[RetentionPoint]

    @property
    def total_provider_cost_usd(self) -> float:
        return round(sum(row.provider_cost_usd for row in self.providers), 4)

    @property
    def contribution_usd(self) -> float:
        """Cash collected in the window, less cash paid to providers in it.

        Not accrual accounting: credits bought last month can be spent today. It is
        still the number that answers "is this burning money per user".
        """
        return round(self.revenue.net_usd - self.total_provider_cost_usd, 4)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _scalar_int(self, statement: Select[Any]) -> int:
        value = await self._session.scalar(statement)
        return int(value or 0)

    async def usage(self, *, since: datetime, until: datetime) -> UsageSummary:
        # A session row is created only by the Mini App auth exchange, which makes
        # distinct users here "opened the app", not merely "exists".
        active = await self._scalar_int(
            select(func.count(func.distinct(AuthSession.user_id))).where(
                AuthSession.created_at >= since, AuthSession.created_at < until
            )
        )
        new_users = await self._scalar_int(
            select(func.count(User.id)).where(User.created_at >= since, User.created_at < until)
        )
        started = await self._scalar_int(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.created_at >= since, GenerationJob.created_at < until
            )
        )
        succeeded = await self._scalar_int(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.created_at >= since,
                GenerationJob.created_at < until,
                GenerationJob.status == GenerationStatus.SUCCEEDED.value,
            )
        )
        failed = await self._scalar_int(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.created_at >= since,
                GenerationJob.created_at < until,
                GenerationJob.status.in_(
                    [
                        GenerationStatus.FAILED.value,
                        GenerationStatus.TIMED_OUT.value,
                        GenerationStatus.DEAD_LETTER.value,
                    ]
                ),
            )
        )
        # Credits actually consumed by delivered work, taken from the usage rows
        # rather than the ledger: the ledger also carries bonuses and refunds.
        credits_spent = await self._scalar_int(
            select(func.coalesce(func.sum(ProviderUsage.user_credit_price), 0)).where(
                ProviderUsage.created_at >= since, ProviderUsage.created_at < until
            )
        )
        return UsageSummary(
            active_users=active,
            new_users=new_users,
            generations_started=started,
            generations_succeeded=succeeded,
            generations_failed=failed,
            credits_spent=credits_spent,
        )

    async def funnel(self, *, since: datetime, until: datetime) -> CohortFunnel:
        cohort = select(User.id).where(User.created_at >= since, User.created_at < until)
        cohort_users = await self._scalar_int(select(func.count()).select_from(cohort.subquery()))

        opened = await self._scalar_int(
            select(func.count(func.distinct(AuthSession.user_id))).where(
                AuthSession.user_id.in_(cohort)
            )
        )
        requested = await self._scalar_int(
            select(func.count(func.distinct(GenerationJob.user_id))).where(
                GenerationJob.user_id.in_(cohort)
            )
        )
        delivered = await self._scalar_int(
            select(func.count(func.distinct(GenerationJob.user_id))).where(
                GenerationJob.user_id.in_(cohort),
                GenerationJob.status == GenerationStatus.SUCCEEDED.value,
            )
        )
        checkout = await self._scalar_int(
            select(func.count(func.distinct(PaymentOrder.user_id))).where(
                PaymentOrder.user_id.in_(cohort)
            )
        )
        paid = await self._scalar_int(
            select(func.count(func.distinct(PaymentOrder.user_id))).where(
                PaymentOrder.user_id.in_(cohort), PaymentOrder.paid_at.is_not(None)
            )
        )

        counts = [
            ("registered", cohort_users),
            ("app_opened", opened),
            ("generation_requested", requested),
            ("generation_succeeded", delivered),
            ("checkout_started", checkout),
            ("payment_succeeded", paid),
        ]
        steps: list[FunnelStep] = []
        previous = cohort_users
        for key, value in counts:
            steps.append(
                FunnelStep(
                    key=key,
                    users=value,
                    of_cohort=_ratio(value, cohort_users),
                    of_previous=_ratio(value, previous),
                )
            )
            previous = value
        return CohortFunnel(cohort_users=cohort_users, steps=steps)

    async def revenue(self, *, since: datetime, until: datetime) -> RevenueSummary:
        # Paid orders are the source of truth for money in: a receipt can exist for a
        # charge Telegram later reversed, while paid_at is set when credits were granted.
        paid_window = (
            PaymentOrder.paid_at.is_not(None),
            PaymentOrder.paid_at >= since,
            PaymentOrder.paid_at < until,
        )
        orders_paid = await self._scalar_int(
            select(func.count(PaymentOrder.id)).where(*paid_window)
        )
        paying_users = await self._scalar_int(
            select(func.count(func.distinct(PaymentOrder.user_id))).where(*paid_window)
        )
        stars = await self._scalar_int(
            select(func.coalesce(func.sum(PaymentOrder.total_amount), 0)).where(*paid_window)
        )
        credits_sold = await self._scalar_int(
            select(func.coalesce(func.sum(PaymentOrder.credits), 0)).where(*paid_window)
        )

        refund_window = (
            PaymentRefund.external_refunded_at.is_not(None),
            PaymentRefund.external_refunded_at >= since,
            PaymentRefund.external_refunded_at < until,
        )
        stars_refunded = await self._scalar_int(
            select(func.coalesce(func.sum(PaymentRefund.stars_amount), 0)).where(*refund_window)
        )
        credits_refunded = await self._scalar_int(
            select(func.coalesce(func.sum(PaymentRefund.credits_amount), 0)).where(*refund_window)
        )
        return RevenueSummary(
            orders_paid=orders_paid,
            paying_users=paying_users,
            stars_collected=stars,
            credits_sold=credits_sold,
            stars_refunded=stars_refunded,
            credits_refunded=credits_refunded,
        )

    async def provider_economics(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> list[ProviderEconomics]:
        statement = (
            select(
                ProviderUsage.provider,
                ProviderUsage.provider_model_id,
                ProviderUsage.modality,
                func.count(ProviderUsage.id),
                func.coalesce(func.sum(ProviderUsage.provider_cost_units), 0),
                func.coalesce(func.sum(ProviderUsage.user_credit_price), 0),
                func.avg(ProviderUsage.latency_ms),
            )
            .where(ProviderUsage.created_at >= since, ProviderUsage.created_at < until)
            .group_by(
                ProviderUsage.provider,
                ProviderUsage.provider_model_id,
                ProviderUsage.modality,
            )
            .order_by(func.coalesce(func.sum(ProviderUsage.provider_cost_units), 0).desc())
        )
        rows = (await self._session.execute(statement)).all()
        return [
            ProviderEconomics(
                provider=row[0],
                provider_model_id=row[1],
                modality=row[2],
                generations=int(row[3] or 0),
                provider_cost_units=int(row[4] or 0),
                credits_charged=int(row[5] or 0),
                avg_latency_ms=int(row[6]) if row[6] is not None else None,
            )
            for row in rows
        ]

    async def retention(
        self, *, since: datetime, until: datetime, days: tuple[int, ...]
    ) -> list[RetentionPoint]:
        """Share of a registration cohort that opened the app again on day N.

        The cohort is closed off before measuring: a user who registered yesterday
        cannot yet have a day-7 outcome, and counting them as a miss would understate
        retention by however much of the window is younger than N days.
        """
        points: list[RetentionPoint] = []
        for day in days:
            cohort_cutoff = until - timedelta(days=day)
            cohort = select(User.id, User.created_at).where(
                User.created_at >= since, User.created_at < cohort_cutoff
            )
            cohort_subquery = cohort.subquery()
            cohort_users = await self._scalar_int(select(func.count()).select_from(cohort_subquery))
            returned = await self._scalar_int(
                select(func.count(func.distinct(AuthSession.user_id)))
                .select_from(cohort_subquery)
                .join(AuthSession, AuthSession.user_id == cohort_subquery.c.id)
                .where(
                    AuthSession.created_at >= cohort_subquery.c.created_at + timedelta(days=day),
                    AuthSession.created_at < cohort_subquery.c.created_at + timedelta(days=day + 1),
                )
            )
            points.append(
                RetentionPoint(day=day, cohort_users=cohort_users, returned_users=returned)
            )
        return points

    async def snapshot(
        self,
        *,
        days: int = 30,
        now: datetime | None = None,
        retention_days: tuple[int, ...] = (1, 7),
    ) -> AnalyticsSnapshot:
        until = now or datetime.now(UTC)
        since = until - timedelta(days=days)
        return AnalyticsSnapshot(
            since=since,
            until=until,
            usage=await self.usage(since=since, until=until),
            funnel=await self.funnel(since=since, until=until),
            revenue=await self.revenue(since=since, until=until),
            providers=await self.provider_economics(since=since, until=until),
            retention=await self.retention(since=since, until=until, days=retention_days),
        )
