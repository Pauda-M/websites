"""Tasks domain — Microsoft To Do / Planner tasks, normalized across providers."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class WorkspaceTaskStatus(enum.StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"


class WorkspaceTaskPriority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class WorkspaceTask(BaseModel):
    """A task from To Do or Planner."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    source: str = "todo"  # "todo" | "planner"
    list_or_plan_id: str | None = None
    title: str
    notes: str = ""
    status: WorkspaceTaskStatus = WorkspaceTaskStatus.NOT_STARTED
    priority: WorkspaceTaskPriority = WorkspaceTaskPriority.NORMAL
    assigned_to_provider_ids: list[str] = Field(default_factory=list)
    due_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)
