"""Mini-app surface for recurring subscriptions.

The mini-app cannot charge anyone itself: Telegram only bills a subscription through an
invoice link created with `subscription_period`. So `POST /subscriptions/checkout` returns
a link for the client to open, and credits appear only once Telegram delivers the charge to
the bot. Nothing here grants credits.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_current_user,
    get_db_session,
    get_payment_gateway,
    get_settings_dep,
)
from kelbet.config import Settings
from kelbet.payments.gateway import SubscriptionGateway
from kelbet.services.auth import SessionUser
from kelbet.services.payment import payment_new_purchase_allowed, payment_support_url
from kelbet.services.subscription import SubscriptionService, SubscriptionStateDTO

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionPlanResponse(BaseModel):
    slug: str
    plan: str
    name: str
    description: str
    monthly_credits: int
    stars: int
    kzt_price: int | None


class SubscriptionStateResponse(BaseModel):
    status: str
    plan: str
    plan_slug: str
    plan_name: str
    monthly_credits: int
    stars: int
    current_period_end: str | None
    cancel_at_period_end: bool
    renewal_count: int
    renewal_failed: bool


class SubscriptionPlansResponse(BaseModel):
    items: list[SubscriptionPlanResponse]
    subscriptions_enabled: bool
    current: SubscriptionStateResponse | None
    period_days: int
    terms_url: str
    terms_version: str
    refund_policy_url: str
    support_url: str


class SubscriptionCheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=64)
    terms_accepted: bool
    terms_version: str | None = Field(default=None, min_length=1, max_length=32)


class SubscriptionCheckoutResponse(BaseModel):
    subscription_id: str
    plan_slug: str
    plan_name: str
    stars: int
    monthly_credits: int
    period_days: int
    invoice_url: str
    terms_url: str
    refund_policy_url: str


class SubscriptionCancelResponse(BaseModel):
    subscription_id: str
    cancel_at_period_end: bool
    access_until: str | None


def _state_response(state: SubscriptionStateDTO) -> SubscriptionStateResponse:
    return SubscriptionStateResponse(
        status=state.status.value,
        plan=state.plan.value,
        plan_slug=state.plan_slug,
        plan_name=state.plan_name,
        monthly_credits=state.monthly_credits,
        stars=state.stars,
        current_period_end=(
            state.current_period_end.isoformat() if state.current_period_end is not None else None
        ),
        cancel_at_period_end=state.cancel_at_period_end,
        renewal_count=state.renewal_count,
        renewal_failed=state.renewal_failed,
    )


@router.get("/plans", response_model=SubscriptionPlansResponse)
async def list_subscription_plans(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> SubscriptionPlansResponse:
    service = SubscriptionService(session, settings)
    plans = await service.list_plans(current.language, telegram_id=current.telegram_id)
    state = await service.get_state(current.user_id, current.language)
    enabled = bool(
        settings.bot_token
        and settings.subscriptions_enabled
        and payment_new_purchase_allowed(settings, current.telegram_id)
    )
    return SubscriptionPlansResponse(
        items=[
            SubscriptionPlanResponse(
                slug=plan.slug,
                plan=plan.plan.value,
                name=plan.name,
                description=plan.description,
                monthly_credits=plan.monthly_credits,
                stars=plan.stars,
                kzt_price=plan.kzt_price,
            )
            for plan in plans
        ],
        subscriptions_enabled=enabled,
        current=_state_response(state) if state is not None else None,
        period_days=30,
        terms_url=settings.payment_terms_url,
        terms_version=settings.payment_terms_version,
        refund_policy_url=settings.payment_refund_policy_url,
        support_url=payment_support_url(settings),
    )


@router.post("/checkout", response_model=SubscriptionCheckoutResponse)
async def create_subscription_checkout(
    body: SubscriptionCheckoutRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    gateway: SubscriptionGateway = Depends(get_payment_gateway),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> SubscriptionCheckoutResponse:
    checkout = await SubscriptionService(session, settings).start_checkout(
        user_id=current.user_id,
        plan_slug=body.plan_slug,
        idempotency_key=idempotency_key,
        terms_accepted=body.terms_accepted,
        language=current.language,
        accepted_terms_version=body.terms_version,
    )
    invoice_url = await gateway.create_subscription_link(checkout)
    return SubscriptionCheckoutResponse(
        subscription_id=str(checkout.subscription_id),
        plan_slug=checkout.plan_slug,
        plan_name=checkout.plan_name,
        stars=checkout.stars,
        monthly_credits=checkout.monthly_credits,
        period_days=checkout.subscription_period_seconds // 86_400,
        invoice_url=invoice_url,
        terms_url=checkout.terms_url,
        refund_policy_url=checkout.refund_policy_url,
    )


@router.post("/cancel", response_model=SubscriptionCancelResponse)
async def cancel_subscription(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    gateway: SubscriptionGateway = Depends(get_payment_gateway),
) -> SubscriptionCancelResponse:
    """Stop renewal. Access continues to the end of the period the user already paid for."""
    result = await SubscriptionService(session, settings).request_cancel(user_id=current.user_id)
    if result.root_charge_id is not None:
        # Telegram is told after the local state is written. A failure here leaves the user
        # with the cancellation they asked for rather than an error, and reconciliation can
        # retry the remote side; the reverse order could stop the billing while our records
        # still said it was running.
        await gateway.set_subscription_cancelled(
            user_id=result.telegram_id,
            charge_id=result.root_charge_id,
            cancelled=True,
        )
    return SubscriptionCancelResponse(
        subscription_id=str(result.subscription_id),
        cancel_at_period_end=True,
        access_until=(
            result.current_period_end.isoformat() if result.current_period_end is not None else None
        ),
    )
