"""Repository for episodic memory: time-indexed experiences ("what happened")."""

from __future__ import annotations

import builtins
import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import EpisodicEventRow
from pb_api.cognitive.domain.episodic import EpisodicEvent
from pb_api.cognitive.repositories.base import (
    BaseRepository,
    json_to_uuids,
    uuids_to_json,
)


def _row_to_episodic(row: EpisodicEventRow) -> EpisodicEvent:
    return EpisodicEvent(
        id=row.id,
        timestamp=row.occurred_at,
        actor=row.actor,
        organization=row.tenant_id,
        conversation=row.conversation,
        customer=row.customer,
        project=row.project,
        importance=row.importance,
        confidence=row.confidence,
        summary=row.summary,
        embedding=list(row.embedding) if row.embedding is not None else None,
        metadata=dict(row.meta),
        related_entities=json_to_uuids(row.related_entities),
    )


class EpisodicRepository(BaseRepository):
    async def add(self, event: EpisodicEvent) -> EpisodicEvent:
        row = EpisodicEventRow(
            id=event.id,
            tenant_id=event.organization,
            occurred_at=event.timestamp,
            actor=event.actor,
            conversation=event.conversation,
            customer=event.customer,
            project=event.project,
            importance=event.importance,
            confidence=event.confidence,
            summary=event.summary,
            embedding=event.embedding,
            meta=event.metadata,
            related_entities=uuids_to_json(event.related_entities),
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_episodic(row)

    async def get(self, tenant_id: uuid.UUID, event_id: uuid.UUID) -> EpisodicEvent | None:
        row = await self.session.get(EpisodicEventRow, event_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_episodic(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        conversation: uuid.UUID | None = None,
        customer: uuid.UUID | None = None,
        project: uuid.UUID | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        stmt = select(EpisodicEventRow).where(EpisodicEventRow.tenant_id == tenant_id)
        if conversation is not None:
            stmt = stmt.where(EpisodicEventRow.conversation == conversation)
        if customer is not None:
            stmt = stmt.where(EpisodicEventRow.customer == customer)
        if project is not None:
            stmt = stmt.where(EpisodicEventRow.project == project)
        if actor is not None:
            stmt = stmt.where(EpisodicEventRow.actor == actor)
        stmt = stmt.order_by(EpisodicEventRow.occurred_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_episodic(row) for row in rows]

    async def recent(self, tenant_id: uuid.UUID, limit: int = 20) -> builtins.list[EpisodicEvent]:
        # ``builtins.list`` because the ``list`` method above shadows the builtin
        # for annotation resolution within this class.
        return await self.list(tenant_id, limit=limit)
