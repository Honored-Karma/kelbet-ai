from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings, get_settings
from kelbet.db.models import GenerationTemplate
from kelbet.domain.enums import Language, TemplateKind
from kelbet.domain.exceptions import (
    GenerationTemplateNotFoundError,
    GenerationTemplateValidationError,
)
from kelbet.repositories.catalog import GenerationTemplateRepository


@dataclass(frozen=True, slots=True)
class GenerationTemplateDTO:
    id: UUID
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


@dataclass(frozen=True, slots=True)
class TemplateSelection:
    entity: GenerationTemplate
    inputs: dict[str, str]
    snapshot: dict[str, Any]


def _localized(values: dict[str, Any], language: Language, *, fallback: str = "") -> dict[str, str]:
    entry = values.get(language.value) or values.get(Language.RU.value) or {}
    if not isinstance(entry, dict):
        return {"name": fallback, "description": ""}
    return {
        "name": str(entry.get("name") or fallback),
        "description": str(entry.get("description") or ""),
    }


def validate_template_inputs(
    template: GenerationTemplate, values: dict[str, object] | None
) -> dict[str, str]:
    raw = values or {}
    fields = template.required_inputs.get("fields", [])
    if not isinstance(fields, list):
        raise GenerationTemplateValidationError("Template field schema is invalid")
    specs: dict[str, dict[str, object]] = {}
    for field in fields:
        if isinstance(field, dict) and isinstance(field.get("key"), str):
            specs[str(field["key"])] = field
    unknown = set(raw) - set(specs)
    if unknown:
        raise GenerationTemplateValidationError("Unknown template input field")

    cleaned: dict[str, str] = {}
    for key, spec in specs.items():
        value = raw.get(key, "")
        if not isinstance(value, str):
            raise GenerationTemplateValidationError("Template inputs must be text")
        text = unicodedata.normalize("NFC", value).strip()
        required = spec.get("required") is True
        raw_max_length = spec.get("max_length")
        if not isinstance(raw_max_length, int):
            raise GenerationTemplateValidationError("Template field schema is invalid")
        max_length = raw_max_length
        if required and not text:
            raise GenerationTemplateValidationError(f"Template input {key} is required")
        if max_length <= 0 or len(text) > max_length:
            raise GenerationTemplateValidationError(f"Template input {key} is too long")
        if any(unicodedata.category(char).startswith("C") for char in text):
            raise GenerationTemplateValidationError(
                f"Template input {key} contains control characters"
            )
        if text:
            cleaned[key] = text
    return cleaned


def validate_asset_count(template_snapshot: dict[str, Any], count: int) -> None:
    required = template_snapshot.get("required_inputs")
    required = required if isinstance(required, dict) else {}
    assets = required.get("assets")
    assets = assets if isinstance(assets, dict) else {}
    minimum = int(assets.get("min") or 0)
    maximum = int(assets.get("max") or 0)
    if count < minimum or (maximum >= 0 and count > maximum):
        raise GenerationTemplateValidationError(
            f"Template requires between {minimum} and {maximum} source assets"
        )


class GenerationTemplateService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._templates = GenerationTemplateRepository(session)

    async def list_active(
        self, *, language: Language, kind: TemplateKind | None = None
    ) -> list[GenerationTemplateDTO]:
        if not self._settings.server_templates_enabled:
            return []
        rows = await self._templates.list_active(kind=kind.value if kind else None)
        return [self._to_dto(row, language) for row in rows]

    async def select_for_quote(
        self,
        *,
        template_id: UUID,
        template_inputs: dict[str, object] | None,
        model_modality: str,
    ) -> TemplateSelection:
        if not self._settings.server_templates_enabled:
            raise GenerationTemplateNotFoundError("Server templates are disabled")
        row = await self._templates.get_by_id(template_id)
        if row is None or not row.enabled:
            raise GenerationTemplateNotFoundError("Generation template is unavailable")
        if model_modality not in row.compatible_modalities:
            raise GenerationTemplateValidationError(
                "Generation template is incompatible with the selected model"
            )
        inputs = validate_template_inputs(row, template_inputs)
        return TemplateSelection(
            entity=row,
            inputs=inputs,
            snapshot=self.snapshot(row),
        )

    async def require_current(self, template_id: UUID) -> GenerationTemplate:
        row = await self._templates.get_by_id(template_id)
        if row is None or not row.enabled or not self._settings.server_templates_enabled:
            raise GenerationTemplateNotFoundError("Generation template is unavailable")
        return row

    @staticmethod
    def snapshot(row: GenerationTemplate) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "slug": row.slug,
            "version": row.version,
            "kind": row.kind,
            "localization": dict(row.localization),
            "prompt_preset": dict(row.prompt_preset),
            "aspect_ratio": row.aspect_ratio,
            "duration_sec": row.duration_sec,
            "compatible_modalities": list(row.compatible_modalities),
            "required_inputs": dict(row.required_inputs),
            "preview_metadata": dict(row.preview_metadata),
            "compositor": row.compositor,
        }

    @staticmethod
    def _to_dto(row: GenerationTemplate, language: Language) -> GenerationTemplateDTO:
        preset = row.prompt_preset.get(language.value) or row.prompt_preset.get("ru") or ""
        return GenerationTemplateDTO(
            id=row.id,
            slug=row.slug,
            version=row.version,
            kind=TemplateKind(row.kind),
            display_order=row.display_order,
            localization=_localized(row.localization, language, fallback=row.slug),
            prompt_preset=str(preset),
            aspect_ratio=row.aspect_ratio,
            duration_sec=row.duration_sec,
            compatible_modalities=list(row.compatible_modalities),
            required_inputs=dict(row.required_inputs),
            preview_metadata=dict(row.preview_metadata),
            compositor=row.compositor,
        )
