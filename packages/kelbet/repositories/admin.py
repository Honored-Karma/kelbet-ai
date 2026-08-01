from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.db.models import AuditEvent, OperatorMembership


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_membership(self, user_id: UUID) -> OperatorMembership | None:
        result = await self._session.execute(
            select(OperatorMembership).where(
                OperatorMembership.user_id == user_id,
                OperatorMembership.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def lock_action(self, action_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:action_id))"),
            {"action_id": str(action_id)},
        )

    async def get_audit_by_action_id(self, action_id: UUID) -> AuditEvent | None:
        result = await self._session.execute(
            select(AuditEvent).where(AuditEvent.action_id == action_id)
        )
        return result.scalar_one_or_none()

    async def append_audit(
        self,
        *,
        action_id: UUID,
        request_hash: str,
        operator_user_id: UUID,
        operator_role: str,
        action: str,
        object_type: str,
        object_id: str,
        before_data: dict[str, object],
        after_data: dict[str, object],
        reason: str,
        reference: str,
        correlation_id: UUID,
    ) -> AuditEvent:
        row = AuditEvent(
            action_id=action_id,
            request_hash=request_hash,
            operator_user_id=operator_user_id,
            operator_role=operator_role,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            reference=reference,
            correlation_id=correlation_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_audit(self, *, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
