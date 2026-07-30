from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest

from kelbet.domain.exceptions import WebhookVerificationError
from kelbet.webhook_security import verify_standard_webhook

_KEY = b"k" * 32
_SECRET = f"whsec_{base64.b64encode(_KEY).decode('ascii')}"


def _signature(payload: bytes, webhook_id: str, timestamp: str) -> str:
    message = f"{webhook_id}.{timestamp}.".encode() + payload
    digest = base64.b64encode(hmac.new(_KEY, message, hashlib.sha256).digest()).decode()
    return f"v1,{digest}"


def test_standard_webhook_accepts_valid_signature_and_rotated_header() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    payload = b'{"type":"video.generated","data":{"id":"operations/op-1"}}'
    webhook_id = "msg_video_1"
    timestamp = str(int(now.timestamp()))
    valid = _signature(payload, webhook_id, timestamp)

    verify_standard_webhook(
        payload=payload,
        webhook_id=webhook_id,
        webhook_timestamp=timestamp,
        webhook_signature=f"v1,invalid {valid}",
        signing_secrets=[_SECRET],
        now=now,
    )


@pytest.mark.parametrize(
    ("timestamp_delta", "signature"),
    [
        (timedelta(minutes=-6), "valid"),
        (timedelta(minutes=6), "valid"),
        (timedelta(), "v1,invalid"),
    ],
)
def test_standard_webhook_rejects_replay_and_invalid_signature(
    timestamp_delta: timedelta,
    signature: str,
) -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    payload = b'{"type":"video.generated"}'
    webhook_id = "msg_video_2"
    timestamp = str(int((now + timestamp_delta).timestamp()))
    supplied = _signature(payload, webhook_id, timestamp) if signature == "valid" else signature

    with pytest.raises(WebhookVerificationError):
        verify_standard_webhook(
            payload=payload,
            webhook_id=webhook_id,
            webhook_timestamp=timestamp,
            webhook_signature=supplied,
            signing_secrets=[_SECRET],
            now=now,
        )


def test_standard_webhook_requires_serialized_secret() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    with pytest.raises(WebhookVerificationError):
        verify_standard_webhook(
            payload=b"{}",
            webhook_id="msg_video_3",
            webhook_timestamp=str(int(now.timestamp())),
            webhook_signature="v1,invalid",
            signing_secrets=["not-a-standard-secret"],
            now=now,
        )
