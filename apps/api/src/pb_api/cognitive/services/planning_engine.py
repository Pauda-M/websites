"""Planning Engine: decompose a goal/objective into a plan (a DAG of tasks).

Decomposition is deterministic here: an explicit task list, or — when a goal has
child goals — one task per child. A future planner (LLM-assisted) replaces the
decomposition step without changing the plan representation.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.planning import Plan, PlanStatus, PlanTask
from pb_api.cognitive.repositories.goals import GoalRepository
from pb_api.cognitive.repositories.planning import PlanRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class PlanningEngine:
    def __init__(
        self,
        plan_repo: PlanRepository,
        goal_repo: GoalRepository,
        events: EventProcessor,
    ) -> None:
        self._plans = plan_repo
        self._goals = goal_repo
        self._events = events

    async def create_plan(
        self,
        *,
        tenant_id: uuid.UUID,
        objective: str,
        tasks: list[PlanTask] | None = None,
        goal_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
    ) -> Plan:
        resolved_tasks = list(tasks) if tasks else []
        if not resolved_tasks and goal_id is not None:
            resolved_tasks = await self._decompose_goal(tenant_id, goal_id)
        plan = Plan(
            tenant_id=tenant_id,
            goal_id=goal_id,
            agent_id=agent_id,
            objective=objective,
            tasks=resolved_tasks,
            status=PlanStatus.DRAFT,
        )
        stored = await self._plans.add(plan)
        await self._events.record(
            event_type=EventType.AGENT_PLAN_CREATED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"objective": objective, "task_count": len(resolved_tasks)},
        )
        return stored

    async def _decompose_goal(self, tenant_id: uuid.UUID, goal_id: uuid.UUID) -> list[PlanTask]:
        children = await self._goals.children(tenant_id, goal_id)
        return [
            PlanTask(
                key=f"goal-{child.id}",
                title=child.title,
                description=child.description,
                priority=child.priority,
            )
            for child in sorted(children, key=lambda goal: goal.priority)
        ]

    async def get(self, tenant_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None:
        return await self._plans.get(tenant_id, plan_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        goal_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: PlanStatus | None = None,
    ) -> list[Plan]:
        return await self._plans.list(tenant_id, goal_id=goal_id, agent_id=agent_id, status=status)

    async def set_status(
        self, tenant_id: uuid.UUID, plan_id: uuid.UUID, status: PlanStatus
    ) -> Plan | None:
        plan = await self._plans.get(tenant_id, plan_id)
        if plan is None:
            return None
        plan.status = status
        return await self._plans.update(plan)
