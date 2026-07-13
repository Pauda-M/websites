"""Repository for plans (goal decompositions into task DAGs)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import PlanRow
from pb_api.cognitive.domain.planning import Plan, PlanStatus, PlanTask
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_plan(row: PlanRow) -> Plan:
    return Plan(
        id=row.id,
        tenant_id=row.tenant_id,
        goal_id=row.goal_id,
        agent_id=row.agent_id,
        objective=row.objective,
        tasks=[PlanTask.model_validate(task) for task in row.tasks],
        status=PlanStatus(row.status),
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class PlanRepository(BaseRepository):
    async def add(self, plan: Plan) -> Plan:
        row = PlanRow(
            id=plan.id,
            tenant_id=plan.tenant_id,
            goal_id=plan.goal_id,
            agent_id=plan.agent_id,
            objective=plan.objective,
            tasks=[task.model_dump(mode="json") for task in plan.tasks],
            status=plan.status.value,
            meta=plan.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_plan(row)

    async def get(self, tenant_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None:
        row = await self.session.get(PlanRow, plan_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_plan(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        goal_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: PlanStatus | None = None,
        limit: int = 100,
    ) -> list[Plan]:
        stmt = select(PlanRow).where(PlanRow.tenant_id == tenant_id)
        if goal_id is not None:
            stmt = stmt.where(PlanRow.goal_id == goal_id)
        if agent_id is not None:
            stmt = stmt.where(PlanRow.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(PlanRow.status == status.value)
        stmt = stmt.order_by(PlanRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_plan(row) for row in rows]

    async def update(self, plan: Plan) -> Plan | None:
        row = await self.session.get(PlanRow, plan.id)
        if row is None or row.tenant_id != plan.tenant_id:
            return None
        row.status = plan.status.value
        row.tasks = [task.model_dump(mode="json") for task in plan.tasks]
        row.meta = plan.metadata
        await self.session.flush()
        return _row_to_plan(row)
