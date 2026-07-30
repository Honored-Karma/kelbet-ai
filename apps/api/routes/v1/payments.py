from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_current_user,
    get_db_session,
    get_payment_gateway,
    get_settings_dep,
)
from kelbet.config import Settings
from kelbet.payments.gateway import PaymentInvoiceGateway
from kelbet.services.auth import SessionUser
from kelbet.services.payment import PaymentOrderDTO, PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentProductResponse(BaseModel):
    slug: str
    name: str
    description: str
    credits: int
    stars: int


class PaymentProductsResponse(BaseModel):
    items: list[PaymentProductResponse]
    payments_enabled: bool
    terms_url: str


class CreatePaymentOrderRequest(BaseModel):
    product_slug: str = Field(min_length=1, max_length=64)
    terms_accepted: bool


class PaymentOrderResponse(BaseModel):
    id: str
    status: str
    product_slug: str
    product_name: str
    credits: int
    currency: str
    total_amount: int
    invoice_url: str | None = None
    expires_at: str
    created_at: str
    paid_at: str | None


class PaymentHistoryResponse(BaseModel):
    items: list[PaymentOrderResponse]


def _order_response(
    order: PaymentOrderDTO,
    *,
    invoice_url: str | None = None,
) -> PaymentOrderResponse:
    return PaymentOrderResponse(
        id=str(order.id),
        status=order.status.value,
        product_slug=order.product_slug,
        product_name=order.product_name,
        credits=order.credits,
        currency=order.currency,
        total_amount=order.total_amount,
        invoice_url=invoice_url,
        expires_at=order.expires_at.isoformat(),
        created_at=order.created_at.isoformat(),
        paid_at=order.paid_at.isoformat() if order.paid_at else None,
    )


@router.get("/products", response_model=PaymentProductsResponse)
async def list_payment_products(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> PaymentProductsResponse:
    products = await PaymentService(session, settings).list_products(current.language)
    enabled = bool(
        settings.payments_enabled
        and settings.bot_token
        and settings.payment_terms_url.strip()
        and settings.support_username.strip().lstrip("@")
    )
    return PaymentProductsResponse(
        items=[
            PaymentProductResponse(
                slug=item.slug,
                name=item.name,
                description=item.description,
                credits=item.credits,
                stars=item.stars,
            )
            for item in products
        ],
        payments_enabled=enabled,
        terms_url=settings.payment_terms_url,
    )


@router.post("/orders", response_model=PaymentOrderResponse)
async def create_payment_order(
    body: CreatePaymentOrderRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    gateway: PaymentInvoiceGateway = Depends(get_payment_gateway),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> PaymentOrderResponse:
    order = await PaymentService(session, settings).create_order(
        user_id=current.user_id,
        product_slug=body.product_slug,
        idempotency_key=idempotency_key,
        terms_accepted=body.terms_accepted,
        language=current.language,
    )
    invoice_url = await gateway.create_invoice_link(order)
    return _order_response(order, invoice_url=invoice_url)


@router.get("/history", response_model=PaymentHistoryResponse)
async def payment_history(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaymentHistoryResponse:
    orders = await PaymentService(session, settings).list_history(
        user_id=current.user_id,
        language=current.language,
        limit=limit,
        offset=offset,
    )
    return PaymentHistoryResponse(items=[_order_response(order) for order in orders])
