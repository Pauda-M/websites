"""Hierarchical goals: Company → Department → Agent → Task."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class GoalLevel(enum.StrEnum):
    COMPANY = "company"
    DEPARTMENT = "department"
    AGENT = "agent"
    TASK = "task"


class GoalStatus(enum.StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


class Goal(BaseModel):
    """A goal in the hierarchy with priority, dependencies, and progress."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    level: GoalLevel
    parent_id: uuid.UUID | None = None
    owner_agent_id: uuid.UUID | None = None
    title: str
    description: str = ""
    priority: int = Field(default=3, ge=1, le=5)  # 1 = highest
    status: GoalStatus = GoalStatus.PROPOSED
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    depends_on: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class GoalHistoryEntry(BaseModel):
    """An append-only record of a change to a goal."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    goal_id: uuid.UUID
    change: str  # e.g. "status: active->achieved", "progress: 0.2->0.5"
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
