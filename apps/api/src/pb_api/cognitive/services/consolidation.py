"""Memory Consolidation — background maintenance of the memory store.

Responsibilities (Phase 7 spec): merge duplicates, promote important memories,
archive stale memories, compress history, generate summaries, and maintain
embeddings. Runs idempotently so it is safe to schedule repeatedly.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.domain.common import (
    MemoryType,
    cosine_similarity,
    hash_embedding,
)
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.memory import MemoryItem
from pb_api.cognitive.repositories.memory import MemoryRepository
from pb_api.cognitive.services.event_processor import EventProcessor


class ConsolidationReport(BaseModel):
    scanned: int = 0
    embeddings_backfilled: int = 0
    duplicates_merged: int = 0
    promoted: int = 0
    archived: int = 0
    summaries_created: int = 0


class MemoryConsolidationService:
    def __init__(
        self,
        memory_repo: MemoryRepository,
        events: EventProcessor,
        settings: CognitiveSettings | None = None,
    ) -> None:
        self._memory = memory_repo
        self._events = events
        self._settings = settings or get_cognitive_settings()

    async def consolidate(self, tenant_id: uuid.UUID) -> ConsolidationReport:
        report = ConsolidationReport()
        items = await self._memory.list(tenant_id, include_archived=False, limit=1000)
        report.scanned = len(items)

        items = await self._maintain_embeddings(items, report)
        await self._merge_duplicates(tenant_id, items, report)
        # Re-read after merges so promotion/archival see current strengths.
        live = await self._memory.list(tenant_id, include_archived=False, limit=1000)
        await self._promote_important(tenant_id, live, report)
        await self._archive_stale(tenant_id, live, report)
        return report

    async def _maintain_embeddings(
        self, items: list[MemoryItem], report: ConsolidationReport
    ) -> list[MemoryItem]:
        """Backfill missing embeddings so similarity is always available."""
        refreshed: list[MemoryItem] = []
        for item in items:
            if item.embedding is None:
                item.embedding = hash_embedding(item.content)
                updated = await self._memory.update(item)
                report.embeddings_backfilled += 1
                refreshed.append(updated or item)
            else:
                refreshed.append(item)
        return refreshed

    async def _merge_duplicates(
        self, tenant_id: uuid.UUID, items: list[MemoryItem], report: ConsolidationReport
    ) -> None:
        threshold = self._settings.duplicate_similarity_threshold
        survivors: list[MemoryItem] = []
        for item in items:
            duplicate_of: MemoryItem | None = None
            for survivor in survivors:
                if item.memory_type is not survivor.memory_type:
                    continue
                if item.embedding is None or survivor.embedding is None:
                    continue
                if cosine_similarity(item.embedding, survivor.embedding) >= threshold:
                    duplicate_of = survivor
                    break
            if duplicate_of is None:
                survivors.append(item)
                continue
            # Reinforce the survivor, archive the duplicate.
            duplicate_of.importance = max(duplicate_of.importance, item.importance)
            duplicate_of.strength = min(1.0, duplicate_of.strength + 0.1)
            duplicate_of.access_count += item.access_count
            await self._memory.update(duplicate_of)
            item.archived = True
            await self._memory.update(item)
            report.duplicates_merged += 1
            await self._events.record(
                event_type=EventType.MEMORY_ITEM_DEDUPLICATED,
                tenant_id=tenant_id,
                aggregate_id=item.id,
                payload={"merged_into": str(duplicate_of.id)},
            )

    async def _promote_important(
        self, tenant_id: uuid.UUID, items: list[MemoryItem], report: ConsolidationReport
    ) -> None:
        threshold = self._settings.promotion_importance_threshold
        for item in items:
            if item.memory_type is not MemoryType.EPISODIC:
                continue
            if item.importance < threshold:
                continue
            if "promoted_to" in item.metadata:
                continue  # already promoted on a previous pass — keep idempotent
            summary = item.summary or item.content
            promoted = MemoryItem(
                tenant_id=tenant_id,
                owner_agent_id=item.owner_agent_id,
                memory_type=MemoryType.LONG_TERM,
                content=summary,
                summary=summary,
                embedding=item.embedding,
                importance=item.importance,
                confidence=item.confidence,
                strength=1.0,
                source_event_id=item.source_event_id,
                related_entity_ids=item.related_entity_ids,
                metadata={**item.metadata, "promoted_from": str(item.id)},
            )
            await self._memory.add(promoted)
            item.metadata = {**item.metadata, "promoted_to": str(promoted.id)}
            await self._memory.update(item)
            report.promoted += 1
            report.summaries_created += 1
            await self._events.record(
                event_type=EventType.MEMORY_ITEM_PROMOTED,
                tenant_id=tenant_id,
                aggregate_id=item.id,
                payload={"promoted_to": str(promoted.id)},
            )
            await self._events.record(
                event_type=EventType.MEMORY_ITEM_SUMMARIZED,
                tenant_id=tenant_id,
                aggregate_id=promoted.id,
                payload={"summary": summary[:200]},
            )

    async def _archive_stale(
        self, tenant_id: uuid.UUID, items: list[MemoryItem], report: ConsolidationReport
    ) -> None:
        threshold = self._settings.archive_strength_threshold
        for item in items:
            if item.memory_type is MemoryType.LONG_TERM:
                continue
            if item.strength > threshold:
                continue
            item.archived = True
            await self._memory.update(item)
            report.archived += 1
            await self._events.record(
                event_type=EventType.MEMORY_ITEM_ARCHIVED,
                tenant_id=tenant_id,
                aggregate_id=item.id,
                payload={"reason": "stale", "strength": item.strength},
            )
