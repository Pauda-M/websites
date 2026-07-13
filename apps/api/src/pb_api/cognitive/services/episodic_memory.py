"""Episodic memory service: record and recall time-indexed experiences.

Recording an episode also writes a unified ``MemoryItem`` (type EPISODIC) so the
memory engine ranks and consolidates it alongside every other memory, and emits
a ``pb.memory.item.created`` event.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.common import MemoryType, hash_embedding
from pb_api.cognitive.domain.episodic import EpisodicEvent
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.memory import MemoryItem
from pb_api.cognitive.repositories.episodic import EpisodicRepository
from pb_api.cognitive.repositories.memory import MemoryRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class EpisodicMemoryService:
    def __init__(
        self,
        episodic_repo: EpisodicRepository,
        memory_repo: MemoryRepository,
        events: EventProcessor,
    ) -> None:
        self._episodic = episodic_repo
        self._memory = memory_repo
        self._events = events

    async def record(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: str,
        summary: str,
        conversation: uuid.UUID | None = None,
        customer: uuid.UUID | None = None,
        project: uuid.UUID | None = None,
        importance: float = 0.5,
        confidence: float = 0.5,
        embedding: list[float] | None = None,
        metadata: dict[str, object] | None = None,
        related_entities: list[uuid.UUID] | None = None,
    ) -> EpisodicEvent:
        resolved_embedding = embedding if embedding is not None else hash_embedding(summary)
        event = EpisodicEvent(
            organization=tenant_id,
            actor=actor,
            summary=summary,
            conversation=conversation,
            customer=customer,
            project=project,
            importance=importance,
            confidence=confidence,
            embedding=resolved_embedding,
            metadata=metadata or {},
            related_entities=related_entities or [],
        )
        stored = await self._episodic.add(event)

        related = list(stored.related_entities)
        for ref in (customer, project, conversation):
            if ref is not None and ref not in related:
                related.append(ref)
        memory = MemoryItem(
            tenant_id=tenant_id,
            memory_type=MemoryType.EPISODIC,
            content=summary,
            summary=summary,
            embedding=resolved_embedding,
            importance=importance,
            confidence=confidence,
            source_event_id=stored.id,
            related_entity_ids=related,
            metadata={"actor": actor, **(metadata or {})},
        )
        await self._memory.add(memory)
        await self._events.record(
            event_type=EventType.MEMORY_ITEM_CREATED,
            tenant_id=tenant_id,
            actor=actor,
            aggregate_id=stored.id,
            payload={"memory_type": MemoryType.EPISODIC.value, "summary": summary},
        )
        return stored

    async def get(self, tenant_id: uuid.UUID, event_id: uuid.UUID) -> EpisodicEvent | None:
        return await self._episodic.get(tenant_id, event_id)

    async def recent(self, tenant_id: uuid.UUID, limit: int = 20) -> list[EpisodicEvent]:
        return await self._episodic.recent(tenant_id, limit=limit)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        conversation: uuid.UUID | None = None,
        customer: uuid.UUID | None = None,
        project: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        return await self._episodic.list(
            tenant_id,
            conversation=conversation,
            customer=customer,
            project=project,
            limit=limit,
        )
