"""Planning engine domain models: a plan is a DAG of tasks toward a goal."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class PlanStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PlanTask(BaseModel):
    """A single task within a plan."""

    key: str
    title: str
    description: str = ""
    capability: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)


class Plan(BaseModel):
    """A decomposition of a goal into an ordered/parallel set of tasks."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    goal_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    objective: str
    tasks: list[PlanTask] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
