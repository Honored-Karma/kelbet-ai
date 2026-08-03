"""Return credit holds that outlived whatever was supposed to finalise them.

Every generation path releases its own hold on failure, so in a healthy system
this sweeper finds nothing. It exists for the paths that cannot clean up after
themselves: a hold whose generation row never got linked, a job whose queue
message vanished before any worker claimed it, or a process that died between
reserving credits and recording why. Those holds are invisible to the user and
permanent — the balance still reads full while `available` is quietly short —
so something has to enforce the deadline that `reserve()` already writes.

The one rule that matters: a hold belonging to a job that is still active is
never touched. Capture happens when the job finishes, and releasing credits
from under work that is still running would let a user's generation succeed
without paying for it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models.credit_reservation import CreditReservation
from kelbet.domain.enums import GenerationStatus
from kelbet.observability import get_metrics
from kelbet.repositories.generation import GenerationRepository
from kelbet.repositories.wallet import WalletRepository
from kelbet.services.generation_sm import is_terminal
from kelbet.services.wallet import WalletService

logger = logging.getLogger(__name__)


class ReservationSweeper:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._wallets = WalletRepository(session)
        self._jobs = GenerationRepository(session)
        self._wallet_svc = WalletService(session)

    async def sweep(self, *, now: datetime | None = None, limit: int = 100) -> list[UUID]:
        current = now or datetime.now(UTC)
        candidates = await self._wallets.list_expired_held_reservations(now=current, limit=limit)
        expired: list[UUID] = []

        for reservation in candidates:
            reason = await self._strand_reason(reservation)
            if reason is None:
                continue

            result = await self._wallet_svc.expire(reservation.id, now=current)
            if not result.applied:
                continue

            expired.append(reservation.id)
            get_metrics().incr(
                "reservation_expired.total",
                tags={"reason": reason},
            )
            logger.warning(
                "reservation_expired reservation_id=%s generation_id=%s amount=%s reason=%s",
                reservation.id,
                reservation.generation_id,
                reservation.amount,
                reason,
            )

        if expired:
            await self._session.flush()
        return expired

    async def _strand_reason(self, reservation: CreditReservation) -> str | None:
        """Why this hold is safe to return, or None when it must be left alone."""

        job = None
        if reservation.generation_id is not None:
            job = await self._jobs.get_by_id(reservation.generation_id)
            if job is None:
                return "generation_missing"
        else:
            # The reservation names no generation. Before calling it abandoned,
            # ask the other side of the link: a caller that set the job's
            # reservation_id without setting this column would otherwise have a
            # live job's credits handed back underneath it.
            job = await self._jobs.get_by_reservation_id(reservation.id)
            if job is None:
                # Genuinely unbound. Whatever was creating the generation
                # stopped before any job could reference the hold.
                return "unbound"

        status = GenerationStatus(job.status)
        if not is_terminal(status):
            # Still live. The runner owns this hold and will capture or release
            # it; the sweeper's deadline is not a reason to interfere.
            return None

        if status is GenerationStatus.SUCCEEDED:
            # A successful job should have captured its hold. Reaching here means
            # the capture was lost, which is a bug worth seeing rather than a
            # balance worth keeping — hand the credits back and name it.
            return "succeeded_uncaptured"

        return f"terminal_{status.value}"
