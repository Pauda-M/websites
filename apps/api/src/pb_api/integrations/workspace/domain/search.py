"""Search domain — unified index entries and ranked search hits.

Every workspace surface (mail, meetings, documents, contacts, tasks, events) is
projected into a single :class:`IndexEntry`. A :class:`SearchHit` pairs an entry
with its similarity score for a query, produced by the search service's in-memory
cosine ranking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class IndexEntry(BaseModel):
    """A unified, searchable document projected from a workspace resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    kind: str
    source_provider_id: str
    connection_id: uuid.UUID | None = None
    title: str = ""
    snippet: str = ""
    body: str = ""
    web_url: str | None = None
    embedding: list[float] = Field(default_factory=list)
    ref: dict[str, object] = Field(default_factory=dict)
    indexed_at: datetime = Field(default_factory=utcnow)


class SearchHit(BaseModel):
    """An index entry paired with its similarity score for a query."""

    model_config = ConfigDict(from_attributes=True)

    entry: IndexEntry
    score: float = 0.0
