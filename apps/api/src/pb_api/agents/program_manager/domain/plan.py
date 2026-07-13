"""Planning domain — the Program Manager's structured, authority-aware plan.

The Program Manager specialises the Cognitive Core's generic plan: every
:class:`PMPlanStep` additionally declares its **objective**, **dependencies**,
**required tools**, **risk**, **expected outcome**, **fallback**, and the
**authority** it needs — the fields the Program Manager reasons over to decide
what it may execute autonomously. The generic ``cognitive.Plan`` does not model
these, so this is a specialisation, not a duplication (see ADR-0011).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.agents.program_manager.domain.common import (
    PMAuthorityLevel,
    PMGoalType,
    RiskLevel,
    new_id,
    utcnow,
)


class PMPlanStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PMPlanStep(BaseModel):
    """A single, authority-aware step in a Program Manager plan."""

    key: str
    objective: str
    goal_type: PMGoalType
    depends_on: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW
    expected_outcome: str = ""
    fallback: str = ""
    authority_required: PMAuthorityLevel = PMAuthorityLevel.ACT_WITH_APPROVAL
    action: str = ""  # canonical policy action string, e.g. "crm.update"
    resource: str = "*"


class PMPlan(BaseModel):
    """An ordered, dependency-aware decomposition of a goal into steps."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    run_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    goal_type: PMGoalType
    objective: str
    steps: list[PMPlanStep] = Field(default_factory=list)
    status: PMPlanStatus = PMPlanStatus.DRAFT
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
