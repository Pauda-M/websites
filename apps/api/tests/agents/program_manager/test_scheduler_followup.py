from __future__ import annotations

import uuid
from datetime import timedelta

from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.domain.common import FollowUpCadence, utcnow
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledActionKind,
    ScheduledActionStatus,
    SubjectType,
)


async def test_followup_schedules_at_cadence_and_is_due_after_delay(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    now = utcnow()
    subject = uuid.uuid4()
    action = await pm.followups.schedule_followup(
        tenant_id=tenant,
        subject_type=SubjectType.LEAD,
        subject_id=subject,
        cadence=FollowUpCadence.FIRST_TOUCH,
        now=now,
    )
    assert action.kind is ScheduledActionKind.FOLLOWUP
    assert action.run_at == now + timedelta(hours=24)

    # Not due before the cadence elapses...
    assert await pm.scheduler.due(tenant, now=now + timedelta(hours=1)) == []
    # ...due after it.
    due = await pm.scheduler.due(tenant, now=now + timedelta(hours=25))
    assert [a.id for a in due] == [action.id]


async def test_mark_executed_and_cancel_transition_status(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    now = utcnow()
    action = await pm.followups.schedule_followup(
        tenant_id=tenant,
        subject_type=SubjectType.ORGANIZATION,
        subject_id=uuid.uuid4(),
        now=now,
    )
    executed = await pm.scheduler.mark_executed(tenant, action.id, now=now)
    assert executed is not None
    assert executed.status is ScheduledActionStatus.EXECUTED
    assert executed.attempts == 1

    other = await pm.followups.schedule_followup(
        tenant_id=tenant,
        subject_type=SubjectType.ORGANIZATION,
        subject_id=uuid.uuid4(),
        now=now,
    )
    cancelled = await pm.scheduler.cancel(tenant, other.id)
    assert cancelled is not None
    assert cancelled.status is ScheduledActionStatus.CANCELLED
    # A cancelled action is never due.
    assert other.id not in {
        a.id for a in await pm.scheduler.due(tenant, now=now + timedelta(days=365))
    }
