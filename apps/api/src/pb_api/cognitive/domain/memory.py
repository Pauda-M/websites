"""Memory domain models.

``MemoryItem`` is the unified record owned by the Memory Engine
(`docs/genesis/008_Memory_Engine.md`). Working memory is modelled separately as
short-lived, token-aware, versioned entries that assemble into a ``WorkingSet``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import MemoryType, new_id, utcnow


class MemoryItem(BaseModel):
    """A unified memory record spanning episodic / semantic / procedural stores."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    owner_agent_id: uuid.UUID | None = None
    memory_type: MemoryType
    content: str
    summary: str | None = None
    embedding: list[float] | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    source_event_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    related_entity_ids: list[uuid.UUID] = Field(default_factory=list)
    access_count: int = 0
    archived: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    last_accessed_at: datetime = Field(default_factory=utcnow)


class WorkingMemoryEntry(BaseModel):
    """A single item held in an agent's working memory.

    Short-lived, token-aware, and versioned. ``expires_at`` drives automatic
    expiry; ``relevance`` orders entries when the budget forces truncation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    scope_key: str  # task or conversation scope this entry belongs to
    content: str
    token_estimate: int = 0
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    version: int = 1
    source: str = "unknown"  # e.g. "recall", "observation", "goal", "merge"
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None


class WorkingSet(BaseModel):
    """An assembled, token-bounded view of working memory for one scope."""

    scope_key: str
    entries: list[WorkingMemoryEntry] = Field(default_factory=list)
    total_tokens: int = 0
    token_budget: int
    truncated: bool = False
