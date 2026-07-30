from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
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


class QuoteResponse(BaseModel):
    quote_id: str
    model_slug: str
    user_credit_price: int
    currency: str
    params: dict[str, Any]
    expires_at: str
    available: int


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
    )
