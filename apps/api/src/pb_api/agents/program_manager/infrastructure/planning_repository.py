"""Tenant-scoped async repository for Program Manager plans.

A plan's ordered :class:`PMPlanStep` blocks are serialised to JSON
(`model_dump(mode="json")`) on write and reconstructed with
:meth:`PMPlanStep.model_validate` on read. :class:`PMPlan` is created once and
never carries an ``updated_at`` — ``update`` refreshes only its mutable fields.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.agents.program_manager.db.models import PMPlanRow
from pb_api.agents.program_manager.domain.common import PMGoalType
from pb_api.agents.program_manager.domain.plan import (
    PMPlan,
    PMPlanStatus,
    PMPlanStep,
)
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_plan(row: PMPlanRow) -> PMPlan:
    return PMPlan(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        goal_id=row.goal_id,
        goal_type=PMGoalType(row.goal_type),
        objective=row.objective,
        steps=[PMPlanStep.model_validate(step) for step in row.steps],
        status=PMPlanStatus(row.status),
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class PMPlanRepository(BaseRepository):
    async def add(self, plan: PMPlan) -> PMPlan:
        row = PMPlanRow(
            id=plan.id,
            tenant_id=plan.tenant_id,
            run_id=plan.run_id,
            goal_id=plan.goal_id,
            goal_type=plan.goal_type.value,
            objective=plan.objective,
            steps=[step.model_dump(mode="json") for step in plan.steps],
            status=plan.status.value,
            meta=plan.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_plan(row)

    async def get(self, tenant_id: uuid.UUID, plan_id: uuid.UUID) -> PMPlan | None:
        row = await self.session.get(PMPlanRow, plan_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_plan(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[PMPlan]:
        stmt = select(PMPlanRow).where(PMPlanRow.tenant_id == tenant_id)
        if run_id is not None:
            stmt = stmt.where(PMPlanRow.run_id == run_id)
        stmt = stmt.order_by(PMPlanRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_plan(row) for row in rows]

    async def update(self, plan: PMPlan) -> PMPlan | None:
        row = await self.session.get(PMPlanRow, plan.id)
        if row is None or row.tenant_id != plan.tenant_id:
            return None
        row.status = plan.status.value
        row.steps = [step.model_dump(mode="json") for step in plan.steps]
        row.objective = plan.objective
        row.meta = plan.metadata
        await self.session.flush()
        return _row_to_plan(row)
