"""Scheduling domain — the Program Manager's single deferred-work primitive.

Every future action the Program Manager owns — a follow-up, a reminder, a
recurring review, a deferred task — is one :class:`ScheduledAction`. The
FollowUpEngine is a thin façade over this primitive (it creates
``kind=FOLLOWUP`` actions with a cadence); there is deliberately no second
"follow-up" table, so scheduled work has exactly one home.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.agents.program_manager.domain.common import (
    FollowUpCadence,
    PMGoalType,
    new_id,
    utcnow,
)


class ScheduledActionKind(enum.StrEnum):
    FOLLOWUP = "followup"
    TASK = "task"
    REMINDER = "reminder"
    REVIEW = "review"


class ScheduledActionStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SubjectType(enum.StrEnum):
    """The CRM entity a scheduled action concerns."""

    ORGANIZATION = "organization"
    CONTACT = "contact"
    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    PROJECT = "project"
    MEETING = "meeting"
    PROPOSAL = "proposal"


class ScheduledAction(BaseModel):
    """A unit of deferred work due at ``run_at``.

    When due, the scheduler realises the action's ``goal_type`` against its
    subject — e.g. a ``FOLLOWUP`` whose ``goal_type`` is ``FOLLOW_UP_LEAD``
    starts a Program Manager run to follow up the referenced lead.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    kind: ScheduledActionKind = ScheduledActionKind.FOLLOWUP
    goal_type: PMGoalType = PMGoalType.FOLLOW_UP_LEAD
    run_at: datetime
    status: ScheduledActionStatus = ScheduledActionStatus.PENDING
    subject_type: SubjectType | None = None
    subject_id: uuid.UUID | None = None
    cadence: FollowUpCadence | None = None
    reason: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    attempts: int = Field(default=0, ge=0)
    executed_at: datetime | None = None
    last_error: str | None = None
    created_by_agent_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
