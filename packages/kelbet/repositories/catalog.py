from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models.catalog import (
    CatalogModel,
    FeatureFlag,
    GenerationTemplate,
    PriceQuote,
)


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[CatalogModel]:
        result = await self._session.execute(
            select(CatalogModel).order_by(CatalogModel.display_order, CatalogModel.slug)
        )
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> CatalogModel | None:
        result = await self._session.execute(select(CatalogModel).where(CatalogModel.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_slug_for_update(self, slug: str) -> CatalogModel | None:
        result = await self._session.execute(
            select(CatalogModel).where(CatalogModel.slug == slug).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, model_id: UUID) -> CatalogModel | None:
        result = await self._session.execute(
            select(CatalogModel).where(CatalogModel.id == model_id)
        )
        return result.scalar_one_or_none()


class FeatureFlagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> FeatureFlag | None:
        result = await self._session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[FeatureFlag]:
        result = await self._session.execute(select(FeatureFlag))
        return list(result.scalars().all())

    async def get_for_update(self, key: str) -> FeatureFlag | None:
        result = await self._session.execute(
            select(FeatureFlag).where(FeatureFlag.key == key).with_for_update()
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        key: str,
        *,
        enabled: bool,
        payload: dict[str, Any] | None = None,
    ) -> FeatureFlag:
        existing = await self.get(key)
        if existing is None:
            row = FeatureFlag(key=key, enabled=enabled, payload=payload)
            self._session.add(row)
            await self._session.flush()
            return row
        existing.enabled = enabled
        existing.payload = payload
        await self._session.flush()
        return existing


class GenerationTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[GenerationTemplate]:
        result = await self._session.execute(
            select(GenerationTemplate).order_by(
                GenerationTemplate.display_order, GenerationTemplate.slug
            )
        )
        return list(result.scalars().all())

    async def list_active(self, *, kind: str | None = None) -> list[GenerationTemplate]:
        statement = select(GenerationTemplate).where(GenerationTemplate.enabled.is_(True))
        if kind is not None:
            statement = statement.where(GenerationTemplate.kind == kind)
        result = await self._session.execute(
            statement.order_by(GenerationTemplate.display_order, GenerationTemplate.slug)
        )
        return list(result.scalars().all())

    async def get_by_id(self, template_id: UUID) -> GenerationTemplate | None:
        result = await self._session.execute(
            select(GenerationTemplate).where(GenerationTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> GenerationTemplate | None:
        result = await self._session.execute(
            select(GenerationTemplate).where(GenerationTemplate.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_slug_for_update(self, slug: str) -> GenerationTemplate | None:
        result = await self._session.execute(
            select(GenerationTemplate).where(GenerationTemplate.slug == slug).with_for_update()
        )
        return result.scalar_one_or_none()


class PriceQuoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        model_id: UUID,
        model_slug: str,
        user_credit_price: int,
        params: dict[str, Any],
        snapshot: dict[str, Any],
        template_id: UUID | None,
        template_slug: str | None,
        template_version: int | None,
        template_inputs: dict[str, Any],
        template_snapshot: dict[str, Any],
        expires_at: datetime,
    ) -> PriceQuote:
        row = PriceQuote(
            user_id=user_id,
            model_id=model_id,
            model_slug=model_slug,
            user_credit_price=user_credit_price,
            params=params,
            snapshot=snapshot,
            template_id=template_id,
            template_slug=template_slug,
            template_version=template_version,
            template_inputs=template_inputs,
            template_snapshot=template_snapshot,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, quote_id: UUID) -> PriceQuote | None:
        result = await self._session.execute(select(PriceQuote).where(PriceQuote.id == quote_id))
        return result.scalar_one_or_none()
