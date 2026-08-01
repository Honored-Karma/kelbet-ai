"""Grant test credits to an existing KELBET user through the immutable wallet ledger."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import get_settings
from kelbet.db.session import build_session_factory
from kelbet.domain.enums import TxReason
from kelbet.repositories.user import UserRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.wallet import WalletService

MAX_SINGLE_GRANT = 1_000_000
REFERENCE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,63}$")


class GrantCreditsError(RuntimeError):
    """Raised when an operator grant cannot be safely applied."""


@dataclass(frozen=True, slots=True)
class GrantCreditsResult:
    telegram_id: int
    username: str | None
    amount: int
    applied: bool
    balance_before: int
    balance_after: int
    reserved: int
    available_after: int
    transaction_id: UUID | None
    idempotency_key: str

    def as_json(self) -> str:
        payload = asdict(self)
        payload["transaction_id"] = (
            str(self.transaction_id) if self.transaction_id is not None else None
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)


def grant_idempotency_key(telegram_id: int, reference: str) -> str:
    if telegram_id <= 0:
        raise ValueError("Telegram ID must be positive")
    if not REFERENCE_PATTERN.fullmatch(reference):
        raise ValueError(
            "Reference must be 3-64 characters and contain only letters, numbers, ., _, : or -"
        )
    return f"admin-grant:{telegram_id}:{reference}"


async def grant_credits(
    session: AsyncSession,
    *,
    telegram_id: int,
    amount: int,
    reference: str,
    idempotency_key: str | None = None,
    source: str = "operator_cli",
    operator_user_id: UUID | None = None,
) -> GrantCreditsResult:
    if amount <= 0 or amount > MAX_SINGLE_GRANT:
        raise ValueError(f"Amount must be between 1 and {MAX_SINGLE_GRANT}")

    users = UserRepository(session)
    wallets = WalletRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    if user is None:
        raise GrantCreditsError(
            f"User with Telegram ID {telegram_id} was not found. Open the bot and run /start first."
        )

    wallet = await wallets.get_by_user_id_for_update(user.id)
    if wallet is None:
        raise GrantCreditsError(f"Wallet for Telegram ID {telegram_id} was not found")

    balance_before = wallet.balance
    effective_key = idempotency_key or grant_idempotency_key(telegram_id, reference)
    if len(effective_key) > 128:
        raise ValueError("Idempotency key must not exceed 128 characters")
    result = await WalletService(session).credit(
        wallet.id,
        amount,
        TxReason.ADMIN_ADJUST,
        effective_key,
        meta={
            "source": source,
            "reference": reference,
            "telegram_id": telegram_id,
            "operator_user_id": str(operator_user_id) if operator_user_id else None,
        },
    )
    await session.refresh(wallet)

    return GrantCreditsResult(
        telegram_id=telegram_id,
        username=user.username,
        amount=amount,
        applied=result.applied,
        balance_before=balance_before,
        balance_after=wallet.balance,
        reserved=wallet.reserved,
        available_after=wallet.available,
        transaction_id=result.transaction_id,
        idempotency_key=effective_key,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-id", type=int, required=True)
    parser.add_argument("--amount", type=int, required=True)
    parser.add_argument(
        "--reference",
        required=True,
        help="Unique grant reference. Reusing it will not credit the wallet twice.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that this command changes a production wallet.",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("--confirm is required to change a wallet")
    return args


async def _run(args: argparse.Namespace) -> int:
    factory = build_session_factory(get_settings())
    try:
        async with factory() as session, session.begin():
            result = await grant_credits(
                session,
                telegram_id=args.telegram_id,
                amount=args.amount,
                reference=args.reference,
            )
    except (GrantCreditsError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    print(result.as_json())
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(_arguments())))


if __name__ == "__main__":
    main()
