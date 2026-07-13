"""Scheduler — the Program Manager's single home for deferred work.

Owns the lifecycle of :class:`ScheduledAction`: creating due-dated work, listing
what is due, and recording execution/failure/cancellation. The Program Manager's
``SCHEDULE_NEXT`` lifecycle step and its follow-up engine both funnel through
here, so there is exactly one scheduling mechanism (no duplicated timers).
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from pb_api.agents.program_manager.domain.common import FollowUpCadence, PMGoalType, utcnow
from pb_api.agents.program_manager.domain.events import PMEventType
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledAction,
    ScheduledActionKind,
    ScheduledActionStatus,
    SubjectType,
)
from pb_api.agents.program_manager.infrastructure.scheduling_repository import (
    ScheduledActionRepository,
)
from pb_api.cognitive.services.event_processor import EventProcessor


class Scheduler:
    def __init__(self, actions: ScheduledActionRepository, events: EventProcessor) -> None:
        self._actions = actions
        self._events = events

    async def schedule(
        self,
        *,
        tenant_id: uuid.UUID,
        run_at: datetime,
        goal_type: PMGoalType,
        kind: ScheduledActionKind = ScheduledActionKind.TASK,
        subject_type: SubjectType | None = None,
        subject_id: uuid.UUID | None = None,
        cadence: FollowUpCadence | None = None,
        reason: str = "",
        payload: dict[str, object] | None = None,
        created_by_agent_id: uuid.UUID | None = None,
    ) -> ScheduledAction:
        action = await self._actions.add(
            ScheduledAction(
                tenant_id=tenant_id,
                kind=kind,
                goal_type=goal_type,
                run_at=run_at,
                subject_type=subject_type,
                subject_id=subject_id,
                cadence=cadence,
                reason=reason,
                payload=payload or {},
                created_by_agent_id=created_by_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.ACTION_SCHEDULED,
            tenant_id=tenant_id,
            aggregate_id=action.id,
            payload={
                "kind": kind.value,
                "goal_type": goal_type.value,
                "run_at": run_at.isoformat(),
            },
        )
        return action

    async def get(self, tenant_id: uuid.UUID, action_id: uuid.UUID) -> ScheduledAction | None:
        return await self._actions.get(tenant_id, action_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: ScheduledActionStatus | None = None,
        kind: ScheduledActionKind | None = None,
    ) -> builtins.list[ScheduledAction]:
        return await self._actions.list(tenant_id, status=status, kind=kind)

    async def due(
        self, tenant_id: uuid.UUID, *, now: datetime | None = None, limit: int = 100
    ) -> builtins.list[ScheduledAction]:
        return await self._actions.due(tenant_id, now=now or utcnow(), limit=limit)

    async def mark_executed(
        self, tenant_id: uuid.UUID, action_id: uuid.UUID, *, now: datetime | None = None
    ) -> ScheduledAction | None:
        action = await self._actions.get(tenant_id, action_id)
        if action is None:
            return None
        action.status = ScheduledActionStatus.EXECUTED
        action.executed_at = now or utcnow()
        action.attempts += 1
        action.last_error = None
        updated = await self._actions.update(action)
        await self._events.record(
            event_type=PMEventType.ACTION_DUE_EXECUTED,
            tenant_id=tenant_id,
            aggregate_id=action_id,
            payload={"goal_type": action.goal_type.value},
        )
        return updated

    async def mark_failed(
        self, tenant_id: uuid.UUID, action_id: uuid.UUID, *, error: str
    ) -> ScheduledAction | None:
        action = await self._actions.get(tenant_id, action_id)
        if action is None:
            return None
        action.status = ScheduledActionStatus.FAILED
        action.attempts += 1
        action.last_error = error
        return await self._actions.update(action)

    async def cancel(self, tenant_id: uuid.UUID, action_id: uuid.UUID) -> ScheduledAction | None:
        action = await self._actions.get(tenant_id, action_id)
        if action is None:
            return None
        action.status = ScheduledActionStatus.CANCELLED
        updated = await self._actions.update(action)
        await self._events.record(
            event_type=PMEventType.ACTION_CANCELLED,
            tenant_id=tenant_id,
            aggregate_id=action_id,
            payload={},
        )
        return updated
