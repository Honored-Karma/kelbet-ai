from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_settings_dep
from kelbet.config import Settings
from kelbet.domain.enums import Language, Modality, TemplateKind
from kelbet.services.auth import SessionUser
from kelbet.services.catalog import CatalogService
from kelbet.services.templates import GenerationTemplateService

router = APIRouter(prefix="/catalog", tags=["catalog"])


class LocalizedTextResponse(BaseModel):
    name: str
    description: str


class CatalogModelResponse(BaseModel):
    id: str
    slug: str
    modality: Modality
    provider: str
    provider_model_id: str
    display_order: int
    enabled: bool
    deprecated: bool
    replacement_slug: str | None
    user_credit_price: int
    capabilities: dict[str, Any]
    input_requirements: dict[str, Any]
    localization: LocalizedTextResponse
    pricing_rules: dict[str, Any] | None


class CatalogListResponse(BaseModel):
    items: list[CatalogModelResponse]


class GenerationTemplateResponse(BaseModel):
    id: str
    slug: str
    version: int
    kind: TemplateKind
    display_order: int
    localization: dict[str, str]
    prompt_preset: str
    aspect_ratio: str
    duration_sec: int | None
    compatible_modalities: list[str]
    required_inputs: dict[str, Any]
    preview_metadata: dict[str, Any]
    compositor: str | None


class GenerationTemplateListResponse(BaseModel):
    items: list[GenerationTemplateResponse]


def _to_response(dto: object) -> CatalogModelResponse:
    from kelbet.services.catalog import CatalogModelDTO

    assert isinstance(dto, CatalogModelDTO)
    return CatalogModelResponse(
        id=str(dto.id),
        slug=dto.slug,
        modality=dto.modality,
        provider=dto.provider,
        provider_model_id=dto.provider_model_id,
        display_order=dto.display_order,
        enabled=dto.enabled,
        deprecated=dto.deprecated,
        replacement_slug=dto.replacement_slug,
        user_credit_price=dto.user_credit_price,
        capabilities=dto.capabilities,
        input_requirements=dto.input_requirements,
        localization=LocalizedTextResponse(
            name=dto.localization.name,
            description=dto.localization.description,
        ),
        pricing_rules=dto.pricing_rules,
    )


@router.get("/models", response_model=CatalogListResponse)
async def list_models(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    lang: Language | None = Query(default=None),
) -> CatalogListResponse:
    language = lang or current.language
    items = await CatalogService(session).list_models_for_user(
        language=language,
        telegram_id=current.telegram_id,
    )
    return CatalogListResponse(items=[_to_response(item) for item in items])


@router.get("/templates", response_model=GenerationTemplateListResponse)
async def list_generation_templates(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    lang: Language | None = Query(default=None),
    kind: TemplateKind | None = Query(default=None),
) -> GenerationTemplateListResponse:
    items = await GenerationTemplateService(session, settings).list_active(
        language=lang or current.language,
        kind=kind,
    )
    return GenerationTemplateListResponse(
        items=[
            GenerationTemplateResponse(
                id=str(item.id),
                slug=item.slug,
                version=item.version,
                kind=item.kind,
                display_order=item.display_order,
                localization=item.localization,
                prompt_preset=item.prompt_preset,
                aspect_ratio=item.aspect_ratio,
                duration_sec=item.duration_sec,
                compatible_modalities=item.compatible_modalities,
                required_inputs=item.required_inputs,
                preview_metadata=item.preview_metadata,
                compositor=item.compositor,
            )
            for item in items
        ]
    )


@router.get("/models/{slug}", response_model=CatalogModelResponse)
async def get_model(
    slug: str,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    lang: Language | None = Query(default=None),
) -> CatalogModelResponse:
    language = lang or current.language
    item = await CatalogService(session).get_model_for_user(
        slug,
        language=language,
        telegram_id=current.telegram_id,
    )
    return _to_response(item)
