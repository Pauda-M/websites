"""Event Processor.

Everything of consequence becomes an immutable event (Phase 7 spec). This is the
single write path for cognitive domain events; it appends to the append-only
event store and returns the recorded event. A future adapter also publishes to
the platform ``EventBus`` (`docs/genesis/005_Event_Model.md`) — the interface
here does not change when that lands.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.events import CognitiveEvent
from pb_api.cognitive.repositories.events import EventRepository


class EventProcessor:
    def __init__(self, repository: EventRepository) -> None:
        self._repo = repository

    async def record(
        self,
        *,
        event_type: str,
        tenant_id: uuid.UUID,
        actor: str = "system",
        aggregate_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
        payload: dict[str, object] | None = None,
    ) -> CognitiveEvent:
        event = CognitiveEvent(
            type=event_type,
            tenant_id=tenant_id,
            actor=actor,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload or {},
        )
        return await self._repo.append(event)

    async def history(
        self,
        tenant_id: uuid.UUID,
        *,
        event_type: str | None = None,
        aggregate_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[CognitiveEvent]:
        return await self._repo.list(
            tenant_id,
            type=event_type,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            limit=limit,
        )
