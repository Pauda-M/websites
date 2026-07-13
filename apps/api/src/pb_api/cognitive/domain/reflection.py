"""Reflection domain model.

Every completed task produces a reflection: objective, outcome, success/failure,
lessons learned, confidence, and future recommendations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class Reflection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    objective: str
    outcome: str
    success: bool
    failure_reason: str | None = None
    lessons_learned: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    future_recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
