import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
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


def _test_database_url() -> str:
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kelbet:kelbet@localhost:5433/kelbet_test",
    )


async def _reset_schema(conn: AsyncConnection) -> None:
    """Give the test a database holding exactly what the models declare.

    Dropping the schema rather than calling `Base.metadata.drop_all` is deliberate. CI
    runs `alembic upgrade head` before pytest, so the database arrives holding
    `alembic_version` plus whatever the migrations built. `drop_all` only knows the
    tables registered on the metadata and orders them by the relationships declared
    there, so one foreign key that lived in a migration but not in a model was enough to
    make it drop `generation_jobs` too early and take 130 tests down with it. `DROP
    SCHEMA ... CASCADE` cannot be defeated that way — it removes everything regardless
    of what the ORM believes. Drift between models and migrations is then caught
    deliberately and separately, by tests/test_schema_drift.py.
    """
    await conn.execute(text("DROP SCHEMA public CASCADE"))
    await conn.execute(text("CREATE SCHEMA public"))
    await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_test_database_url(), pool_pre_ping=True)
    async with engine.begin() as conn:
        await _reset_schema(conn)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        # Leave the database empty. CI runs `alembic upgrade head` before pytest, so a
        # suite that exits leaving model-built tables behind makes the *next* run's
        # migration step fail on "relation already exists" — a confusing failure in a
        # step that is not at fault.
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session, db_session.begin():
        yield db_session
