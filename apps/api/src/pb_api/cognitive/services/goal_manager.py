"""Goal Manager: hierarchical goals (Company → Department → Agent → Task).

Supports priority, dependencies, status, progress, and an append-only history.
Dependency and parent references are validated to keep the hierarchy sound.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.goals import (
    Goal,
    GoalHistoryEntry,
    GoalLevel,
    GoalStatus,
)
from pb_api.cognitive.repositories.goals import GoalHistoryRepository, GoalRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class GoalManager:
    def __init__(
        self,
        goal_repo: GoalRepository,
        history_repo: GoalHistoryRepository,
        events: EventProcessor,
    ) -> None:
        self._goals = goal_repo
        self._history = history_repo
        self._events = events

    async def create_goal(
        self,
        *,
        tenant_id: uuid.UUID,
        level: GoalLevel,
        title: str,
        description: str = "",
        parent_id: uuid.UUID | None = None,
        owner_agent_id: uuid.UUID | None = None,
        priority: int = 3,
        depends_on: list[uuid.UUID] | None = None,
    ) -> Goal:
        if parent_id is not None and await self._goals.get(tenant_id, parent_id) is None:
            raise ValueError("parent goal not found")
        goal = Goal(
            tenant_id=tenant_id,
            level=level,
            title=title,
            description=description,
            parent_id=parent_id,
            owner_agent_id=owner_agent_id,
            priority=priority,
            depends_on=depends_on or [],
        )
        stored = await self._goals.add(goal)
        await self._history.add(
            GoalHistoryEntry(tenant_id=tenant_id, goal_id=stored.id, change="created")
        )
        await self._events.record(
            event_type=EventType.AGENT_GOAL_CREATED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"level": level.value, "title": title},
        )
        return stored

    async def get(self, tenant_id: uuid.UUID, goal_id: uuid.UUID) -> Goal | None:
        return await self._goals.get(tenant_id, goal_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        level: GoalLevel | None = None,
        status: GoalStatus | None = None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> builtins.list[Goal]:
        return await self._goals.list(
            tenant_id, level=level, status=status, owner_agent_id=owner_agent_id
        )

    async def children(self, tenant_id: uuid.UUID, parent_id: uuid.UUID) -> builtins.list[Goal]:
        return await self._goals.children(tenant_id, parent_id)

    async def set_status(
        self, tenant_id: uuid.UUID, goal_id: uuid.UUID, status: GoalStatus
    ) -> Goal | None:
        goal = await self._goals.get(tenant_id, goal_id)
        if goal is None:
            return None
        previous = goal.status
        if status is previous:
            return goal
        if status is GoalStatus.ACTIVE:
            await self._assert_dependencies_met(tenant_id, goal)
        goal.status = status
        if status is GoalStatus.ACHIEVED:
            goal.progress = 1.0
        updated = await self._goals.update(goal)
        await self._history.add(
            GoalHistoryEntry(
                tenant_id=tenant_id,
                goal_id=goal_id,
                change=f"status: {previous.value}->{status.value}",
            )
        )
        await self._events.record(
            event_type=EventType.AGENT_GOAL_UPDATED,
            tenant_id=tenant_id,
            aggregate_id=goal_id,
            payload={"status": status.value},
        )
        return updated

    async def set_progress(
        self, tenant_id: uuid.UUID, goal_id: uuid.UUID, progress: float
    ) -> Goal | None:
        goal = await self._goals.get(tenant_id, goal_id)
        if goal is None:
            return None
        previous = goal.progress
        goal.progress = max(0.0, min(1.0, progress))
        if goal.progress >= 1.0 and goal.status is not GoalStatus.ACHIEVED:
            goal.status = GoalStatus.ACHIEVED
        updated = await self._goals.update(goal)
        await self._history.add(
            GoalHistoryEntry(
                tenant_id=tenant_id,
                goal_id=goal_id,
                change=f"progress: {previous:.2f}->{goal.progress:.2f}",
            )
        )
        return updated

    async def history(
        self, tenant_id: uuid.UUID, goal_id: uuid.UUID
    ) -> builtins.list[GoalHistoryEntry]:
        return await self._history.list(tenant_id, goal_id)

    async def _assert_dependencies_met(self, tenant_id: uuid.UUID, goal: Goal) -> None:
        for dep_id in goal.depends_on:
            dep = await self._goals.get(tenant_id, dep_id)
            if dep is None or dep.status is not GoalStatus.ACHIEVED:
                raise ValueError(f"dependency {dep_id} not achieved")
