"""Analytics over the operational tables.

These numbers are the ones that get quoted to an outsider, so the tests are written
against the two ways a metric lies rather than against the happy path alone:

* a denominator that quietly includes the wrong people — a period funnel counting a
  user who registered months ago as today's conversion, or a retention cohort counting
  users who are not yet old enough to have returned;
* a margin that reads healthy because the loss is in the half of the business the
  number does not cover.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apps.api.main import create_app
from apps.api.routes.v1.analytics import read_analytics
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.analytics import AnalyticsService
from kelbet.catalog.seed_db import seed_catalog
from kelbet.catalog.seeds import CREDIT_COST_UNITS
from kelbet.db.models import (
    AuthSession,
    CatalogModel,
    GenerationJob,
    PaymentOrder,
    PaymentProduct,
    ProviderUsage,
    User,
)
from kelbet.domain.enums import GenerationStatus, Language, Plan
from kelbet.payments.seed_db import seed_payment_products
from kelbet.payments.seeds import CREDIT_COST_USD, STAR_PAYOUT_USD

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


async def _user(session: AsyncSession, *, telegram_id: int, created_at: datetime) -> User:
    user = User(
        telegram_id=telegram_id,
        username=f"user{telegram_id}",
        language=Language.RU.value,
        plan=Plan.FREE.value,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(user)
    await session.flush()
    return user


async def _session_row(session: AsyncSession, *, user: User, created_at: datetime) -> None:
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=uuid4().hex,
            telegram_auth_date=created_at,
            init_data_hash=uuid4().hex,
            expires_at=created_at + timedelta(days=1),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    await session.flush()


async def _generation(
    session: AsyncSession,
    *,
    user: User,
    model_id: UUID,
    created_at: datetime,
    status: GenerationStatus,
    credits: int = 100,
) -> GenerationJob:
    job = GenerationJob(
        user_id=user.id,
        model_id=model_id,
        modality="video",
        status=status.value,
        idempotency_key=uuid4().hex,
        request_hash=uuid4().hex[:32],
        prompt_redacted=False,
        params={},
        user_credit_price=credits,
        provider="fal",
        provider_model_id="fal-ai/kling-video/v3/pro/text-to-video",
        progress_pct=100 if status is GenerationStatus.SUCCEEDED else 0,
        attempt_count=1,
        max_attempts=1,
        correlation_id=uuid4(),
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(job)
    await session.flush()
    return job


async def _usage(
    session: AsyncSession,
    *,
    job: GenerationJob,
    created_at: datetime,
    provider_cost_units: int,
    credits: int,
    provider: str = "fal",
    latency_ms: int = 1000,
) -> None:
    session.add(
        ProviderUsage(
            generation_id=job.id,
            provider=provider,
            provider_model_id="fal-ai/kling-video/v3/pro/text-to-video",
            modality="video",
            provider_cost_units=provider_cost_units,
            user_credit_price=credits,
            latency_ms=latency_ms,
            created_at=created_at,
        )
    )
    await session.flush()


async def _paid_order(
    session: AsyncSession,
    *,
    user: User,
    product: PaymentProduct,
    paid_at: datetime | None,
    stars: int,
    credits: int,
) -> None:
    session.add(
        PaymentOrder(
            user_id=user.id,
            product_id=product.id,
            status="paid" if paid_at else "pending",
            idempotency_key=uuid4().hex,
            invoice_payload=uuid4().hex,
            currency="XTR",
            total_amount=stars,
            credits=credits,
            product_snapshot={"slug": product.slug},
            terms_version="2026-08-12",
            terms_accepted_at=paid_at or NOW,
            expires_at=NOW + timedelta(hours=1),
            paid_at=paid_at,
            created_at=paid_at or NOW,
            updated_at=paid_at or NOW,
        )
    )
    await session.flush()


async def _video_model_id(session: AsyncSession) -> UUID:
    await seed_catalog(session)
    model = (
        await session.execute(select(CatalogModel).where(CatalogModel.modality == "video").limit(1))
    ).scalar_one()
    return model.id


async def _starter_product(session: AsyncSession) -> PaymentProduct:
    await seed_payment_products(session)
    return (
        await session.execute(select(PaymentProduct).order_by(PaymentProduct.credits).limit(1))
    ).scalar_one()


@pytest.mark.asyncio
async def test_an_empty_product_reports_zeros_rather_than_dividing_by_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The dashboard is opened before the first user exists, and a crash there reads
    as a broken product to whoever is watching."""
    async with session_factory() as session, session.begin():
        snapshot = await AnalyticsService(session).snapshot(days=30, now=NOW)

        assert snapshot.usage.active_users == 0
        assert snapshot.usage.success_rate == 0.0
        assert snapshot.funnel.cohort_users == 0
        assert snapshot.funnel.paid_conversion_rate == 0.0
        assert snapshot.revenue.net_usd == 0.0
        assert snapshot.revenue.pack_margin == 0.0
        assert snapshot.revenue.arpu_usd == 0.0
        assert snapshot.providers == []
        assert snapshot.contribution_usd == 0.0


@pytest.mark.asyncio
async def test_usage_counts_only_the_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        inside = await _user(session, telegram_id=9001, created_at=NOW - timedelta(days=2))
        outside = await _user(session, telegram_id=9002, created_at=NOW - timedelta(days=90))

        await _session_row(session, user=inside, created_at=NOW - timedelta(days=1))
        await _session_row(session, user=outside, created_at=NOW - timedelta(days=80))

        await _generation(
            session,
            user=inside,
            model_id=model_id,
            created_at=NOW - timedelta(days=1),
            status=GenerationStatus.SUCCEEDED,
        )
        await _generation(
            session,
            user=inside,
            model_id=model_id,
            created_at=NOW - timedelta(days=1),
            status=GenerationStatus.FAILED,
        )
        await _generation(
            session,
            user=outside,
            model_id=model_id,
            created_at=NOW - timedelta(days=80),
            status=GenerationStatus.SUCCEEDED,
        )

        usage = await AnalyticsService(session).usage(since=NOW - timedelta(days=30), until=NOW)

        assert usage.new_users == 1
        assert usage.active_users == 1
        assert usage.generations_started == 2
        assert usage.generations_succeeded == 1
        assert usage.generations_failed == 1
        assert usage.success_rate == 0.5


@pytest.mark.asyncio
async def test_the_funnel_is_cohort_based_and_refuses_borrowed_conversions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A user who registered before the window and pays inside it is not a conversion
    of this window's traffic. Counting them would make the headline rate a function of
    how long the product has existed."""
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        product = await _starter_product(session)

        newcomer = await _user(session, telegram_id=9101, created_at=NOW - timedelta(days=3))
        veteran = await _user(session, telegram_id=9102, created_at=NOW - timedelta(days=120))

        for user in (newcomer, veteran):
            await _session_row(session, user=user, created_at=NOW - timedelta(days=1))
            await _generation(
                session,
                user=user,
                model_id=model_id,
                created_at=NOW - timedelta(days=1),
                status=GenerationStatus.SUCCEEDED,
            )
        # Only the veteran pays, and they pay inside the window.
        await _paid_order(
            session,
            user=veteran,
            product=product,
            paid_at=NOW - timedelta(days=1),
            stars=99,
            credits=100,
        )

        funnel = await AnalyticsService(session).funnel(since=NOW - timedelta(days=30), until=NOW)

        assert funnel.cohort_users == 1
        assert funnel.activation_rate == 1.0
        # The payment belongs to a user outside the cohort, so conversion stays zero.
        assert funnel.paid_conversion_rate == 0.0


@pytest.mark.asyncio
async def test_the_funnel_reports_where_the_step_to_step_loss_happens(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        users = [
            await _user(session, telegram_id=9200 + index, created_at=NOW - timedelta(days=5))
            for index in range(4)
        ]
        # All four open the app, two ask for a generation, one gets a result.
        for user in users:
            await _session_row(session, user=user, created_at=NOW - timedelta(days=4))
        await _generation(
            session,
            user=users[0],
            model_id=model_id,
            created_at=NOW - timedelta(days=4),
            status=GenerationStatus.SUCCEEDED,
        )
        await _generation(
            session,
            user=users[1],
            model_id=model_id,
            created_at=NOW - timedelta(days=4),
            status=GenerationStatus.FAILED,
        )

        funnel = await AnalyticsService(session).funnel(since=NOW - timedelta(days=30), until=NOW)
        steps = {step.key: step for step in funnel.steps}

        assert steps["registered"].users == 4
        assert steps["app_opened"].users == 4
        assert steps["generation_requested"].users == 2
        assert steps["generation_succeeded"].users == 1
        # Half the people who opened the app never asked for anything: that is the leak.
        assert steps["generation_requested"].of_previous == 0.5
        assert steps["generation_succeeded"].of_previous == 0.5
        assert steps["generation_succeeded"].of_cohort == 0.25


@pytest.mark.asyncio
async def test_revenue_is_net_of_refunds_and_names_the_credit_liability(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        product = await _starter_product(session)
        buyer = await _user(session, telegram_id=9301, created_at=NOW - timedelta(days=10))
        # Two paid orders and one still pending; the pending one is not revenue.
        await _paid_order(
            session,
            user=buyer,
            product=product,
            paid_at=NOW - timedelta(days=2),
            stars=99,
            credits=100,
        )
        await _paid_order(
            session,
            user=buyer,
            product=product,
            paid_at=NOW - timedelta(days=1),
            stars=99,
            credits=100,
        )
        await _paid_order(session, user=buyer, product=product, paid_at=None, stars=99, credits=100)

        revenue = await AnalyticsService(session).revenue(since=NOW - timedelta(days=30), until=NOW)

        assert revenue.orders_paid == 2
        assert revenue.paying_users == 1
        assert revenue.stars_collected == 198
        assert revenue.credits_sold == 200
        assert revenue.gross_usd == round(198 * STAR_PAYOUT_USD, 4)
        assert revenue.credit_liability_usd == round(200 * CREDIT_COST_USD, 4)
        # The catalog is priced for a 60% target margin; this is that number measured
        # rather than asserted in a seed file.
        assert revenue.pack_margin >= 0.60
        assert revenue.arpu_usd == revenue.net_usd


@pytest.mark.asyncio
async def test_delivery_margin_turns_negative_when_a_route_is_sold_below_cost(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """This is the failure that grows with every user, and the only place it shows up.

    Pack margin stays healthy while it happens: the credits were sold profitably, and
    the loss appears later, when they are spent on a route that costs more to serve
    than the credits it charges.
    """
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        user = await _user(session, telegram_id=9401, created_at=NOW - timedelta(days=5))

        profitable = await _generation(
            session,
            user=user,
            model_id=model_id,
            created_at=NOW - timedelta(days=3),
            status=GenerationStatus.SUCCEEDED,
            credits=100,
        )
        # 100 credits allow 4000 units of provider spend; this one used 3000.
        await _usage(
            session,
            job=profitable,
            created_at=NOW - timedelta(days=3),
            provider_cost_units=3000,
            credits=100,
        )

        underwater = await _generation(
            session,
            user=user,
            model_id=model_id,
            created_at=NOW - timedelta(days=2),
            status=GenerationStatus.SUCCEEDED,
            credits=50,
        )
        # 50 credits allow 2000 units; this one burned 5000.
        await _usage(
            session,
            job=underwater,
            created_at=NOW - timedelta(days=2),
            provider_cost_units=5000,
            credits=50,
            provider="runway",
        )

        rows = await AnalyticsService(session).provider_economics(
            since=NOW - timedelta(days=30), until=NOW
        )
        by_provider = {row.provider: row for row in rows}

        assert by_provider["fal"].delivery_margin == 0.25
        assert by_provider["fal"].charged_budget_units == 100 * CREDIT_COST_UNITS
        assert by_provider["runway"].delivery_margin < 0
        assert by_provider["runway"].provider_cost_usd == 0.5
        # Ordered by spend so the most expensive route is the first thing read.
        assert rows[0].provider == "runway"


@pytest.mark.asyncio
async def test_contribution_puts_cash_collected_against_cash_paid_out(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        product = await _starter_product(session)
        user = await _user(session, telegram_id=9501, created_at=NOW - timedelta(days=6))
        await _paid_order(
            session,
            user=user,
            product=product,
            paid_at=NOW - timedelta(days=5),
            stars=285,
            credits=300,
        )
        job = await _generation(
            session,
            user=user,
            model_id=model_id,
            created_at=NOW - timedelta(days=4),
            status=GenerationStatus.SUCCEEDED,
            credits=140,
        )
        await _usage(
            session,
            job=job,
            created_at=NOW - timedelta(days=4),
            provider_cost_units=5600,
            credits=140,
        )

        snapshot = await AnalyticsService(session).snapshot(days=30, now=NOW)

        assert snapshot.total_provider_cost_usd == 0.56
        assert snapshot.contribution_usd == round(snapshot.revenue.net_usd - 0.56, 4)
        assert snapshot.contribution_usd > 0


@pytest.mark.asyncio
async def test_retention_closes_the_cohort_before_measuring_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A user who registered an hour ago cannot have a day-7 outcome yet. Counting
    them as a miss would make retention fall simply because the window is recent."""
    async with session_factory() as session, session.begin():
        returning = await _user(session, telegram_id=9601, created_at=NOW - timedelta(days=10))
        # Registered and came back the next day.
        await _session_row(session, user=returning, created_at=NOW - timedelta(days=10))
        await _session_row(
            session,
            user=returning,
            created_at=NOW - timedelta(days=10) + timedelta(days=1, hours=2),
        )
        # Too young to be judged on day 1 at all.
        too_young = await _user(session, telegram_id=9602, created_at=NOW - timedelta(hours=3))
        await _session_row(session, user=too_young, created_at=NOW - timedelta(hours=3))

        points = await AnalyticsService(session).retention(
            since=NOW - timedelta(days=30), until=NOW, days=(1,)
        )

        day1 = points[0]
        assert day1.cohort_users == 1, "the user registered 3 hours ago must not be judged"
        assert day1.returned_users == 1
        assert day1.rate == 1.0


@pytest.mark.asyncio
async def test_credits_spent_reads_delivered_work_not_the_whole_ledger(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The ledger also carries welcome bonuses, purchases and refunds. Summing it
    would report credits "spent" that were never spent on anything."""
    async with session_factory() as session, session.begin():
        model_id = await _video_model_id(session)
        user = await _user(session, telegram_id=9701, created_at=NOW - timedelta(days=4))
        job = await _generation(
            session,
            user=user,
            model_id=model_id,
            created_at=NOW - timedelta(days=3),
            status=GenerationStatus.SUCCEEDED,
            credits=88,
        )
        await _usage(
            session,
            job=job,
            created_at=NOW - timedelta(days=3),
            provider_cost_units=3500,
            credits=88,
        )

        usage = await AnalyticsService(session).usage(since=NOW - timedelta(days=30), until=NOW)

        assert usage.credits_spent == 88


def test_the_analytics_endpoint_is_not_readable_without_an_operator() -> None:
    """Revenue and margin are the last thing that should be world-readable, and the
    route sits under /admin only by convention — the dependency is what enforces it."""
    app = create_app(testing=True)
    routes = [
        route for route in app.routes if getattr(route, "path", "") == "/api/v1/admin/analytics"
    ]

    assert routes, "the analytics route is not mounted"
    dependencies = getattr(routes[0], "dependant", None)
    assert dependencies is not None
    calls = {dep.call for dep in dependencies.dependencies}
    from apps.api.deps import get_operator

    assert get_operator in calls, "analytics is reachable without operator authorisation"
    assert read_analytics.__name__ == "read_analytics"
