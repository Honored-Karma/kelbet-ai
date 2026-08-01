"""Provider webhook signature verification on the unmodified request body."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from datetime import UTC, datetime

from kelbet.domain.exceptions import WebhookVerificationError


def google_webhook_secrets(serialized: str) -> list[str]:
    """Parse configured Standard Webhooks secrets used during secret rotation."""
    return [part.strip() for part in serialized.split(",") if part.strip()]


def verify_standard_webhook(
    *,
    payload: bytes,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
    signing_secrets: list[str],
    max_age_seconds: int = 300,
    now: datetime | None = None,
) -> None:
    """Verify a symmetric Standard Webhooks signature with replay protection."""
    if not signing_secrets:
        raise WebhookVerificationError("Webhook signing secret is not configured")
    if not webhook_id or not webhook_timestamp or not webhook_signature:
        raise WebhookVerificationError("Required Standard Webhooks headers are missing")
    if len(webhook_id) > 128:
        raise WebhookVerificationError("Webhook id is too long")

    try:
        timestamp = int(webhook_timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Webhook timestamp is invalid") from exc

    current = now or datetime.now(UTC)
    if abs(int(current.timestamp()) - timestamp) > max_age_seconds:
        raise WebhookVerificationError("Webhook timestamp is outside the replay window")

    candidates = [
        value
        for token in webhook_signature.split()
        for version, separator, value in [token.partition(",")]
        if separator and version == "v1" and value
    ]
    if not candidates:
        raise WebhookVerificationError("Webhook signature has no supported v1 value")

    signed_payload = (
        webhook_id.encode("utf-8") + b"." + webhook_timestamp.encode("ascii") + b"." + payload
    )
    for serialized_secret in signing_secrets:
        key = _decode_standard_secret(serialized_secret)
        expected = base64.b64encode(hmac.new(key, signed_payload, hashlib.sha256).digest()).decode(
            "ascii"
        )
        if any(hmac.compare_digest(expected, candidate) for candidate in candidates):
            return

    raise WebhookVerificationError("Webhook signature does not match")


def _decode_standard_secret(serialized: str) -> bytes:
    if not serialized.startswith("whsec_"):
        raise WebhookVerificationError("Webhook secret must use the whsec_ format")
    try:
        decoded = base64.b64decode(serialized.removeprefix("whsec_"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WebhookVerificationError("Webhook secret is not valid base64") from exc
    if not 24 <= len(decoded) <= 64:
        raise WebhookVerificationError("Webhook secret length is invalid")
    return decoded
