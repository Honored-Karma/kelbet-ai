"""Operator-facing analytics: one request, one dashboard.

Everything is returned in a single payload on purpose. The numbers are only
meaningful next to each other — a conversion rate without the cohort size behind it,
or a revenue figure without the provider cost against it, is the kind of statistic
that gets quoted and then walked back.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session, get_operator
from kelbet.analytics import AnalyticsService
from kelbet.services.admin import OperatorContext

router = APIRouter(prefix="/admin/analytics", tags=["admin"])


class FunnelStepResponse(BaseModel):
    key: str
    users: int
    of_cohort: float
    of_previous: float


class FunnelResponse(BaseModel):
    cohort_users: int
    activation_rate: float
    paid_conversion_rate: float
    steps: list[FunnelStepResponse]


class UsageResponse(BaseModel):
    active_users: int
    new_users: int
    generations_started: int
    generations_succeeded: int
    generations_failed: int
    success_rate: float
    credits_spent: int


class RevenueResponse(BaseModel):
    orders_paid: int
    paying_users: int
    stars_collected: int
    credits_sold: int
    stars_refunded: int
    credits_refunded: int
    gross_usd: float
    refunded_usd: float
    net_usd: float
    credit_liability_usd: float
    pack_margin: float
    arpu_usd: float


class ProviderEconomicsResponse(BaseModel):
    provider: str
    provider_model_id: str
    modality: str
    generations: int
    provider_cost_usd: float
    credits_charged: int
    delivery_margin: float
    avg_latency_ms: int | None


class RetentionResponse(BaseModel):
    day: int
    cohort_users: int
    returned_users: int
    rate: float


class AnalyticsResponse(BaseModel):
    since: str
    until: str
    days: int
    usage: UsageResponse
    funnel: FunnelResponse
    revenue: RevenueResponse
    providers: list[ProviderEconomicsResponse]
    retention: list[RetentionResponse]
    total_provider_cost_usd: float
    contribution_usd: float


@router.get("", response_model=AnalyticsResponse)
async def read_analytics(
    days: int = Query(default=30, ge=1, le=365),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    del operator  # read access is the whole authorisation this endpoint needs
    snapshot = await AnalyticsService(session).snapshot(days=days)
    return AnalyticsResponse(
        since=snapshot.since.isoformat(),
        until=snapshot.until.isoformat(),
        days=days,
        usage=UsageResponse(
            active_users=snapshot.usage.active_users,
            new_users=snapshot.usage.new_users,
            generations_started=snapshot.usage.generations_started,
            generations_succeeded=snapshot.usage.generations_succeeded,
            generations_failed=snapshot.usage.generations_failed,
            success_rate=snapshot.usage.success_rate,
            credits_spent=snapshot.usage.credits_spent,
        ),
        funnel=FunnelResponse(
            cohort_users=snapshot.funnel.cohort_users,
            activation_rate=snapshot.funnel.activation_rate,
            paid_conversion_rate=snapshot.funnel.paid_conversion_rate,
            steps=[
                FunnelStepResponse(
                    key=step.key,
                    users=step.users,
                    of_cohort=step.of_cohort,
                    of_previous=step.of_previous,
                )
                for step in snapshot.funnel.steps
            ],
        ),
        revenue=RevenueResponse(
            orders_paid=snapshot.revenue.orders_paid,
            paying_users=snapshot.revenue.paying_users,
            stars_collected=snapshot.revenue.stars_collected,
            credits_sold=snapshot.revenue.credits_sold,
            stars_refunded=snapshot.revenue.stars_refunded,
            credits_refunded=snapshot.revenue.credits_refunded,
            gross_usd=snapshot.revenue.gross_usd,
            refunded_usd=snapshot.revenue.refunded_usd,
            net_usd=snapshot.revenue.net_usd,
            credit_liability_usd=snapshot.revenue.credit_liability_usd,
            pack_margin=snapshot.revenue.pack_margin,
            arpu_usd=snapshot.revenue.arpu_usd,
        ),
        providers=[
            ProviderEconomicsResponse(
                provider=row.provider,
                provider_model_id=row.provider_model_id,
                modality=row.modality,
                generations=row.generations,
                provider_cost_usd=row.provider_cost_usd,
                credits_charged=row.credits_charged,
                delivery_margin=row.delivery_margin,
                avg_latency_ms=row.avg_latency_ms,
            )
            for row in snapshot.providers
        ],
        retention=[
            RetentionResponse(
                day=point.day,
                cohort_users=point.cohort_users,
                returned_users=point.returned_users,
                rate=point.rate,
            )
            for point in snapshot.retention
        ],
        total_provider_cost_usd=snapshot.total_provider_cost_usd,
        contribution_usd=snapshot.contribution_usd,
    )
