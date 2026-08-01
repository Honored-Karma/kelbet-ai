from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import LabeledPrice

from kelbet.domain.exceptions import PaymentUnavailableError
from kelbet.services.payment import PaymentOrderDTO


class PaymentInvoiceGateway(Protocol):
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str: ...


@dataclass(frozen=True, slots=True)
class StarTransactionRecord:
    transaction_id: str
    amount: int
    occurred_at: datetime
    direction: Literal["incoming", "outgoing"]
    partner_type: str
    transaction_type: str | None


class StarsGatewayError(RuntimeError):
    """Safe gateway failure classification; never carries a raw Telegram response."""

    def __init__(self, code: str, *, transient: bool, outcome_unknown: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.transient = transient
        self.outcome_unknown = outcome_unknown


class StarsOperationsGateway(PaymentInvoiceGateway, Protocol):
    async def refund_star_payment(self, user_id: int, charge_id: str) -> bool: ...

    async def get_star_transactions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[StarTransactionRecord]: ...


class AiogramStarsGateway:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        return await self._bot.create_invoice_link(
            title=order.product_name[:32],
            description=order.product_description[:255],
            payload=order.invoice_payload,
            currency=order.currency,
            prices=[
                LabeledPrice(
                    label=f"{order.credits} KELBET credits",
                    amount=order.total_amount,
                )
            ],
        )

    async def refund_star_payment(self, user_id: int, charge_id: str) -> bool:
        try:
            return await self._bot.refund_star_payment(
                user_id=user_id,
                telegram_payment_charge_id=charge_id,
            )
        except TelegramAPIError as exc:
            raise _safe_aiogram_error(exc) from None

    async def get_star_transactions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[StarTransactionRecord]:
        try:
            response = await self._bot.get_star_transactions(offset=offset, limit=limit)
        except TelegramAPIError as exc:
            raise _safe_aiogram_error(exc) from None
        records: list[StarTransactionRecord] = []
        for transaction in response.transactions:
            partner = transaction.source or transaction.receiver
            if partner is None or (transaction.source is None) == (transaction.receiver is None):
                raise StarsGatewayError("invalid_transaction_direction", transient=False)
            partner_type = str(partner.type)
            if "." in partner_type:
                partner_type = partner_type.rsplit(".", 1)[-1].lower()
            records.append(
                StarTransactionRecord(
                    transaction_id=transaction.id,
                    amount=transaction.amount,
                    occurred_at=transaction.date,
                    direction="incoming" if transaction.source is not None else "outgoing",
                    partner_type=partner_type[:32],
                    transaction_type=(
                        str(value)[:64]
                        if (value := getattr(partner, "transaction_type", None)) is not None
                        else None
                    ),
                )
            )
        return records


def _safe_aiogram_error(exc: TelegramAPIError) -> StarsGatewayError:
    if isinstance(exc, TelegramRetryAfter):
        return StarsGatewayError("telegram_rate_limited", transient=True)
    if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
        return StarsGatewayError("telegram_result_unknown", transient=True, outcome_unknown=True)
    if isinstance(
        exc,
        (
            TelegramBadRequest,
            TelegramUnauthorizedError,
            TelegramForbiddenError,
        ),
    ):
        return StarsGatewayError("telegram_request_rejected", transient=False)
    return StarsGatewayError("telegram_api_error", transient=False)


class DisabledPaymentGateway:
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        raise PaymentUnavailableError("Telegram Stars gateway is disabled")

    async def refund_star_payment(self, user_id: int, charge_id: str) -> bool:
        raise PaymentUnavailableError("Telegram Stars refund gateway is disabled")

    async def get_star_transactions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[StarTransactionRecord]:
        raise PaymentUnavailableError("Telegram Stars reconciliation gateway is disabled")


class MockPaymentGateway:
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        return f"https://t.me/$kelbet_{order.id.hex}"


class FakeStarsGateway(MockPaymentGateway):
    """Deterministic fake for timeout, partial-failure and reconciliation tests."""

    def __init__(
        self,
        *,
        transactions: list[StarTransactionRecord] | None = None,
        refund_outcomes: list[bool | Exception] | None = None,
    ) -> None:
        self.transactions = list(transactions or [])
        self.refund_outcomes: deque[bool | Exception] = deque(refund_outcomes or [True])
        self.refund_calls: list[tuple[int, str]] = []
        self.transaction_calls: list[tuple[int, int]] = []

    async def refund_star_payment(self, user_id: int, charge_id: str) -> bool:
        self.refund_calls.append((user_id, charge_id))
        outcome = self.refund_outcomes.popleft() if self.refund_outcomes else True
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def get_star_transactions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[StarTransactionRecord]:
        self.transaction_calls.append((offset, limit))
        return self.transactions[offset : offset + limit]
