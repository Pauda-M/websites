"""Tenant-scoped async repository for scheduled actions.

:class:`ScheduledAction` is the Program Manager's single deferred-work
primitive; :meth:`ScheduledActionRepository.due` is the scheduler's poll — it
returns the PENDING actions whose ``run_at`` has arrived.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from sqlalchemy import select

from pb_api.agents.program_manager.db.models import ScheduledActionRow
from pb_api.agents.program_manager.domain.common import (
    FollowUpCadence,
    PMGoalType,
)
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledAction,
    ScheduledActionKind,
    ScheduledActionStatus,
    SubjectType,
)
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_scheduled_action(row: ScheduledActionRow) -> ScheduledAction:
    return ScheduledAction(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=ScheduledActionKind(row.kind),
        goal_type=PMGoalType(row.goal_type),
        run_at=row.run_at,
        status=ScheduledActionStatus(row.status),
        subject_type=SubjectType(row.subject_type) if row.subject_type is not None else None,
        subject_id=row.subject_id,
        cadence=FollowUpCadence(row.cadence) if row.cadence is not None else None,
        reason=row.reason,
        payload=dict(row.payload),
        attempts=row.attempts,
        executed_at=row.executed_at,
        last_error=row.last_error,
        created_by_agent_id=row.created_by_agent_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ScheduledActionRepository(BaseRepository):
    async def add(self, action: ScheduledAction) -> ScheduledAction:
        row = ScheduledActionRow(
            id=action.id,
            tenant_id=action.tenant_id,
            kind=action.kind.value,
            goal_type=action.goal_type.value,
            run_at=action.run_at,
            status=action.status.value,
            subject_type=action.subject_type.value if action.subject_type is not None else None,
            subject_id=action.subject_id,
            cadence=action.cadence.value if action.cadence is not None else None,
            reason=action.reason,
            payload=action.payload,
            attempts=action.attempts,
            executed_at=action.executed_at,
            last_error=action.last_error,
            created_by_agent_id=action.created_by_agent_id,
            meta=action.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_scheduled_action(row)

    async def get(self, tenant_id: uuid.UUID, action_id: uuid.UUID) -> ScheduledAction | None:
        row = await self.session.get(ScheduledActionRow, action_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_scheduled_action(row)

    async def update(self, action: ScheduledAction) -> ScheduledAction | None:
        row = await self.session.get(ScheduledActionRow, action.id)
        if row is None or row.tenant_id != action.tenant_id:
            return None
        row.kind = action.kind.value
        row.goal_type = action.goal_type.value
        row.run_at = action.run_at
        row.status = action.status.value
        row.subject_type = action.subject_type.value if action.subject_type is not None else None
        row.subject_id = action.subject_id
        row.cadence = action.cadence.value if action.cadence is not None else None
        row.reason = action.reason
        row.payload = action.payload
        row.attempts = action.attempts
        row.executed_at = action.executed_at
        row.last_error = action.last_error
        row.created_by_agent_id = action.created_by_agent_id
        row.meta = action.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_scheduled_action(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: ScheduledActionStatus | None = None,
        kind: ScheduledActionKind | None = None,
        limit: int = 200,
    ) -> list[ScheduledAction]:
        stmt = select(ScheduledActionRow).where(ScheduledActionRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(ScheduledActionRow.status == status.value)
        if kind is not None:
            stmt = stmt.where(ScheduledActionRow.kind == kind.value)
        stmt = stmt.order_by(ScheduledActionRow.run_at.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_scheduled_action(row) for row in rows]

    async def due(
        self, tenant_id: uuid.UUID, *, now: datetime, limit: int = 100
    ) -> builtins.list[ScheduledAction]:
        # ``builtins.list`` because the ``list`` method above shadows the builtin
        # for annotation resolution within this class.
        stmt = (
            select(ScheduledActionRow)
            .where(
                ScheduledActionRow.tenant_id == tenant_id,
                ScheduledActionRow.status == ScheduledActionStatus.PENDING.value,
                ScheduledActionRow.run_at <= now,
            )
            .order_by(ScheduledActionRow.run_at.asc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_scheduled_action(row) for row in rows]
