from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings
from kelbet.db.models import PaymentOrder, PaymentProduct, PaymentReceipt
from kelbet.domain.enums import (
    Language,
    PaymentReceiptStatus,
    PaymentStatus,
    TxReason,
)
from kelbet.domain.exceptions import (
    IdempotencyConflictError,
    PaymentProductNotFoundError,
    PaymentUnavailableError,
    PaymentValidationError,
    UserNotFoundError,
    WalletNotFoundError,
)
from kelbet.repositories.payment import PaymentRepository
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.wallet import WalletService

STARS_CURRENCY = "XTR"


@dataclass(frozen=True, slots=True)
class PaymentProductDTO:
    slug: str
    name: str
    description: str
    credits: int
    stars: int


@dataclass(frozen=True, slots=True)
class PaymentOrderDTO:
    id: UUID
    status: PaymentStatus
    invoice_payload: str
    currency: str
    total_amount: int
    credits: int
    product_slug: str
    product_name: str
    product_description: str
    terms_url: str
    expires_at: datetime
    created_at: datetime
    paid_at: datetime | None


@dataclass(frozen=True, slots=True)
class PreCheckoutResult:
    ok: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentCompletionResult:
    processed: bool
    applied: bool
    order_id: UUID | None
    credits: int
    balance: int | None
    error_code: str | None = None


class PaymentService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._payments = PaymentRepository(session)
        self._users = UserRepository(session)
        self._wallets = WalletRepository(session)
        self._wallet_service = WalletService(session)

    def _assert_available(self) -> None:
        if (
            not self._settings.payments_enabled
            or not self._settings.payment_terms_url.strip()
            or not self._settings.support_username.strip().lstrip("@")
        ):
            raise PaymentUnavailableError("Telegram Stars payments are not configured")

    async def list_products(self, language: Language) -> list[PaymentProductDTO]:
        products = await self._payments.list_products()
        return [self._product_dto(product, language) for product in products]

    async def create_order(
        self,
        *,
        user_id: UUID,
        product_slug: str,
        idempotency_key: str,
        terms_accepted: bool,
        language: Language,
        now: datetime | None = None,
    ) -> PaymentOrderDTO:
        self._assert_available()
        if not terms_accepted:
            raise PaymentValidationError("Terms must be accepted before creating an invoice")
        if not idempotency_key or len(idempotency_key) > 128:
            raise PaymentValidationError("Invalid payment idempotency key")

        product = await self._payments.get_product_by_slug(product_slug)
        if product is None:
            raise PaymentProductNotFoundError(f"Unknown payment product {product_slug}")
        existing = await self._payments.get_order_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.user_id != user_id or existing.product_snapshot.get("slug") != product.slug:
                raise IdempotencyConflictError("Payment idempotency key payload changed")
            return self._order_dto(existing, language)

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")

        current = now or datetime.now(UTC)
        order_id = uuid4()
        order = PaymentOrder(
            id=order_id,
            user_id=user_id,
            product_id=product.id,
            status=PaymentStatus.PENDING.value,
            idempotency_key=idempotency_key,
            invoice_payload=f"kelbet:{order_id.hex}",
            currency=STARS_CURRENCY,
            total_amount=product.stars,
            credits=product.credits,
            product_snapshot={
                "slug": product.slug,
                "credits": product.credits,
                "stars": product.stars,
                "localization": product.localization,
            },
            terms_version=self._settings.payment_terms_version,
            terms_accepted_at=current,
            expires_at=current + timedelta(minutes=self._settings.payment_order_ttl_minutes),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(order)
                await self._session.flush()
        except IntegrityError:
            existing = await self._payments.get_order_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            if existing.user_id != user_id or existing.product_snapshot.get("slug") != product.slug:
                raise IdempotencyConflictError("Payment idempotency key payload changed") from None
            order = existing
        return self._order_dto(order, language)

    async def validate_pre_checkout(
        self,
        *,
        telegram_id: int,
        query_id: str,
        invoice_payload: str,
        currency: str,
        total_amount: int,
        now: datetime | None = None,
    ) -> PreCheckoutResult:
        try:
            self._assert_available()
        except PaymentUnavailableError:
            return PreCheckoutResult(ok=False, error_code="payments_unavailable")
        current = now or datetime.now(UTC)
        order = await self._payments.get_order_by_payload(invoice_payload, for_update=True)
        error = await self._validate_order(
            order=order,
            telegram_id=telegram_id,
            currency=currency,
            total_amount=total_amount,
        )
        if error is not None:
            return PreCheckoutResult(ok=False, error_code=error)
        assert order is not None
        if order.expires_at <= current:
            order.status = PaymentStatus.EXPIRED.value
            await self._session.flush()
            return PreCheckoutResult(ok=False, error_code="order_expired")
        order.pre_checkout_query_id = query_id[:128]
        await self._session.flush()
        return PreCheckoutResult(ok=True)

    async def complete_payment(
        self,
        *,
        telegram_id: int,
        invoice_payload: str,
        currency: str,
        total_amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None,
        now: datetime | None = None,
    ) -> PaymentCompletionResult:
        current = now or datetime.now(UTC)
        existing = await self._payments.get_receipt_by_charge_id(telegram_payment_charge_id)
        if existing is not None:
            return await self._completion_from_receipt(existing)

        receipt = PaymentReceipt(
            telegram_user_id=telegram_id,
            telegram_payment_charge_id=telegram_payment_charge_id,
            provider_payment_charge_id=provider_payment_charge_id or None,
            invoice_payload=invoice_payload,
            currency=currency,
            total_amount=total_amount,
            status=PaymentReceiptStatus.REJECTED.value,
            error_code="processing",
            created_at=current,
            processed_at=None,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(receipt)
                await self._session.flush()
        except IntegrityError:
            existing = await self._payments.get_receipt_by_charge_id(telegram_payment_charge_id)
            if existing is None:
                raise
            return await self._completion_from_receipt(existing)

        order = await self._payments.get_order_by_payload(invoice_payload, for_update=True)
        error = await self._validate_order(
            order=order,
            telegram_id=telegram_id,
            currency=currency,
            total_amount=total_amount,
        )
        if error is None and order is not None and order.status == PaymentStatus.PAID.value:
            error = "order_already_paid"
        if error is not None or order is None:
            receipt.error_code = error or "order_not_found"
            receipt.processed_at = current
            await self._session.flush()
            return PaymentCompletionResult(
                processed=False,
                applied=False,
                order_id=order.id if order is not None else None,
                credits=0,
                balance=None,
                error_code=receipt.error_code,
            )

        existing_order_receipt = await self._payments.get_receipt_by_order_id(order.id)
        if existing_order_receipt is not None and existing_order_receipt.id != receipt.id:
            receipt.error_code = "order_already_paid"
            receipt.processed_at = current
            await self._session.flush()
            return PaymentCompletionResult(
                processed=False,
                applied=False,
                order_id=order.id,
                credits=0,
                balance=None,
                error_code=receipt.error_code,
            )

        wallet = await self._wallets.get_by_user_id(order.user_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet for user {order.user_id} not found")
        credit = await self._wallet_service.credit(
            wallet.id,
            order.credits,
            TxReason.PAYMENT_PURCHASE,
            f"stars:{telegram_payment_charge_id}",
            meta={
                "payment_order_id": str(order.id),
                "product_slug": order.product_snapshot.get("slug"),
                "stars": order.total_amount,
                "telegram_payment_charge_id": telegram_payment_charge_id,
            },
        )
        order.status = PaymentStatus.PAID.value
        order.ledger_transaction_id = credit.transaction_id
        order.paid_at = order.paid_at or current
        receipt.order_id = order.id
        receipt.status = PaymentReceiptStatus.PROCESSED.value
        receipt.error_code = None
        receipt.processed_at = current
        await self._session.flush()
        return PaymentCompletionResult(
            processed=True,
            applied=credit.applied,
            order_id=order.id,
            credits=order.credits,
            balance=credit.balance,
        )

    async def list_history(
        self,
        *,
        user_id: UUID,
        language: Language,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PaymentOrderDTO]:
        rows = await self._payments.list_orders_for_user(
            user_id,
            limit=limit,
            offset=offset,
        )
        return [self._order_dto(row, language) for row in rows]

    async def _validate_order(
        self,
        *,
        order: PaymentOrder | None,
        telegram_id: int,
        currency: str,
        total_amount: int,
    ) -> str | None:
        if order is None:
            return "order_not_found"
        user = await self._users.get_by_id(order.user_id)
        if user is None or user.telegram_id != telegram_id:
            return "buyer_mismatch"
        if currency != STARS_CURRENCY or order.currency != currency:
            return "currency_mismatch"
        if total_amount != order.total_amount:
            return "amount_mismatch"
        if order.status not in {PaymentStatus.PENDING.value, PaymentStatus.PAID.value}:
            return "order_not_payable"
        return None

    async def _completion_from_receipt(
        self,
        receipt: PaymentReceipt,
    ) -> PaymentCompletionResult:
        if receipt.status != PaymentReceiptStatus.PROCESSED.value or receipt.order_id is None:
            return PaymentCompletionResult(
                processed=False,
                applied=False,
                order_id=receipt.order_id,
                credits=0,
                balance=None,
                error_code=receipt.error_code,
            )
        order = await self._payments.get_order_by_payload(receipt.invoice_payload)
        if order is None:
            return PaymentCompletionResult(
                processed=False,
                applied=False,
                order_id=receipt.order_id,
                credits=0,
                balance=None,
                error_code="order_not_found",
            )
        wallet = await self._wallets.get_by_user_id(order.user_id)
        return PaymentCompletionResult(
            processed=True,
            applied=False,
            order_id=order.id,
            credits=order.credits,
            balance=wallet.balance if wallet is not None else None,
        )

    def _product_dto(
        self,
        product: PaymentProduct,
        language: Language,
    ) -> PaymentProductDTO:
        localized = _localized(product.localization, language)
        return PaymentProductDTO(
            slug=product.slug,
            name=str(localized.get("name") or product.slug),
            description=str(localized.get("description") or ""),
            credits=product.credits,
            stars=product.stars,
        )

    def _order_dto(self, order: PaymentOrder, language: Language) -> PaymentOrderDTO:
        localization = order.product_snapshot.get("localization")
        localized = _localized(localization if isinstance(localization, dict) else {}, language)
        return PaymentOrderDTO(
            id=order.id,
            status=PaymentStatus(order.status),
            invoice_payload=order.invoice_payload,
            currency=order.currency,
            total_amount=order.total_amount,
            credits=order.credits,
            product_slug=str(order.product_snapshot.get("slug") or ""),
            product_name=str(localized.get("name") or order.product_snapshot.get("slug") or ""),
            product_description=str(localized.get("description") or ""),
            terms_url=self._settings.payment_terms_url,
            expires_at=order.expires_at,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )


def _localized(localization: dict[str, Any], language: Language) -> dict[str, Any]:
    value = localization.get(language.value) or localization.get(Language.RU.value) or {}
    return value if isinstance(value, dict) else {}
