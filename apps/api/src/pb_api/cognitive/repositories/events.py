"""Repository for the append-only cognitive event store."""

from __future__ import annotations

import builtins
import uuid

from sqlalchemy import select

from pb_api.cognitive.db.models import EventRow
from pb_api.cognitive.domain.events import CognitiveEvent
from pb_api.cognitive.repositories.base import BaseRepository


def _row_to_event(row: EventRow) -> CognitiveEvent:
    return CognitiveEvent(
        id=row.id,
        type=row.type,
        tenant_id=row.tenant_id,
        occurred_at=row.occurred_at,
        actor=row.actor,
        aggregate_id=row.aggregate_id,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        schema_version=row.schema_version,
        payload=dict(row.payload),
    )


class EventRepository(BaseRepository):
    async def append(self, event: CognitiveEvent) -> CognitiveEvent:
        row = EventRow(
            id=event.id,
            tenant_id=event.tenant_id,
            type=event.type,
            occurred_at=event.occurred_at,
            actor=event.actor,
            aggregate_id=event.aggregate_id,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            schema_version=event.schema_version,
            payload=event.payload,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_event(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        type: str | None = None,
        aggregate_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[CognitiveEvent]:
        stmt = select(EventRow).where(EventRow.tenant_id == tenant_id)
        if type is not None:
            stmt = stmt.where(EventRow.type == type)
        if aggregate_id is not None:
            stmt = stmt.where(EventRow.aggregate_id == aggregate_id)
        if correlation_id is not None:
            stmt = stmt.where(EventRow.correlation_id == correlation_id)
        stmt = stmt.order_by(EventRow.occurred_at.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_event(row) for row in rows]

    async def by_correlation(
        self, tenant_id: uuid.UUID, correlation_id: uuid.UUID
    ) -> builtins.list[CognitiveEvent]:
        # ``builtins.list`` because the ``list`` method above shadows the builtin
        # for annotation resolution within this class.
        return await self.list(tenant_id, correlation_id=correlation_id)
