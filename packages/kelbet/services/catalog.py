from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.catalog.pricing import (
    compute_user_credit_price,
    validate_params_against_capabilities,
)
from kelbet.config import Settings, get_settings
from kelbet.db.models.catalog import CatalogModel
from kelbet.domain.enums import Language, Modality
from kelbet.domain.exceptions import (
    CatalogModelNotFoundError,
    GenerationTemplateValidationError,
    ModelUnavailableError,
    QuoteNotFoundError,
    WalletNotFoundError,
)
from kelbet.observability import get_metrics
from kelbet.repositories.catalog import (
    CatalogRepository,
    FeatureFlagRepository,
    PriceQuoteRepository,
)
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.templates import GenerationTemplateService

DEFAULT_QUOTE_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class LocalizedText:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class CatalogModelDTO:
    id: UUID
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
    localization: LocalizedText
    pricing_rules: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class QuoteDTO:
    quote_id: UUID
    model_slug: str
    user_credit_price: int
    currency: str
    params: dict[str, Any]
    expires_at: datetime
    available: int
    template_id: UUID | None
    template_slug: str | None
    template_version: int | None
    template_inputs: dict[str, Any]
    template_snapshot: dict[str, Any]
    routing_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WalletBalanceDTO:
    balance: int
    reserved: int
    available: int


def _routing_snapshot(model: CatalogModel, *, params: dict[str, Any]) -> dict[str, Any]:
    capabilities = dict(model.capabilities or {})
    fallback_raw = capabilities.get("fallback")
    fallback = dict(fallback_raw) if isinstance(fallback_raw, dict) else None
    ui = capabilities.get("ui")
    ui = ui if isinstance(ui, dict) else {}
    if fallback is not None:
        for key in (
            "provider_cost_ceiling_units",
            "provider_cost_ceiling_units_per_second",
        ):
            value = ui.get(key)
            if isinstance(value, int) and value > 0:
                fallback[key] = value
    primary_cost = 0
    if model.provider_cost_units > 0:
        primary_cost = compute_user_credit_price(
            model.provider_cost_units,
            params=params,
            pricing_rules=model.pricing_rules,
        )
    return {
        "version": 1,
        "primary": {
            "provider": model.provider,
            "provider_model_id": model.provider_model_id,
            "provider_cost_units": primary_cost,
        },
        "fallback": fallback,
    }


class FeatureFlagService:
    def __init__(self, session: AsyncSession) -> None:
        self._flags = FeatureFlagRepository(session)

    async def is_enabled(self, key: str, *, telegram_id: int | None = None) -> bool:
        flag = await self._flags.get(key)
        if flag is None:
            return False
        if not flag.enabled:
            return False
        payload = flag.payload or {}
        allowlist = payload.get("telegram_ids")
        if allowlist is None:
            return True
        if telegram_id is None:
            return False
        return telegram_id in allowlist


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._catalog = CatalogRepository(session)
        self._flags = FeatureFlagService(session)

    async def list_models_for_user(
        self,
        *,
        language: Language,
        telegram_id: int,
        include_disabled: bool = False,
    ) -> list[CatalogModelDTO]:
        models = await self._catalog.list_all()
        result: list[CatalogModelDTO] = []
        for model in models:
            if not include_disabled and not model.enabled:
                continue
            if model.deprecated_at is not None and not include_disabled:
                continue
            if model.feature_flag and not await self._flags.is_enabled(
                model.feature_flag, telegram_id=telegram_id
            ):
                continue
            result.append(self._to_dto(model, language))
        return result

    async def get_model_for_user(
        self,
        slug: str,
        *,
        language: Language,
        telegram_id: int,
        for_quote: bool = False,
    ) -> CatalogModelDTO:
        model = await self._require_visible(slug, telegram_id=telegram_id, for_quote=for_quote)
        return self._to_dto(model, language)

    async def get_model_entity_for_quote(self, slug: str, *, telegram_id: int) -> CatalogModel:
        return await self._require_visible(slug, telegram_id=telegram_id, for_quote=True)

    async def _require_visible(
        self,
        slug: str,
        *,
        telegram_id: int,
        for_quote: bool,
    ) -> CatalogModel:
        model = await self._catalog.get_by_slug(slug)
        if model is None:
            raise CatalogModelNotFoundError(f"Unknown model slug={slug}")
        if not model.enabled:
            raise ModelUnavailableError(f"Model {slug} is disabled")
        if model.deprecated_at is not None and for_quote:
            raise ModelUnavailableError(f"Model {slug} is deprecated")
        if model.feature_flag and not await self._flags.is_enabled(
            model.feature_flag, telegram_id=telegram_id
        ):
            raise ModelUnavailableError(f"Model {slug} is not available")
        return model

    def _to_dto(self, model: CatalogModel, language: Language) -> CatalogModelDTO:
        loc = model.localization or {}
        entry = (
            loc.get(language.value)
            or loc.get(Language.KK.value)
            or loc.get(Language.RU.value)
            or {}
        )
        return CatalogModelDTO(
            id=model.id,
            slug=model.slug,
            modality=Modality(model.modality),
            provider=model.provider,
            provider_model_id=model.provider_model_id,
            display_order=model.display_order,
            enabled=model.enabled,
            deprecated=model.deprecated_at is not None,
            replacement_slug=model.replacement_slug,
            user_credit_price=model.user_credit_price,
            capabilities=dict(model.capabilities or {}),
            input_requirements=dict(model.input_requirements or {}),
            localization=LocalizedText(
                name=str(entry.get("name") or model.slug),
                description=str(entry.get("description") or ""),
            ),
            pricing_rules=dict(model.pricing_rules) if model.pricing_rules else None,
        )


class QuoteService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._catalog = CatalogService(session)
        self._quotes = PriceQuoteRepository(session)
        self._wallets = WalletRepository(session)
        self._templates = GenerationTemplateService(session, self._settings)

    async def create_quote(
        self,
        *,
        user_id: UUID,
        telegram_id: int,
        model_slug: str,
        params: dict[str, Any] | None = None,
        template_id: UUID | None = None,
        template_inputs: dict[str, object] | None = None,
        now: datetime | None = None,
        ttl: timedelta = DEFAULT_QUOTE_TTL,
    ) -> QuoteDTO:
        current = now or datetime.now(UTC)
        model = await self._catalog.get_model_entity_for_quote(model_slug, telegram_id=telegram_id)
        cleaned = validate_params_against_capabilities(params or {}, model.capabilities or {})
        selection = None
        if template_id is not None:
            selection = await self._templates.select_for_quote(
                template_id=template_id,
                template_inputs=template_inputs,
                model_modality=model.modality,
            )
            template = selection.entity
            if cleaned.get("aspect_ratio") != template.aspect_ratio:
                raise GenerationTemplateValidationError(
                    "Quote aspect ratio does not match the generation template"
                )
            if template.duration_sec is not None and (
                cleaned.get("duration_sec") != template.duration_sec
            ):
                raise GenerationTemplateValidationError(
                    "Quote duration does not match the generation template"
                )
        elif template_inputs:
            raise GenerationTemplateValidationError("Template inputs require a generation template")
        price = compute_user_credit_price(
            model.user_credit_price,
            params=cleaned,
            pricing_rules=model.pricing_rules,
        )
        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {user_id} not found")

        expires_at = current + ttl
        routing_snapshot = _routing_snapshot(model, params=cleaned)
        snapshot = {
            "model_id": str(model.id),
            "model_slug": model.slug,
            "base_price": model.user_credit_price,
            "provider_cost_units": model.provider_cost_units,
            "provider": model.provider,
            "provider_model_id": model.provider_model_id,
            "modality": model.modality,
            "pricing_rules": model.pricing_rules,
            "params": cleaned,
            "user_credit_price": price,
            "template": selection.snapshot if selection else None,
            "template_inputs": selection.inputs if selection else {},
            "routing": routing_snapshot,
        }
        row = await self._quotes.create(
            user_id=user_id,
            model_id=model.id,
            model_slug=model.slug,
            user_credit_price=price,
            params=cleaned,
            snapshot=snapshot,
            template_id=selection.entity.id if selection else None,
            template_slug=selection.entity.slug if selection else None,
            template_version=selection.entity.version if selection else None,
            template_inputs=selection.inputs if selection else {},
            template_snapshot=selection.snapshot if selection else {},
            expires_at=expires_at,
        )
        if selection is not None:
            get_metrics().incr(
                "template.selected",
                tags={"template": selection.entity.slug, "kind": selection.entity.kind},
            )
        return QuoteDTO(
            quote_id=row.id,
            model_slug=model.slug,
            user_credit_price=price,
            currency="credits",
            params=cleaned,
            expires_at=expires_at,
            available=wallet.balance - wallet.reserved,
            template_id=row.template_id,
            template_slug=row.template_slug,
            template_version=row.template_version,
            template_inputs=dict(row.template_inputs),
            template_snapshot=dict(row.template_snapshot),
            routing_snapshot=dict(routing_snapshot),
        )

    async def get_valid_quote(
        self,
        quote_id: UUID,
        *,
        user_id: UUID,
        now: datetime | None = None,
    ) -> QuoteDTO:
        current = now or datetime.now(UTC)
        row = await self._quotes.get_by_id(quote_id)
        if row is None or row.user_id != user_id:
            raise QuoteNotFoundError(f"Quote {quote_id} not found")
        if row.expires_at <= current:
            raise QuoteNotFoundError(f"Quote {quote_id} expired")
        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {user_id} not found")
        return QuoteDTO(
            quote_id=row.id,
            model_slug=row.model_slug,
            user_credit_price=row.user_credit_price,
            currency="credits",
            params=dict(row.params or {}),
            expires_at=row.expires_at,
            available=wallet.balance - wallet.reserved,
            template_id=row.template_id,
            template_slug=row.template_slug,
            template_version=row.template_version,
            template_inputs=dict(row.template_inputs),
            template_snapshot=dict(row.template_snapshot),
            routing_snapshot=(
                dict(row.snapshot["routing"])
                if isinstance((row.snapshot or {}).get("routing"), dict)
                else {
                    "version": 0,
                    "primary": {
                        "provider": row.snapshot.get("provider"),
                        "provider_model_id": row.snapshot.get("provider_model_id"),
                        "provider_cost_units": row.snapshot.get("provider_cost_units", 0),
                    },
                    "fallback": None,
                }
            ),
        )


class WalletQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._wallets = WalletRepository(session)

    async def get_balance(self, user_id: UUID) -> WalletBalanceDTO:
        wallet = await self._wallets.get_by_user_id(user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {user_id} not found")
        return WalletBalanceDTO(
            balance=wallet.balance,
            reserved=wallet.reserved,
            available=wallet.balance - wallet.reserved,
        )
