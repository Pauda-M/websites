"""Repository for reflections (post-task learning records)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import ReflectionRow
from pb_api.cognitive.domain.reflection import Reflection
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_reflection(row: ReflectionRow) -> Reflection:
    return Reflection(
        id=row.id,
        tenant_id=row.tenant_id,
        agent_id=row.agent_id,
        task_id=row.task_id,
        objective=row.objective,
        outcome=row.outcome,
        success=row.success,
        failure_reason=row.failure_reason,
        lessons_learned=[str(item) for item in row.lessons_learned],
        confidence=row.confidence,
        future_recommendations=[str(item) for item in row.future_recommendations],
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class ReflectionRepository(BaseRepository):
    async def add(self, reflection: Reflection) -> Reflection:
        row = ReflectionRow(
            id=reflection.id,
            tenant_id=reflection.tenant_id,
            agent_id=reflection.agent_id,
            task_id=reflection.task_id,
            objective=reflection.objective,
            outcome=reflection.outcome,
            success=reflection.success,
            failure_reason=reflection.failure_reason,
            lessons_learned=list(reflection.lessons_learned),
            confidence=reflection.confidence,
            future_recommendations=list(reflection.future_recommendations),
            meta=reflection.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_reflection(row)

    async def get(self, tenant_id: uuid.UUID, reflection_id: uuid.UUID) -> Reflection | None:
        row = await self.session.get(ReflectionRow, reflection_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_reflection(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        success: bool | None = None,
        limit: int = 100,
    ) -> list[Reflection]:
        stmt = select(ReflectionRow).where(ReflectionRow.tenant_id == tenant_id)
        if agent_id is not None:
            stmt = stmt.where(ReflectionRow.agent_id == agent_id)
        if task_id is not None:
            stmt = stmt.where(ReflectionRow.task_id == task_id)
        if success is not None:
            stmt = stmt.where(ReflectionRow.success.is_(success))
        stmt = stmt.order_by(ReflectionRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_reflection(row) for row in rows]
