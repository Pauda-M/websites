"""Follow-up engine — cadence-driven follow-ups over the Scheduler.

A deliberately thin façade: a follow-up *is* a ``ScheduledAction`` of kind
``FOLLOWUP`` whose ``run_at`` is derived from a named cadence (24h / 72h / 7d /
30d, or a custom delay). Keeping this a façade — rather than a parallel table or
timer — means every follow-up is visible, cancellable, and executable through the
one scheduling mechanism.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pb_api.agents.program_manager.application.scheduler import Scheduler
from pb_api.agents.program_manager.config import ProgramManagerSettings
from pb_api.agents.program_manager.domain.common import FollowUpCadence, PMGoalType, utcnow
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledAction,
    ScheduledActionKind,
    SubjectType,
)


class FollowUpEngine:
    def __init__(self, scheduler: Scheduler, settings: ProgramManagerSettings) -> None:
        self._scheduler = scheduler
        self._settings = settings

    async def schedule_followup(
        self,
        *,
        tenant_id: uuid.UUID,
        subject_type: SubjectType,
        subject_id: uuid.UUID,
        cadence: FollowUpCadence = FollowUpCadence.FIRST_TOUCH,
        custom_seconds: int | None = None,
        goal_type: PMGoalType = PMGoalType.FOLLOW_UP_LEAD,
        reason: str = "",
        created_by_agent_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> ScheduledAction:
        """Schedule a follow-up ``cadence`` from ``now`` against a CRM subject."""
        base = now or utcnow()
        run_at = base + self._settings.cadence_delay(cadence, custom_seconds)
        return await self._scheduler.schedule(
            tenant_id=tenant_id,
            run_at=run_at,
            goal_type=goal_type,
            kind=ScheduledActionKind.FOLLOWUP,
            subject_type=subject_type,
            subject_id=subject_id,
            cadence=cadence,
            reason=reason or f"Follow up ({cadence.value})",
            created_by_agent_id=created_by_agent_id,
        )
