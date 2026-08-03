from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import SubscriptionPlan
from kelbet.subscriptions.seeds import subscription_plan_rows


async def seed_subscription_plans(session: AsyncSession) -> None:
    """Upsert the tiers by slug.

    Prices are updated in place, which is safe because a live subscription reads its own
    frozen `plan_snapshot` rather than the plan row. Repricing therefore affects new
    purchases only, and never what an existing subscriber already paid for.
    """
    statement = insert(SubscriptionPlan).values(subscription_plan_rows())
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[SubscriptionPlan.slug],
            set_={
                "plan": statement.excluded.plan,
                "monthly_credits": statement.excluded.monthly_credits,
                "stars": statement.excluded.stars,
                "kzt_price": statement.excluded.kzt_price,
                "enabled": statement.excluded.enabled,
                "display_order": statement.excluded.display_order,
                "localization": statement.excluded.localization,
            },
        )
    )
    await session.flush()
