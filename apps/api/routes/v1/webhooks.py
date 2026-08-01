from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session, get_generation_queue, get_settings_dep
from kelbet.config import Settings
from kelbet.domain.exceptions import KelbetError, WebhookVerificationError
from kelbet.queue import GenerationQueue
from kelbet.services.webhook import WebhookService
from kelbet.webhook_security import google_webhook_secrets, verify_standard_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookResponse(BaseModel):
    ok: bool
    duplicate: bool = False


@router.post(
    "/{provider}",
    response_model=WebhookResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"type": "object", "additionalProperties": True}}
            },
        }
    },
)
async def provider_webhook(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    queue: GenerationQueue = Depends(get_generation_queue),
    settings: Settings = Depends(get_settings_dep),
) -> WebhookResponse:
    normalized_provider = provider.strip().lower()
    if not normalized_provider or len(normalized_provider) > 32:
        raise KelbetError("Invalid provider")

    raw_body = await request.body()
    if not raw_body or len(raw_body) > settings.webhook_max_body_bytes:
        raise KelbetError("Webhook body is empty or too large")
    try:
        decoded = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KelbetError("Webhook body is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise KelbetError("Webhook body must be a JSON object")
    payload: dict[str, Any] = decoded

    if normalized_provider == "google":
        event_id = request.headers.get("webhook-id") or ""
        verify_standard_webhook(
            payload=raw_body,
            webhook_id=event_id,
            webhook_timestamp=request.headers.get("webhook-timestamp"),
            webhook_signature=request.headers.get("webhook-signature"),
            signing_secrets=google_webhook_secrets(settings.google_webhook_signing_secrets),
            max_age_seconds=settings.google_webhook_max_age_seconds,
        )
    else:
        expected = settings.webhook_secret
        supplied = request.headers.get("x-kelbet-webhook-secret") or ""
        if not expected or not secrets.compare_digest(supplied, expected):
            raise WebhookVerificationError("Invalid generic webhook secret")
        event_id = request.headers.get("x-event-id") or str(
            payload.get("event_id") or payload.get("id") or ""
        )
    if not event_id or len(event_id) > 128:
        raise KelbetError("Missing or invalid event id")

    result = await WebhookService(session).handle(
        provider=normalized_provider,
        event_id=event_id,
        payload=payload,
        payload_hash=hashlib.sha256(raw_body).hexdigest(),
    )
    if result.enqueue and result.generation_id is not None and result.modality is not None:
        await queue.enqueue(result.generation_id, modality=result.modality)
    return WebhookResponse(ok=True, duplicate=result.duplicate)
