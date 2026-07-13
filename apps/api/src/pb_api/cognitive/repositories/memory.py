"""Repositories for unified memory items and working-memory entries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select

from pb_api.cognitive.db.models import MemoryItemRow, WorkingEntryRow
from pb_api.cognitive.domain.common import MemoryType, ensure_aware, utcnow
from pb_api.cognitive.domain.memory import MemoryItem, WorkingMemoryEntry
from pb_api.cognitive.repositories.base import (
    BaseRepository,
    json_to_uuids,
    uuids_to_json,
)


def _row_to_memory(row: MemoryItemRow) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_agent_id=row.owner_agent_id,
        memory_type=MemoryType(row.memory_type),
        content=row.content,
        summary=row.summary,
        embedding=list(row.embedding) if row.embedding is not None else None,
        importance=row.importance,
        confidence=row.confidence,
        strength=row.strength,
        source_event_id=row.source_event_id,
        metadata=dict(row.meta),
        related_entity_ids=json_to_uuids(row.related_entity_ids),
        access_count=row.access_count,
        archived=row.archived,
        created_at=row.created_at,
        last_accessed_at=row.last_accessed_at,
    )


class MemoryRepository(BaseRepository):
    async def add(self, item: MemoryItem) -> MemoryItem:
        row = MemoryItemRow(
            id=item.id,
            tenant_id=item.tenant_id,
            owner_agent_id=item.owner_agent_id,
            memory_type=item.memory_type.value,
            content=item.content,
            summary=item.summary,
            embedding=item.embedding,
            importance=item.importance,
            confidence=item.confidence,
            strength=item.strength,
            source_event_id=item.source_event_id,
            meta=item.metadata,
            related_entity_ids=uuids_to_json(item.related_entity_ids),
            access_count=item.access_count,
            archived=item.archived,
            last_accessed_at=item.last_accessed_at,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_memory(row)

    async def get(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> MemoryItem | None:
        row = await self.session.get(MemoryItemRow, item_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_memory(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        memory_type: MemoryType | None = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[MemoryItem]:
        stmt = select(MemoryItemRow).where(MemoryItemRow.tenant_id == tenant_id)
        if memory_type is not None:
            stmt = stmt.where(MemoryItemRow.memory_type == memory_type.value)
        if not include_archived:
            stmt = stmt.where(MemoryItemRow.archived.is_(False))
        stmt = stmt.order_by(MemoryItemRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_memory(row) for row in rows]

    async def touch(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> MemoryItem | None:
        """Record a recall: bump access count, strength, and last-accessed."""
        row = await self.session.get(MemoryItemRow, item_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        row.access_count += 1
        row.strength = min(1.0, row.strength + 0.05)
        row.last_accessed_at = utcnow()
        await self.session.flush()
        return _row_to_memory(row)

    async def update(self, item: MemoryItem) -> MemoryItem | None:
        row = await self.session.get(MemoryItemRow, item.id)
        if row is None or row.tenant_id != item.tenant_id:
            return None
        row.summary = item.summary
        row.importance = item.importance
        row.confidence = item.confidence
        row.strength = item.strength
        row.archived = item.archived
        row.embedding = list(item.embedding) if item.embedding is not None else None
        row.meta = item.metadata
        row.related_entity_ids = list(uuids_to_json(item.related_entity_ids))
        await self.session.flush()
        return _row_to_memory(row)

    async def delete(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        row = await self.session.get(MemoryItemRow, item_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


def _row_to_working(row: WorkingEntryRow) -> WorkingMemoryEntry:
    return WorkingMemoryEntry(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_key=row.scope_key,
        content=row.content,
        token_estimate=row.token_estimate,
        relevance=row.relevance,
        version=row.version,
        source=row.source,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


class WorkingMemoryRepository(BaseRepository):
    async def add(self, entry: WorkingMemoryEntry) -> WorkingMemoryEntry:
        row = WorkingEntryRow(
            id=entry.id,
            tenant_id=entry.tenant_id,
            scope_key=entry.scope_key,
            content=entry.content,
            token_estimate=entry.token_estimate,
            relevance=entry.relevance,
            version=entry.version,
            source=entry.source,
            expires_at=entry.expires_at,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_working(row)

    async def list_active(
        self, tenant_id: uuid.UUID, scope_key: str, *, now: datetime | None = None
    ) -> list[WorkingMemoryEntry]:
        current = now or utcnow()
        stmt = (
            select(WorkingEntryRow)
            .where(
                WorkingEntryRow.tenant_id == tenant_id,
                WorkingEntryRow.scope_key == scope_key,
            )
            .order_by(WorkingEntryRow.relevance.desc(), WorkingEntryRow.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            _row_to_working(row)
            for row in rows
            if row.expires_at is None or ensure_aware(row.expires_at) > current
        ]

    async def max_version(self, tenant_id: uuid.UUID, scope_key: str) -> int:
        rows = await self.list_active(tenant_id, scope_key)
        return max((entry.version for entry in rows), default=0)

    async def purge_expired(self, tenant_id: uuid.UUID, *, now: datetime | None = None) -> int:
        current = now or utcnow()
        stmt = (
            delete(WorkingEntryRow)
            .where(WorkingEntryRow.tenant_id == tenant_id)
            .where(WorkingEntryRow.expires_at.is_not(None))
            .where(WorkingEntryRow.expires_at <= current)
        )
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        await self.session.flush()
        return result.rowcount or 0

    async def clear_scope(self, tenant_id: uuid.UUID, scope_key: str) -> int:
        stmt = (
            delete(WorkingEntryRow)
            .where(WorkingEntryRow.tenant_id == tenant_id)
            .where(WorkingEntryRow.scope_key == scope_key)
        )
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        await self.session.flush()
        return result.rowcount or 0
