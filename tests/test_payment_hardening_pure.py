from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kelbet.config import Settings
from kelbet.payments.gateway import FakeStarsGateway, StarTransactionRecord
from kelbet.services.payment import (
    payment_new_purchase_allowed,
    payment_support_reference,
)
from kelbet.services.payment_reconciliation import fetch_star_transaction_window


def _ready_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "payments_enabled": True,
        "payment_terms_url": "https://kelbet.ai/terms",
        "payment_refund_policy_url": "https://kelbet.ai/refunds",
        "payment_terms_version": "2026-08-02-v1",
        "payment_seller_identity": "KELBET",
        "payment_finance_review_confirmed": True,
        "support_username": "kelbet_support",
        "stars_reconciliation_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_canary_gate_restricts_new_purchases_but_empty_list_means_general_rollout() -> None:
    assert payment_new_purchase_allowed(_ready_settings(), 1001) is True
    canary = _ready_settings(stars_canary_telegram_ids="1001,1002")
    assert payment_new_purchase_allowed(canary, 1001) is True
    assert payment_new_purchase_allowed(canary, 1003) is False


def test_support_reference_is_order_safe_and_does_not_expose_charge_data() -> None:
    from uuid import UUID

    reference = payment_support_reference(UUID("12345678-1234-5678-1234-567812345678"))
    assert reference == "KLB-123456781234"
    assert "charge" not in reference.lower()


@pytest.mark.asyncio
async def test_reconciliation_fetch_marks_complete_coverage() -> None:
    record = StarTransactionRecord(
        transaction_id="charge-1",
        amount=100,
        occurred_at=datetime.now(UTC),
        direction="incoming",
        partner_type="user",
        transaction_type="invoice_payment",
        telegram_user_id=1001,
        invoice_payload="kelbet:order",
    )
    result = await fetch_star_transaction_window(
        FakeStarsGateway(transactions=[record]),
        _ready_settings(stars_reconciliation_page_limit=100),
    )
    assert result.records == [record]
    assert result.coverage_complete is True
    assert result.next_offset is None
