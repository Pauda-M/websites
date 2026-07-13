"""Semantic memory service: persistent knowledge with versioning + provenance.

Knowledge updates supersede prior versions (immutable history) rather than
mutating in place, matching Genesis knowledge-evolution semantics.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.cognitive.domain.common import hash_embedding
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.semantic import KnowledgeKind, Relationship, SemanticItem
from pb_api.cognitive.repositories.semantic import SemanticRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class SemanticMemoryService:
    def __init__(self, repository: SemanticRepository, events: EventProcessor) -> None:
        self._repo = repository
        self._events = events

    async def add_knowledge(
        self,
        *,
        tenant_id: uuid.UUID,
        kind: KnowledgeKind,
        name: str,
        content: str,
        confidence: float = 0.5,
        source: str | None = None,
        embedding: list[float] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SemanticItem:
        item = SemanticItem(
            tenant_id=tenant_id,
            kind=kind,
            name=name,
            content=content,
            confidence=confidence,
            source=source,
            embedding=embedding if embedding is not None else hash_embedding(f"{name} {content}"),
            metadata=metadata or {},
        )
        stored = await self._repo.add_item(item)
        await self._events.record(
            event_type=EventType.KNOWLEDGE_ITEM_CREATED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"kind": kind.value, "name": name},
        )
        return stored

    async def update_knowledge(
        self,
        *,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        content: str,
        confidence: float | None = None,
        source: str | None = None,
    ) -> SemanticItem | None:
        """Supersede an existing item with a new version (history preserved)."""
        current = await self._repo.get_item(tenant_id, item_id)
        if current is None:
            return None
        replacement = SemanticItem(
            tenant_id=tenant_id,
            kind=current.kind,
            name=current.name,
            content=content,
            confidence=confidence if confidence is not None else current.confidence,
            source=source if source is not None else current.source,
            embedding=current.embedding,
            metadata=current.metadata,
        )
        new_item = await self._repo.supersede(tenant_id, item_id, replacement)
        if new_item is not None:
            await self._events.record(
                event_type=EventType.KNOWLEDGE_ITEM_SUPERSEDED,
                tenant_id=tenant_id,
                aggregate_id=item_id,
                payload={"superseded_by": str(new_item.id), "version": new_item.version},
            )
        return new_item

    async def relate(
        self,
        *,
        tenant_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        confidence: float = 0.5,
        source: str | None = None,
    ) -> Relationship:
        rel = Relationship(
            tenant_id=tenant_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            confidence=confidence,
            source=source,
        )
        stored = await self._repo.add_relationship(rel)
        await self._events.record(
            event_type=EventType.KNOWLEDGE_RELATIONSHIP_ASSERTED,
            tenant_id=tenant_id,
            aggregate_id=stored.id,
            payload={"relation": relation, "source": str(source_id), "target": str(target_id)},
        )
        return stored

    async def get(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> SemanticItem | None:
        return await self._repo.get_item(tenant_id, item_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        kind: KnowledgeKind | None = None,
        include_superseded: bool = False,
        limit: int = 100,
    ) -> builtins.list[SemanticItem]:
        return await self._repo.list_items(
            tenant_id, kind=kind, include_superseded=include_superseded, limit=limit
        )

    async def neighbors(
        self, tenant_id: uuid.UUID, entity_id: uuid.UUID
    ) -> builtins.list[Relationship]:
        return await self._repo.neighbors(tenant_id, entity_id)
