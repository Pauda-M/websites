"""Run domain — the execution record of a single Program Manager lifecycle pass.

A :class:`PMRun` captures one turn of the cognitive lifecycle: what triggered it,
the goal it determined, the plan it built, the states it visited, the tasks it
executed, and how it ended. :class:`PMTask` is a unit of plan execution within a
run — distinct from a CRM ``CrmTask`` (a to-do). Runs and tasks are the audit
trail: every autonomous decision is reconstructable from them plus the event log.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.agents.program_manager.domain.common import (
    PMAuthorityLevel,
    PMGoalType,
    PMState,
    new_id,
    utcnow,
)


class PMTriggerType(enum.StrEnum):
    """What caused a run to start."""

    INBOUND_MESSAGE = "inbound_message"
    SCHEDULED_ACTION = "scheduled_action"
    MANUAL = "manual"
    SYSTEM = "system"


class PMTaskStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_APPROVAL = "awaiting_approval"


class PMTask(BaseModel):
    """A unit of plan-step execution within a run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    step_key: str
    goal_type: PMGoalType
    objective: str
    status: PMTaskStatus = PMTaskStatus.PENDING
    authority_required: PMAuthorityLevel = PMAuthorityLevel.ACT_WITH_APPROVAL
    requires_approval: bool = False
    approved_by: str | None = None
    result: str = ""
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PMRun(BaseModel):
    """One pass of the Program Manager's cognitive lifecycle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    trigger: PMTriggerType = PMTriggerType.MANUAL
    trigger_ref: uuid.UUID | None = None  # e.g. the ScheduledAction id
    input_summary: str = ""
    state: PMState = PMState.IDLE
    goal_type: PMGoalType | None = None
    goal_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    states_visited: list[str] = Field(default_factory=list)
    outcome: str = ""
    success: bool | None = None
    awaiting_approval: bool = False
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
