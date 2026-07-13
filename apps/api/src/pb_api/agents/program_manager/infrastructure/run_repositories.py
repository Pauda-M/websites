"""Tenant-scoped async repositories for Program Manager runs and their tasks.

A :class:`PMRun` is the execution record of one cognitive-lifecycle pass; a
:class:`PMTask` is a unit of plan-step execution within a run. A run is opened
once (``started_at``) and never carries an ``updated_at``; ``update`` refreshes
only its mutable execution fields.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.agents.program_manager.db.models import PMRunRow, PMTaskRow
from pb_api.agents.program_manager.domain.common import (
    PMAuthorityLevel,
    PMGoalType,
    PMState,
)
from pb_api.agents.program_manager.domain.run import (
    PMRun,
    PMTask,
    PMTaskStatus,
    PMTriggerType,
)
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_run(row: PMRunRow) -> PMRun:
    return PMRun(
        id=row.id,
        tenant_id=row.tenant_id,
        agent_id=row.agent_id,
        trigger=PMTriggerType(row.trigger),
        trigger_ref=row.trigger_ref,
        input_summary=row.input_summary,
        state=PMState(row.state),
        goal_type=PMGoalType(row.goal_type) if row.goal_type is not None else None,
        goal_id=row.goal_id,
        plan_id=row.plan_id,
        organization_id=row.organization_id,
        states_visited=list(row.states_visited),
        outcome=row.outcome,
        success=row.success,
        awaiting_approval=row.awaiting_approval,
        error=row.error,
        metadata=dict(row.meta),
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


class PMRunRepository(BaseRepository):
    async def add(self, run: PMRun) -> PMRun:
        row = PMRunRow(
            id=run.id,
            tenant_id=run.tenant_id,
            agent_id=run.agent_id,
            trigger=run.trigger.value,
            trigger_ref=run.trigger_ref,
            input_summary=run.input_summary,
            state=run.state.value,
            goal_type=run.goal_type.value if run.goal_type is not None else None,
            goal_id=run.goal_id,
            plan_id=run.plan_id,
            organization_id=run.organization_id,
            states_visited=list(run.states_visited),
            outcome=run.outcome,
            success=run.success,
            awaiting_approval=run.awaiting_approval,
            error=run.error,
            meta=run.metadata,
            started_at=run.started_at,
            ended_at=run.ended_at,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_run(row)

    async def get(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> PMRun | None:
        row = await self.session.get(PMRunRow, run_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_run(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        agent_id: uuid.UUID | None = None,
        success: bool | None = None,
        awaiting_approval: bool | None = None,
        limit: int = 200,
    ) -> list[PMRun]:
        stmt = select(PMRunRow).where(PMRunRow.tenant_id == tenant_id)
        if agent_id is not None:
            stmt = stmt.where(PMRunRow.agent_id == agent_id)
        if success is not None:
            stmt = stmt.where(PMRunRow.success == success)
        if awaiting_approval is not None:
            stmt = stmt.where(PMRunRow.awaiting_approval == awaiting_approval)
        stmt = stmt.order_by(PMRunRow.started_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_run(row) for row in rows]

    async def update(self, run: PMRun) -> PMRun | None:
        row = await self.session.get(PMRunRow, run.id)
        if row is None or row.tenant_id != run.tenant_id:
            return None
        row.state = run.state.value
        row.goal_type = run.goal_type.value if run.goal_type is not None else None
        row.goal_id = run.goal_id
        row.plan_id = run.plan_id
        row.organization_id = run.organization_id
        row.states_visited = list(run.states_visited)
        row.outcome = run.outcome
        row.success = run.success
        row.awaiting_approval = run.awaiting_approval
        row.error = run.error
        row.meta = run.metadata
        row.ended_at = run.ended_at
        await self.session.flush()
        return _row_to_run(row)


def _row_to_task(row: PMTaskRow) -> PMTask:
    return PMTask(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        step_key=row.step_key,
        goal_type=PMGoalType(row.goal_type),
        objective=row.objective,
        status=PMTaskStatus(row.status),
        authority_required=PMAuthorityLevel(row.authority_required),
        requires_approval=row.requires_approval,
        approved_by=row.approved_by,
        result=row.result,
        error=row.error,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PMTaskRepository(BaseRepository):
    async def add(self, task: PMTask) -> PMTask:
        row = PMTaskRow(
            id=task.id,
            tenant_id=task.tenant_id,
            run_id=task.run_id,
            step_key=task.step_key,
            goal_type=task.goal_type.value,
            objective=task.objective,
            status=task.status.value,
            authority_required=int(task.authority_required),
            requires_approval=task.requires_approval,
            approved_by=task.approved_by,
            result=task.result,
            error=task.error,
            meta=task.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_task(row)

    async def get(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> PMTask | None:
        row = await self.session.get(PMTaskRow, task_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_task(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        status: PMTaskStatus | None = None,
        limit: int = 200,
    ) -> list[PMTask]:
        stmt = select(PMTaskRow).where(PMTaskRow.tenant_id == tenant_id)
        if run_id is not None:
            stmt = stmt.where(PMTaskRow.run_id == run_id)
        if status is not None:
            stmt = stmt.where(PMTaskRow.status == status.value)
        stmt = stmt.order_by(PMTaskRow.created_at.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_task(row) for row in rows]

    async def update(self, task: PMTask) -> PMTask | None:
        row = await self.session.get(PMTaskRow, task.id)
        if row is None or row.tenant_id != task.tenant_id:
            return None
        row.status = task.status.value
        row.requires_approval = task.requires_approval
        row.approved_by = task.approved_by
        row.result = task.result
        row.error = task.error
        row.meta = task.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_task(row)
