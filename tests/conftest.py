import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kelbet.db.base import Base
from kelbet.db.models import (  # noqa: F401
    AuthSession,
    CatalogModel,
    CreditReservation,
    CreditTransaction,
    FeatureFlag,
    GenerationAsset,
    GenerationAttempt,
    GenerationJob,
    GenerationTemplate,
    ModerationDecision,
    NotificationOutbox,
    PaymentOrder,
    PaymentProduct,
    PaymentReceipt,
    PaymentReconciliationIssue,
    PaymentReconciliationRun,
    PaymentRefund,
    PriceQuote,
    PromptAssistantRequest,
    ProviderUsage,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
    StarTransactionObservation,
    User,
    UserConsent,
    Wallet,
    WebhookReceipt,
)


async def _reset_schema(conn: AsyncConnection) -> None:
    """Drop everything in the test database, however it was created.

    `Base.metadata.drop_all` sorts tables by the foreign keys declared on the models,
    so it only works on a schema that `create_all` built. CI runs `alembic upgrade head`
    before pytest, and the migrated schema carries constraints the models do not
    declare — generation_assets.generation_id references generation_jobs in migration
    0006, but the model leaves the column FK-less. drop_all then tries to drop
    generation_jobs first and Postgres refuses with DependentObjectsStillExistError,
    which failed every database test in the suite.

    Dropping the schema sidesteps the ordering question entirely and is safe here
    because this only ever runs against the test database.
    """
    await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
    await conn.exec_driver_sql("CREATE SCHEMA public")


def _test_database_url() -> str:
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kelbet:kelbet@localhost:5433/kelbet_test",
    )


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_test_database_url(), pool_pre_ping=True)
    async with engine.begin() as conn:
        await _reset_schema(conn)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await _reset_schema(conn)
        await engine.dispose()


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session, db_session.begin():
        yield db_session
