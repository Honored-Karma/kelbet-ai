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
from aiogram.types import LabeledPrice, TransactionPartnerUser

from kelbet.domain.exceptions import PaymentUnavailableError
from kelbet.services.payment import PaymentOrderDTO
from kelbet.services.subscription import SubscriptionCheckoutDTO


class PaymentInvoiceGateway(Protocol):
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str: ...


class SubscriptionGateway(Protocol):
    """The two Telegram calls a recurring subscription needs.

    Declared separately from `StarsOperationsGateway` so a test can supply these two
    without also faking refunds and star-transaction paging.
    """

    async def create_subscription_link(self, checkout: SubscriptionCheckoutDTO) -> str: ...

    async def set_subscription_cancelled(
        self, *, user_id: int, charge_id: str, cancelled: bool
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class StarTransactionRecord:
    transaction_id: str
    amount: int
    occurred_at: datetime
    direction: Literal["incoming", "outgoing"]
    partner_type: str
    transaction_type: str | None
    telegram_user_id: int | None = None
    invoice_payload: str | None = None


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

    async def create_subscription_link(self, checkout: SubscriptionCheckoutDTO) -> str:
        """Create a recurring invoice link.

        `sendInvoice` has no `subscription_period` parameter, so a subscription can only be
        offered as a link — which is why this exists instead of reusing `answer_invoice`.
        """
        try:
            return await self._bot.create_invoice_link(
                title=checkout.plan_name[:32],
                description=checkout.plan_description[:255],
                payload=checkout.invoice_payload,
                currency=checkout.currency,
                prices=[
                    LabeledPrice(
                        label=f"{checkout.monthly_credits} KELBET credits / month",
                        amount=checkout.stars,
                    )
                ],
                subscription_period=checkout.subscription_period_seconds,
            )
        except TelegramAPIError as exc:
            raise _safe_aiogram_error(exc) from None

    async def set_subscription_cancelled(
        self, *, user_id: int, charge_id: str, cancelled: bool
    ) -> bool:
        """Stop or resume renewal. Access runs to the end of the paid period either way."""
        try:
            return await self._bot.edit_user_star_subscription(
                user_id=user_id,
                telegram_payment_charge_id=charge_id,
                is_canceled=cancelled,
            )
        except TelegramAPIError as exc:
            raise _safe_aiogram_error(exc) from None

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
                    telegram_user_id=(
                        int(partner.user.id)
                        if isinstance(partner, TransactionPartnerUser)
                        else None
                    ),
                    invoice_payload=(
                        str(value)[:128]
                        if (value := getattr(partner, "invoice_payload", None))
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

    async def create_subscription_link(self, checkout: SubscriptionCheckoutDTO) -> str:
        raise PaymentUnavailableError("Telegram Stars subscription gateway is disabled")

    async def set_subscription_cancelled(
        self, *, user_id: int, charge_id: str, cancelled: bool
    ) -> bool:
        raise PaymentUnavailableError("Telegram Stars subscription gateway is disabled")

    async def refund_star_payment(self, user_id: int, charge_id: str) -> bool:
        raise PaymentUnavailableError("Telegram Stars refund gateway is disabled")

    async def get_star_transactions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[StarTransactionRecord]:
        raise PaymentUnavailableError("Telegram Stars reconciliation gateway is disabled")


class MockPaymentGateway:
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        return f"https://t.me/$kelbet_{order.id.hex}"

    async def create_subscription_link(self, checkout: SubscriptionCheckoutDTO) -> str:
        return f"https://t.me/$kelbet_sub_{checkout.subscription_id.hex}"

    async def set_subscription_cancelled(
        self, *, user_id: int, charge_id: str, cancelled: bool
    ) -> bool:
        """Accept the call. Telegram's own effect is on renewal, which a fake cannot model,
        and the state that matters to the tests is the row this service already wrote."""
        return True


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
