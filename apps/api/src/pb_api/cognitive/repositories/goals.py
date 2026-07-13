"""Repositories for hierarchical goals and their append-only change history."""

from __future__ import annotations

import builtins
import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import GoalHistoryRow, GoalRow
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.domain.goals import Goal, GoalHistoryEntry, GoalLevel, GoalStatus
from pb_api.cognitive.repositories.base import (
    BaseRepository,
    json_to_uuids,
    uuids_to_json,
)


def _row_to_goal(row: GoalRow) -> Goal:
    return Goal(
        id=row.id,
        tenant_id=row.tenant_id,
        level=GoalLevel(row.level),
        parent_id=row.parent_id,
        owner_agent_id=row.owner_agent_id,
        title=row.title,
        description=row.description,
        priority=row.priority,
        status=GoalStatus(row.status),
        progress=row.progress,
        depends_on=json_to_uuids(row.depends_on),
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class GoalRepository(BaseRepository):
    async def add(self, goal: Goal) -> Goal:
        row = GoalRow(
            id=goal.id,
            tenant_id=goal.tenant_id,
            level=goal.level.value,
            parent_id=goal.parent_id,
            owner_agent_id=goal.owner_agent_id,
            title=goal.title,
            description=goal.description,
            priority=goal.priority,
            status=goal.status.value,
            progress=goal.progress,
            depends_on=uuids_to_json(goal.depends_on),
            meta=goal.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_goal(row)

    async def get(self, tenant_id: uuid.UUID, goal_id: uuid.UUID) -> Goal | None:
        row = await self.session.get(GoalRow, goal_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_goal(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        level: GoalLevel | None = None,
        status: GoalStatus | None = None,
        owner_agent_id: uuid.UUID | None = None,
        parent_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Goal]:
        stmt = select(GoalRow).where(GoalRow.tenant_id == tenant_id)
        if level is not None:
            stmt = stmt.where(GoalRow.level == level.value)
        if status is not None:
            stmt = stmt.where(GoalRow.status == status.value)
        if owner_agent_id is not None:
            stmt = stmt.where(GoalRow.owner_agent_id == owner_agent_id)
        if parent_id is not None:
            stmt = stmt.where(GoalRow.parent_id == parent_id)
        stmt = stmt.order_by(GoalRow.priority.asc(), GoalRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_goal(row) for row in rows]

    async def children(self, tenant_id: uuid.UUID, parent_id: uuid.UUID) -> builtins.list[Goal]:
        # ``builtins.list`` because the ``list`` method above shadows the builtin
        # for annotation resolution within this class.
        return await self.list(tenant_id, parent_id=parent_id)

    async def update(self, goal: Goal) -> Goal | None:
        row = await self.session.get(GoalRow, goal.id)
        if row is None or row.tenant_id != goal.tenant_id:
            return None
        row.title = goal.title
        row.description = goal.description
        row.status = goal.status.value
        row.priority = goal.priority
        row.progress = goal.progress
        row.depends_on = list(uuids_to_json(goal.depends_on))
        row.meta = goal.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_goal(row)


def _row_to_history(row: GoalHistoryRow) -> GoalHistoryEntry:
    return GoalHistoryEntry(
        id=row.id,
        tenant_id=row.tenant_id,
        goal_id=row.goal_id,
        change=row.change,
        note=row.note,
        created_at=row.created_at,
    )


class GoalHistoryRepository(BaseRepository):
    async def add(self, entry: GoalHistoryEntry) -> GoalHistoryEntry:
        row = GoalHistoryRow(
            id=entry.id,
            tenant_id=entry.tenant_id,
            goal_id=entry.goal_id,
            change=entry.change,
            note=entry.note,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_history(row)

    async def list(
        self, tenant_id: uuid.UUID, goal_id: uuid.UUID, limit: int = 200
    ) -> list[GoalHistoryEntry]:
        stmt = (
            select(GoalHistoryRow)
            .where(
                GoalHistoryRow.tenant_id == tenant_id,
                GoalHistoryRow.goal_id == goal_id,
            )
            .order_by(GoalHistoryRow.created_at.asc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_history(row) for row in rows]
