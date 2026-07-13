"""Memory ranking contracts.

The ``MemoryRanker`` interface (Phase 7 spec) takes retrieval context and returns
ordered memories with a score and a human-readable reason. No ML here — the
default implementation is deterministic and heuristic; a future model replaces it
behind the same interface.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, Field

from pb_api.cognitive.domain.memory import MemoryItem


class RankingContext(BaseModel):
    """Retrieval context the ranker scores against (Phase 7 inputs)."""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    query: str | None = None
    query_embedding: list[float] | None = None


class RankedMemory(BaseModel):
    """A memory with its ranking score and an explanation."""

    memory: MemoryItem
    score: float
    reason: str


class RankingResult(BaseModel):
    """Ordered memories plus the ranker identity that produced them."""

    ranker: str
    ranked: list[RankedMemory] = Field(default_factory=list)


class MemoryRanker(Protocol):
    """Interface a memory ranker must satisfy. Implementations are swappable."""

    name: str

    def rank(self, memories: list[MemoryItem], context: RankingContext) -> RankingResult: ...
