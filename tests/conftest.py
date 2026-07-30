import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    NotificationOutbox,
    PaymentOrder,
    PaymentProduct,
    PaymentReceipt,
    PriceQuote,
    PromptAssistantRequest,
    ProviderUsage,
    User,
    Wallet,
    WebhookReceipt,
)


def _test_database_url() -> str:
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kelbet:kelbet@localhost:5433/kelbet_test",
    )


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_test_database_url(), pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session, db_session.begin():
        yield db_session
