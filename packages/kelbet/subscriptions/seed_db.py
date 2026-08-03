from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import SubscriptionPlan
from kelbet.subscriptions.seeds import subscription_plan_rows


async def seed_subscription_plans(session: AsyncSession) -> None:
    """Upsert the tiers by slug, mirroring `kelbet.payments.seed_db`.

    Migration 0023 seeds these rows too, so a deployment gets them without a separate
    step. This exists for the paths that build the schema from the models rather than from
    the migrations — the test fixtures — and for re-seeding after a price edit.

    Updating prices in place is safe for live subscribers: a charge is validated against
    the plan row, and both sides of that comparison move together. What a repricing does
    change is the amount Telegram bills next period, which is why an invoice link is
    created per checkout rather than cached.
    """
    statement = insert(SubscriptionPlan).values(subscription_plan_rows())
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[SubscriptionPlan.slug],
            set_={
                "plan_key": statement.excluded.plan_key,
                "stars": statement.excluded.stars,
                "price_kzt": statement.excluded.price_kzt,
                "credits_per_period": statement.excluded.credits_per_period,
                "period_days": statement.excluded.period_days,
                "referral_percent": statement.excluded.referral_percent,
                "enabled": statement.excluded.enabled,
                "display_order": statement.excluded.display_order,
                "localization": statement.excluded.localization,
            },
        )
    )
    await session.flush()
