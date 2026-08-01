from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from apps.api.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kelbet.auth import MemoryReplayStore, sign_init_data
from kelbet.catalog.seed_db import seed_catalog
from kelbet.config import Settings, get_settings
from kelbet.db.models import (
    AuditEvent,
    ModerationDecision,
    OperatorMembership,
    PaymentRefund,
    User,
    Wallet,
)
from kelbet.domain.enums import Language
from kelbet.payments import seed_payment_products
from kelbet.queue import InlineGenerationQueue
from kelbet.services.admin import _safe_reconciliation_details
from kelbet.services.generation_runner import GenerationRunner
from kelbet.services.payment import PaymentService
from kelbet.services.referral import ReferralService
from kelbet.services.registration import RegistrationService

BOT_TOKEN = "999:TEST-TOKEN-ADMIN"
ADMIN_TELEGRAM_ID = 980_001
SUPPORT_TELEGRAM_ID = 980_002
TARGET_TELEGRAM_ID = 980_003


def test_reconciliation_details_are_redacted_before_api_serialization() -> None:
    assert _safe_reconciliation_details(
        {
            "telegram_amount": 20,
            "classification": "external_reversal",
            "payment_charge_id": "secret-charge",
            "raw_payload": "secret-payload",
            "nested": {"secret": True},
        }
    ) == {
        "telegram_amount": 20,
        "classification": "external_reversal",
    }


def _signed_init_data(telegram_id: int) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "username": f"operator_test_{telegram_id}",
            "language_code": "ru",
            "first_name": "Operator",
        },
        separators=(",", ":"),
    )
    return sign_init_data(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": user,
            "query_id": f"admin-test-{telegram_id}",
        },
        BOT_TOKEN,
    )


@pytest.fixture
def admin_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("WELCOME_CREDITS", "20")
    monkeypatch.setenv("ADMIN_ENABLED", "true")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TELEGRAM_IDS", str(ADMIN_TELEGRAM_ID))
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("STARS_REFUNDS_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_TERMS_URL", "https://kelbet.ai/terms")
    monkeypatch.setenv("PAYMENT_REFUND_POLICY_URL", "https://kelbet.ai/refunds")
    monkeypatch.setenv("PAYMENT_TERMS_VERSION", "test-v1")
    monkeypatch.setenv("PAYMENT_SELLER_IDENTITY", "KELBET TEST SELLER")
    monkeypatch.setenv("PAYMENT_FINANCE_REVIEW_CONFIRMED", "true")
    monkeypatch.setenv("SUPPORT_USERNAME", "kelbet_support")
    monkeypatch.setenv("REFERRAL_BOT_USERNAME", "kelbet_test_bot")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
async def admin_client(
    session_factory: async_sessionmaker[AsyncSession],
    admin_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    async with session_factory() as session, session.begin():
        await seed_catalog(session)
        await seed_payment_products(session)
    app = create_app(testing=True)
    app.state.session_factory = session_factory
    app.state.replay_store = MemoryReplayStore()
    app.state.generation_queue = InlineGenerationQueue()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app


async def _login(client: AsyncClient, telegram_id: int) -> str:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": _signed_init_data(telegram_id)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


def _headers(token: str, action_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if action_id is not None:
        headers["Idempotency-Key"] = action_id
    return headers


async def _seed_support(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        user = (
            await session.execute(select(User).where(User.telegram_id == SUPPORT_TELEGRAM_ID))
        ).scalar_one()
        session.add(OperatorMembership(user_id=user.id, role="support"))


@pytest.mark.asyncio
async def test_referrals_are_feature_gated_visible_to_support_and_flag_audited(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
    admin_settings: Settings,
) -> None:
    client, _app = admin_client
    admin_token, support_token, target_token = await asyncio.gather(
        _login(client, ADMIN_TELEGRAM_ID),
        _login(client, SUPPORT_TELEGRAM_ID),
        _login(client, TARGET_TELEGRAM_ID),
    )
    await _seed_support(session_factory)

    action_id = str(uuid4())
    enabled = await client.patch(
        "/api/v1/admin/feature-flags/referrals",
        headers=_headers(admin_token, action_id),
        json={"enabled": True, "reason": "referral_test", "reference": "release-ref"},
    )
    assert enabled.status_code == 200, enabled.text

    async with session_factory() as session, session.begin():
        admin = await session.scalar(select(User).where(User.telegram_id == ADMIN_TELEGRAM_ID))
        assert admin is not None
        summary = await ReferralService(session, admin_settings).get_summary(admin.id)
        assert summary.code
        await RegistrationService(session, admin_settings).register_with_language(
            telegram_id=980_004,
            username="referred_operator_test",
            language=Language.KK,
            referral_code=summary.code,
        )

    support_view = await client.get("/api/v1/admin/referrals", headers=_headers(support_token))
    assert support_view.status_code == 200, support_view.text
    item = support_view.json()["items"][0]
    assert item["status"] == "pending"
    assert "code" not in item
    assert "telegram_id" not in item

    normal_view = await client.get("/api/v1/admin/referrals", headers=_headers(target_token))
    assert normal_view.status_code == 403
    own_summary = await client.get("/api/v1/referrals/me", headers=_headers(admin_token))
    assert own_summary.status_code == 200
    assert own_summary.json()["link"].endswith(f"ref_{summary.code}")

    audit = await client.get("/api/v1/admin/audit", headers=_headers(admin_token))
    assert audit.status_code == 200
    assert any(
        row["action"] == "feature_flag.set_enabled" and row["action_id"] == action_id
        for row in audit.json()["items"]
    )


@pytest.mark.asyncio
async def test_moderation_queue_support_read_admin_review_and_safe_audit(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = admin_client
    admin_token, support_token, _target_token = await asyncio.gather(
        _login(client, ADMIN_TELEGRAM_ID),
        _login(client, SUPPORT_TELEGRAM_ID),
        _login(client, TARGET_TELEGRAM_ID),
    )
    await _seed_support(session_factory)
    async with session_factory() as session, session.begin():
        target = await session.scalar(select(User).where(User.telegram_id == TARGET_TELEGRAM_ID))
        assert target is not None
        decision = ModerationDecision(
            user_id=target.id,
            generation_id=None,
            asset_ids=[],
            context="generation",
            idempotency_key="queue-test-1",
            input_hash="a" * 64,
            mode="report",
            outcome="report",
            reason_codes=["violent_wrongdoing"],
            policy_version="test-v1",
            provider="rules",
            provider_model="ru-kk-baseline-v1",
            provider_request_id=None,
            error_code=None,
            review_status="open",
        )
        session.add(decision)
        await session.flush()
        decision_id = decision.id

    queue = await client.get(
        "/api/v1/admin/moderation",
        headers=_headers(support_token),
    )
    assert queue.status_code == 200, queue.text
    item = queue.json()["items"][0]
    assert item["id"] == str(decision_id)
    assert item["input_hash"] == "a" * 64
    assert "prompt" not in item
    assert "provider_request_id" not in item

    body = {
        "outcome": "false_positive",
        "reason": "policy_review",
        "reference": "case-queue-1",
    }
    denied = await client.post(
        f"/api/v1/admin/moderation/{decision_id}/review",
        headers=_headers(support_token, str(uuid4())),
        json=body,
    )
    assert denied.status_code == 403

    action_id = str(uuid4())
    reviewed = await client.post(
        f"/api/v1/admin/moderation/{decision_id}/review",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    replay = await client.post(
        f"/api/v1/admin/moderation/{decision_id}/review",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    assert reviewed.status_code == replay.status_code == 200
    assert reviewed.json() == replay.json()
    assert reviewed.json()["action"] == "moderation.review"

    async with session_factory() as session:
        stored = await session.get(ModerationDecision, decision_id)
        audit = await session.scalar(
            select(AuditEvent).where(AuditEvent.action_id == UUID(action_id))
        )
    assert stored is not None
    assert stored.review_status == "reviewed"
    assert stored.review_outcome == "false_positive"
    assert audit is not None
    serialized = json.dumps(
        {"before": audit.before_data, "after": audit.after_data}, sort_keys=True
    )
    assert "prompt" not in serialized
    assert "violent_wrongdoing" not in serialized


@pytest.mark.asyncio
async def test_admin_rbac_grant_replay_and_safe_audit(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = admin_client
    admin_token, support_token, target_token = await asyncio.gather(
        _login(client, ADMIN_TELEGRAM_ID),
        _login(client, SUPPORT_TELEGRAM_ID),
        _login(client, TARGET_TELEGRAM_ID),
    )
    await _seed_support(session_factory)

    normal_me = await client.get("/api/v1/admin/me", headers=_headers(target_token))
    assert normal_me.status_code == 403

    support_me = await client.get("/api/v1/admin/me", headers=_headers(support_token))
    assert support_me.status_code == 200
    assert support_me.json()["role"] == "support"
    assert support_me.json()["capabilities"] == ["read"]

    search = await client.get(
        "/api/v1/admin/users",
        params={"q": str(TARGET_TELEGRAM_ID)},
        headers=_headers(support_token),
    )
    assert search.status_code == 200
    target_id = search.json()["items"][0]["id"]

    denied = await client.post(
        f"/api/v1/admin/users/{target_id}/grant-credits",
        headers=_headers(support_token, str(uuid4())),
        json={"amount": 7, "reason": "support_case", "reference": "ticket-001"},
    )
    assert denied.status_code == 403

    action_id = str(uuid4())
    first = await client.post(
        f"/api/v1/admin/users/{target_id}/grant-credits",
        headers=_headers(admin_token, action_id),
        json={"amount": 7, "reason": "support_case", "reference": "ticket-001"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["after"]["applied"] is True
    assert first.json()["after"]["balance"] == 27

    replay = await client.post(
        f"/api/v1/admin/users/{target_id}/grant-credits",
        headers=_headers(admin_token, action_id),
        json={"amount": 7, "reason": "support_case", "reference": "ticket-001"},
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()

    conflict = await client.post(
        f"/api/v1/admin/users/{target_id}/grant-credits",
        headers=_headers(admin_token, action_id),
        json={"amount": 8, "reason": "support_case", "reference": "ticket-001"},
    )
    assert conflict.status_code == 409

    async with session_factory() as session:
        target = (
            await session.execute(select(User).where(User.telegram_id == TARGET_TELEGRAM_ID))
        ).scalar_one()
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == target.id))
        ).scalar_one()
        audits = list((await session.execute(select(AuditEvent))).scalars().all())
    assert wallet.balance == 27
    assert len(audits) == 1
    serialized = json.dumps(
        {"before": audits[0].before_data, "after": audits[0].after_data},
        sort_keys=True,
    )
    assert "prompt" not in serialized
    assert "token" not in serialized
    assert "invoice_payload" not in serialized

    async with session_factory() as session:
        stored = (await session.execute(select(AuditEvent))).scalar_one()
        stored.reason = "tampered"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_blocked_user_cannot_start_paid_generation(
    admin_client: tuple[AsyncClient, object],
) -> None:
    client, _app = admin_client
    admin_token = await _login(client, ADMIN_TELEGRAM_ID)
    target_token = await _login(client, TARGET_TELEGRAM_ID)
    search = await client.get(
        "/api/v1/admin/users",
        params={"q": str(TARGET_TELEGRAM_ID)},
        headers=_headers(admin_token),
    )
    target_id = search.json()["items"][0]["id"]
    quote = await client.post(
        "/api/v1/wallet/quote",
        headers=_headers(target_token),
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
        },
    )
    assert quote.status_code == 200, quote.text

    blocked = await client.post(
        f"/api/v1/admin/users/{target_id}/block",
        headers=_headers(admin_token, str(uuid4())),
        json={"reason": "abuse_guard", "reference": "case-002"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["after"]["blocked"] is True

    generation = await client.post(
        "/api/v1/generations",
        headers=_headers(target_token, "blocked-generation-1"),
        json={"quote_id": quote.json()["quote_id"], "prompt": "private prompt"},
    )
    assert generation.status_code == 403
    assert generation.json()["error"]["code"] == "user_blocked"

    unblocked = await client.post(
        f"/api/v1/admin/users/{target_id}/unblock",
        headers=_headers(admin_token, str(uuid4())),
        json={"reason": "review_complete", "reference": "case-002"},
    )
    assert unblocked.status_code == 200
    created = await client.post(
        "/api/v1/generations",
        headers=_headers(target_token, "unblocked-generation-1"),
        json={"quote_id": quote.json()["quote_id"], "prompt": "private prompt"},
    )
    assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_generation_refund_is_ledger_backed_and_idempotent(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, app = admin_client
    admin_token = await _login(client, ADMIN_TELEGRAM_ID)
    target_token = await _login(client, TARGET_TELEGRAM_ID)
    quote = await client.post(
        "/api/v1/wallet/quote",
        headers=_headers(target_token),
        json={
            "model_slug": "mock-image",
            "params": {"resolution": "720p", "aspect_ratio": "1:1"},
        },
    )
    created = await client.post(
        "/api/v1/generations",
        headers=_headers(target_token, "refund-generation-create"),
        json={"quote_id": quote.json()["quote_id"], "prompt": "not audited"},
    )
    assert created.status_code == 201, created.text
    generation_id = created.json()["id"]

    queue: InlineGenerationQueue = app.state.generation_queue  # type: ignore[attr-defined]
    storage = app.state.object_storage  # type: ignore[attr-defined]
    queued = queue.pop_all()
    assert len(queued) == 1
    async with session_factory() as session, session.begin():
        status = await GenerationRunner(session, storage).process(queued[0][0])
    assert status.value == "succeeded"

    action_id = str(uuid4())
    body = {"reason": "provider_quality", "reference": "case-003"}
    first = await client.post(
        f"/api/v1/admin/generations/{generation_id}/refund",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    second = await client.post(
        f"/api/v1/admin/generations/{generation_id}/refund",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["after"]["applied"] is True

    async with session_factory() as session:
        target = (
            await session.execute(select(User).where(User.telegram_id == TARGET_TELEGRAM_ID))
        ).scalar_one()
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == target.id))
        ).scalar_one()
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "generation.refund")
        )
    assert wallet.balance == 20
    assert audit_count == 1


@pytest.mark.asyncio
async def test_stars_refund_is_admin_only_audited_and_visible_to_support(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = admin_client
    admin_token, support_token, _target_token = await asyncio.gather(
        _login(client, ADMIN_TELEGRAM_ID),
        _login(client, SUPPORT_TELEGRAM_ID),
        _login(client, TARGET_TELEGRAM_ID),
    )
    await _seed_support(session_factory)
    payment_settings = Settings(
        payments_enabled=True,
        payment_terms_url="https://kelbet.ai/terms",
        payment_refund_policy_url="https://kelbet.ai/refunds",
        payment_terms_version="test-v1",
        payment_seller_identity="KELBET TEST SELLER",
        payment_finance_review_confirmed=True,
        support_username="kelbet_support",
    )
    async with session_factory() as session, session.begin():
        target = await session.scalar(select(User).where(User.telegram_id == TARGET_TELEGRAM_ID))
        assert target is not None
        payment = PaymentService(session, payment_settings)
        order = await payment.create_order(
            user_id=target.id,
            product_slug="starter",
            idempotency_key="admin-stars-refund-order",
            terms_accepted=True,
            language=Language.RU,
        )
        completed = await payment.complete_payment(
            telegram_id=TARGET_TELEGRAM_ID,
            invoice_payload=order.invoice_payload,
            currency="XTR",
            total_amount=order.total_amount,
            telegram_payment_charge_id="admin-stars-charge",
            provider_payment_charge_id=None,
        )
        assert completed.processed
        order_id = order.id

    body = {"reason": "buyer_request", "reference": "case-stars-refund"}
    denied = await client.post(
        f"/api/v1/admin/payments/{order_id}/refund",
        headers=_headers(support_token, str(uuid4())),
        json=body,
    )
    assert denied.status_code == 403

    action_id = str(uuid4())
    first = await client.post(
        f"/api/v1/admin/payments/{order_id}/refund",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    replay = await client.post(
        f"/api/v1/admin/payments/{order_id}/refund",
        headers=_headers(admin_token, action_id),
        json=body,
    )
    assert first.status_code == replay.status_code == 200, first.text
    assert first.json() == replay.json()
    assert first.json()["action"] == "payment.refund.request"
    assert first.json()["after"]["status"] == "requested"

    visible = await client.get(
        "/api/v1/admin/payment-reconciliation",
        headers=_headers(support_token),
    )
    assert visible.status_code == 200, visible.text
    assert visible.json()["refunds"][0]["order_id"] == str(order_id)

    async with session_factory() as session:
        refund_count = await session.scalar(select(func.count()).select_from(PaymentRefund))
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "payment.refund.request")
        )
    assert refund_count == 1
    assert audit_count == 1


@pytest.mark.asyncio
async def test_concurrent_admin_grants_preserve_wallet_invariant(
    admin_client: tuple[AsyncClient, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _app = admin_client
    admin_token = await _login(client, ADMIN_TELEGRAM_ID)
    await _login(client, TARGET_TELEGRAM_ID)
    search = await client.get(
        "/api/v1/admin/users",
        params={"q": str(TARGET_TELEGRAM_ID)},
        headers=_headers(admin_token),
    )
    target_id = search.json()["items"][0]["id"]

    async def apply(amount: int, reference: str) -> int:
        response = await client.post(
            f"/api/v1/admin/users/{target_id}/grant-credits",
            headers=_headers(admin_token, str(uuid4())),
            json={"amount": amount, "reason": "concurrent_test", "reference": reference},
        )
        assert response.status_code == 200, response.text
        return int(response.json()["after"]["balance"])

    await asyncio.gather(apply(7, "parallel-001"), apply(9, "parallel-002"))

    async with session_factory() as session:
        target = (
            await session.execute(select(User).where(User.telegram_id == TARGET_TELEGRAM_ID))
        ).scalar_one()
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == target.id))
        ).scalar_one()
        audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))
    assert wallet.balance == 36
    assert wallet.reserved == 0
    assert wallet.available == 36
    assert audit_count == 2


@pytest.mark.asyncio
async def test_admin_controls_are_authorized_and_audited(
    admin_client: tuple[AsyncClient, object],
) -> None:
    client, _app = admin_client
    admin_token = await _login(client, ADMIN_TELEGRAM_ID)
    target_token = await _login(client, TARGET_TELEGRAM_ID)

    controls = await client.get("/api/v1/admin/controls", headers=_headers(admin_token))
    assert controls.status_code == 200, controls.text
    assert controls.json()["models"]
    assert controls.json()["feature_flags"]
    assert {item["status"] for item in controls.json()["provider_health"]} <= {
        "disabled",
        "unconfigured",
        "degraded",
        "healthy",
        "ready",
    }
    assert controls.json()["payment_products"]
    assert len(controls.json()["templates"]) == 11

    normal_controls = await client.get("/api/v1/admin/controls", headers=_headers(target_token))
    assert normal_controls.status_code == 403

    mutations = [
        ("/api/v1/admin/catalog/mock-image", False, "catalog_toggle"),
        (
            f"/api/v1/admin/feature-flags/{controls.json()['feature_flags'][0]['key']}",
            not controls.json()["feature_flags"][0]["enabled"],
            "flag_toggle",
        ),
        ("/api/v1/admin/payment-products/starter", False, "sku_toggle"),
    ]
    for path, enabled, reason in mutations:
        response = await client.patch(
            path,
            headers=_headers(admin_token, str(uuid4())),
            json={"enabled": enabled, "reason": reason, "reference": "release-001"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["after"]["enabled"] is enabled

    template = controls.json()["templates"][0]
    template_mutation = await client.patch(
        f"/api/v1/admin/templates/{template['slug']}",
        headers=_headers(admin_token, str(uuid4())),
        json={
            "enabled": False,
            "display_order": 900,
            "reason": "template_order",
            "reference": "release-001",
        },
    )
    assert template_mutation.status_code == 200, template_mutation.text
    assert template_mutation.json()["after"] == {
        "applied": True,
        "enabled": False,
        "display_order": 900,
    }

    search = await client.get(
        "/api/v1/admin/users",
        params={"q": str(TARGET_TELEGRAM_ID)},
        headers=_headers(admin_token),
    )
    target_id = search.json()["items"][0]["id"]
    payments = await client.get(
        f"/api/v1/admin/users/{target_id}/payments",
        headers=_headers(admin_token),
    )
    assert payments.status_code == 200
    assert payments.json() == {"orders": [], "receipts": []}

    audit = await client.get("/api/v1/admin/audit", headers=_headers(admin_token))
    assert audit.status_code == 200
    assert {item["action"] for item in audit.json()["items"]} == {
        "catalog.set_enabled",
        "feature_flag.set_enabled",
        "payment_product.set_enabled",
        "generation_template.configure",
    }
