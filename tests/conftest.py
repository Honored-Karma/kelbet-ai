import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import make_url
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


def _assert_disposable(url: str) -> None:
    """Refuse to wipe a database that does not look disposable.

    `_reset_schema` issues `DROP SCHEMA public CASCADE`, which destroys everything in the
    schema rather than only the tables the ORM knows about. That is the right tool for a
    test database and a catastrophe against any other one, and the only thing standing
    between the two is the value of `TEST_DATABASE_URL`. A typo, an inherited shell
    export, or a copy-pasted staging URL would otherwise be silently obeyed.

    Requiring the database name to say it is for testing keeps the guard trivial to
    satisfy on purpose and hard to satisfy by accident.
    """
    database = (make_url(url).database or "").lower()
    if not database:
        msg = f"TEST_DATABASE_URL names no database: {url!r}"
        raise RuntimeError(msg)
    if "test" not in database:
        msg = (
            f"refusing to run tests against database {database!r}: the suite drops and "
            "recreates the public schema, so its name must contain 'test'. Set "
            "TEST_DATABASE_URL to a disposable database."
        )
        raise RuntimeError(msg)


async def _reset_schema(conn: AsyncConnection) -> None:
    """Drop everything in the test database, however it was created.

    `Base.metadata.drop_all` orders tables by the foreign keys declared on the models, so
    it only works on a schema that `create_all` built. CI runs `alembic upgrade head`
    before pytest, and any constraint present in a migration but missing from a model
    makes that ordering wrong — which is how a single absent foreign key on
    `generation_assets.generation_id` once failed every database test in the suite with
    `DependentObjectsStillExistError`.

    Dropping the schema sidesteps the ordering question entirely, and keeps doing so even
    if the models and migrations disagree again in future. That they currently agree is
    asserted separately and deliberately, by tests/test_schema_drift.py.
    """
    await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
    await conn.exec_driver_sql("CREATE SCHEMA public")


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = _test_database_url()
    _assert_disposable(url)
    engine = create_async_engine(url, pool_pre_ping=True)
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
