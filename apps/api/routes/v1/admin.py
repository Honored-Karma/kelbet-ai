from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_db_session, get_operator, require_admin
from kelbet.domain.enums import ModerationReviewStatus
from kelbet.services.admin import AdminService, OperatorContext

router = APIRouter(prefix="/admin", tags=["admin"])
SAFE_CODE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,63}$"


class OperatorMeResponse(BaseModel):
    user_id: UUID
    telegram_id: int
    username: str | None
    role: str
    bootstrap: bool
    capabilities: list[str]


class ItemsResponse(BaseModel):
    items: list[dict[str, Any]]


class UserDetailResponse(BaseModel):
    id: str
    telegram_id: int
    username: str | None
    is_blocked: bool
    language: str
    plan: str
    blocked_at: str | None
    blocked_reason: str | None
    created_at: str
    wallet: dict[str, Any] | None


class PaymentsResponse(BaseModel):
    orders: list[dict[str, Any]]
    receipts: list[dict[str, Any]]


class ControlsResponse(BaseModel):
    models: list[dict[str, Any]]
    feature_flags: list[dict[str, Any]]
    provider_health: list[dict[str, Any]]
    payment_products: list[dict[str, Any]]
    templates: list[dict[str, Any]]


class PaymentReconciliationResponse(BaseModel):
    refunds: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    latest_run: dict[str, Any] | None


class ReferralAdminResponse(BaseModel):
    items: list[dict[str, Any]]


class ActionReasonRequest(BaseModel):
    reason: str = Field(pattern=SAFE_CODE)
    reference: str = Field(pattern=SAFE_CODE)


class GrantCreditsRequest(ActionReasonRequest):
    amount: int = Field(ge=1, le=1_000_000)


class SetEnabledRequest(ActionReasonRequest):
    enabled: bool


class SetTemplateRequest(ActionReasonRequest):
    enabled: bool
    display_order: int = Field(ge=0, le=10_000)


class ReviewModerationRequest(ActionReasonRequest):
    outcome: Literal["confirmed_violation", "false_positive", "needs_escalation"]


class AdminActionResponse(BaseModel):
    id: str
    action_id: str
    operator_user_id: str
    operator_role: str
    action: str
    object_type: str
    object_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    reference: str
    correlation_id: str
    created_at: str


def _service(
    request: Request,
    session: AsyncSession,
    operator: OperatorContext,
) -> AdminService:
    return AdminService(
        session,
        operator,
        correlation_id=UUID(request.state.correlation_id),
    )


def _action_response(event: Any) -> AdminActionResponse:
    return AdminActionResponse.model_validate(AdminService.audit_payload(event))


@router.get("/me", response_model=OperatorMeResponse)
async def operator_me(
    operator: OperatorContext = Depends(get_operator),
) -> OperatorMeResponse:
    capabilities = ["read"]
    if operator.can_write:
        capabilities.append("write")
    return OperatorMeResponse(
        user_id=operator.user_id,
        telegram_id=operator.telegram_id,
        username=operator.username,
        role=operator.role.value,
        bootstrap=operator.bootstrap,
        capabilities=capabilities,
    )


@router.get("/users", response_model=ItemsResponse)
async def search_users(
    request: Request,
    q: str = Query(min_length=1, max_length=255),
    limit: int = Query(default=20, ge=1, le=50),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ItemsResponse:
    items = await _service(request, session, operator).search_users(q, limit=limit)
    return ItemsResponse(items=items)


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: UUID,
    request: Request,
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> UserDetailResponse:
    payload = await _service(request, session, operator).get_user(user_id)
    return UserDetailResponse.model_validate(payload)


@router.get("/users/{user_id}/ledger", response_model=ItemsResponse)
async def get_ledger(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ItemsResponse:
    items = await _service(request, session, operator).list_ledger(
        user_id, limit=limit, offset=offset
    )
    return ItemsResponse(items=items)


@router.get("/users/{user_id}/generations", response_model=ItemsResponse)
async def get_generations(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ItemsResponse:
    items = await _service(request, session, operator).list_generations(
        user_id, limit=limit, offset=offset
    )
    return ItemsResponse(items=items)


@router.get("/users/{user_id}/payments", response_model=PaymentsResponse)
async def get_payments(
    user_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentsResponse:
    payload = await _service(request, session, operator).list_payments(
        user_id, limit=limit, offset=offset
    )
    return PaymentsResponse.model_validate(payload)


@router.get("/controls", response_model=ControlsResponse)
async def get_controls(
    request: Request,
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ControlsResponse:
    payload = await _service(request, session, operator).list_controls()
    return ControlsResponse.model_validate(payload)


@router.get("/payment-reconciliation", response_model=PaymentReconciliationResponse)
async def get_payment_reconciliation(
    request: Request,
    status: Literal["open", "resolved", "needs_review"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentReconciliationResponse:
    payload = await _service(request, session, operator).list_payment_reconciliation(
        status=status, limit=limit, offset=offset
    )
    return PaymentReconciliationResponse.model_validate(payload)


@router.get("/audit", response_model=ItemsResponse)
async def get_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ItemsResponse:
    items = await _service(request, session, operator).list_audit(limit=limit, offset=offset)
    return ItemsResponse(items=items)


@router.get("/referrals", response_model=ReferralAdminResponse)
async def get_referrals(
    request: Request,
    status: Literal["pending", "eligible", "credited", "cancelled", "needs_review"] | None = Query(
        default=None
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralAdminResponse:
    items = await _service(request, session, operator).list_referrals(
        status=status, limit=limit, offset=offset
    )
    return ReferralAdminResponse(items=items)


@router.get("/moderation", response_model=ItemsResponse)
async def get_moderation_queue(
    request: Request,
    status: ModerationReviewStatus = Query(default=ModerationReviewStatus.OPEN),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    operator: OperatorContext = Depends(get_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ItemsResponse:
    items = await _service(request, session, operator).list_moderation_queue(
        review_status=status,
        limit=limit,
        offset=offset,
    )
    return ItemsResponse(items=items)


@router.post("/users/{user_id}/grant-credits", response_model=AdminActionResponse)
async def grant_credits(
    user_id: UUID,
    body: GrantCreditsRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).grant(
        user_id=user_id,
        amount=body.amount,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/moderation/{decision_id}/review", response_model=AdminActionResponse)
async def review_moderation_decision(
    decision_id: UUID,
    body: ReviewModerationRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).review_moderation_decision(
        decision_id=decision_id,
        review_outcome=body.outcome,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/generations/{generation_id}/refund", response_model=AdminActionResponse)
async def refund_generation(
    generation_id: UUID,
    body: ActionReasonRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).refund_generation(
        generation_id=generation_id,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/payments/{order_id}/refund", response_model=AdminActionResponse)
async def request_payment_refund(
    order_id: UUID,
    body: ActionReasonRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).request_payment_refund(
        order_id=order_id,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/payment-refunds/{refund_id}/retry", response_model=AdminActionResponse)
async def retry_payment_refund(
    refund_id: UUID,
    body: ActionReasonRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).retry_payment_refund(
        refund_id=refund_id,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/users/{user_id}/block", response_model=AdminActionResponse)
async def block_user(
    user_id: UUID,
    body: ActionReasonRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_user_blocked(
        user_id=user_id,
        blocked=True,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.post("/users/{user_id}/unblock", response_model=AdminActionResponse)
async def unblock_user(
    user_id: UUID,
    body: ActionReasonRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_user_blocked(
        user_id=user_id,
        blocked=False,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.patch("/catalog/{slug}", response_model=AdminActionResponse)
async def set_model_enabled(
    slug: str,
    body: SetEnabledRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_model_enabled(
        slug=slug,
        enabled=body.enabled,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.patch("/feature-flags/{key}", response_model=AdminActionResponse)
async def set_feature_flag_enabled(
    key: str,
    body: SetEnabledRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_feature_flag_enabled(
        key=key,
        enabled=body.enabled,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.patch("/templates/{slug}", response_model=AdminActionResponse)
async def set_template_config(
    slug: str,
    body: SetTemplateRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_template_config(
        slug=slug,
        enabled=body.enabled,
        display_order=body.display_order,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)


@router.patch("/payment-products/{slug}", response_model=AdminActionResponse)
async def set_payment_product_enabled(
    slug: str,
    body: SetEnabledRequest,
    request: Request,
    action_id: UUID = Header(alias="Idempotency-Key"),
    operator: OperatorContext = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminActionResponse:
    event = await _service(request, session, operator).set_payment_product_enabled(
        slug=slug,
        enabled=body.enabled,
        reason=body.reason,
        reference=body.reference,
        action_id=action_id,
    )
    return _action_response(event)
