"""Apply canonical catalog seeds into an open session (tests / ops)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.seeds import catalog_model_rows, feature_flag_rows
from kelbet.catalog.template_seeds import template_rows
from kelbet.db.models.catalog import (
    CatalogModel,
    FeatureFlag,
    GenerationTemplate,
)


async def seed_catalog(session: AsyncSession) -> None:
    existing_flags = {row.key for row in (await session.execute(select(FeatureFlag))).scalars()}
    for row in feature_flag_rows():
        if row["key"] in existing_flags:
            continue
        session.add(FeatureFlag(key=row["key"], enabled=row["enabled"], payload=row["payload"]))

    existing_slugs = {row.slug for row in (await session.execute(select(CatalogModel))).scalars()}
    for row in catalog_model_rows():
        if row["slug"] in existing_slugs:
            continue
        session.add(CatalogModel(**row))

    existing_templates = {
        row.slug for row in (await session.execute(select(GenerationTemplate))).scalars()
    }
    for row in template_rows():
        if row["slug"] in existing_templates:
            continue
        session.add(GenerationTemplate(**row))
    await session.flush()
