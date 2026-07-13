"""Semantic memory: persistent knowledge ("what is true").

Concepts and facts with confidence, source tracking, and version history.
Knowledge updates supersede prior versions rather than mutating in place.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class KnowledgeKind(enum.StrEnum):
    CONCEPT = "concept"
    FACT = "fact"


class SemanticItem(BaseModel):
    """A concept or fact in semantic memory, versioned and provenance-tracked."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    kind: KnowledgeKind
    name: str
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str | None = None  # provenance: event id, document, agent, human
    version: int = 1
    superseded_by: uuid.UUID | None = None
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Relationship(BaseModel):
    """A typed, directed relationship between two semantic entities."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str  # e.g. "works_at", "owns", "relates_to", "derived_from"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
