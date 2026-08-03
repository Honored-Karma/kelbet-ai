from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_current_user, get_db_session, get_settings_dep
from kelbet.config import Settings
from kelbet.services.auth import SessionUser
from kelbet.services.catalog import QuoteService, WalletQueryService

router = APIRouter(prefix="/wallet", tags=["wallet"])


class WalletBalanceResponse(BaseModel):
    balance: int
    reserved: int
    available: int
    currency: str = "credits"


class QuoteRequest(BaseModel):
    model_slug: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    template_id: UUID | None = None
    template_inputs: dict[str, object] = Field(default_factory=dict)


class QuoteResponse(BaseModel):
    quote_id: str
    model_slug: str
    user_credit_price: int
    currency: str
    params: dict[str, Any]
    expires_at: str
    available: int
    template_id: str | None
    template_slug: str | None
    template_version: int | None
    template_inputs: dict[str, Any]


class CreditTransactionResponse(BaseModel):
    id: str
    type: str
    reason: str
    amount: int
    balance_after: int
    created_at: str
    generation_id: str | None


class CreditLedgerResponse(BaseModel):
    items: list[CreditTransactionResponse]


@router.get("/transactions", response_model=CreditLedgerResponse)
async def list_wallet_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CreditLedgerResponse:
    """Every credit movement on the caller's own wallet, newest first."""

    rows = await WalletQueryService(session).list_transactions(
        current.user_id,
        limit=limit,
        offset=offset,
    )
    return CreditLedgerResponse(
        items=[
            CreditTransactionResponse(
                id=str(row.id),
                type=row.type,
                reason=row.reason,
                amount=row.amount,
                balance_after=row.balance_after,
                created_at=row.created_at.isoformat(),
                generation_id=str(row.generation_id) if row.generation_id else None,
            )
            for row in rows
        ]
    )


@router.get("", response_model=WalletBalanceResponse)
async def get_wallet(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WalletBalanceResponse:
    balance = await WalletQueryService(session).get_balance(current.user_id)
    return WalletBalanceResponse(
        balance=balance.balance,
        reserved=balance.reserved,
        available=balance.available,
    )


@router.post("/quote", response_model=QuoteResponse)
async def create_quote(
    body: QuoteRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> QuoteResponse:
    quote = await QuoteService(session, settings).create_quote(
        user_id=current.user_id,
        telegram_id=current.telegram_id,
        model_slug=body.model_slug,
        params=body.params,
        template_id=body.template_id,
        template_inputs=body.template_inputs,
        ttl=timedelta(seconds=settings.quote_ttl_seconds),
    )
    return QuoteResponse(
        quote_id=str(quote.quote_id),
        model_slug=quote.model_slug,
        user_credit_price=quote.user_credit_price,
        currency=quote.currency,
        params=quote.params,
        expires_at=quote.expires_at.isoformat(),
        available=quote.available,
        template_id=str(quote.template_id) if quote.template_id else None,
        template_slug=quote.template_slug,
        template_version=quote.template_version,
        template_inputs=quote.template_inputs,
    )
