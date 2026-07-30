from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import PaymentProduct
from kelbet.payments.seeds import payment_product_rows


async def seed_payment_products(session: AsyncSession) -> None:
    statement = insert(PaymentProduct).values(payment_product_rows())
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PaymentProduct.slug],
            set_={
                "credits": statement.excluded.credits,
                "stars": statement.excluded.stars,
                "enabled": statement.excluded.enabled,
                "display_order": statement.excluded.display_order,
                "localization": statement.excluded.localization,
            },
        )
    )
    await session.flush()
