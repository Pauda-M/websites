"""Episodic memory: time-indexed experiences ("what happened")."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class EpisodicEvent(BaseModel):
    """A recorded experience. Fields mirror the Phase 7 specification exactly.

    ``organization`` is the tenant; ``actor`` is who/what caused it;
    ``conversation`` / ``customer`` / ``project`` are cross-context references by
    ID (never foreign keys — Genesis integrates contexts by ID).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    timestamp: datetime = Field(default_factory=utcnow)
    actor: str
    organization: uuid.UUID  # tenant_id
    conversation: uuid.UUID | None = None
    customer: uuid.UUID | None = None
    project: uuid.UUID | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    related_entities: list[uuid.UUID] = Field(default_factory=list)
