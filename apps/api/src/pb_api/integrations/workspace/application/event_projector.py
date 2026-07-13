"""Workspace event projector.

The one path by which "everything becomes an event, and every event updates
memory" (manifesto: First Principles). Services call :meth:`project` for each
consequential workspace activity; it appends an immutable event through the
Cognitive Core's Event Processor and, when the activity is worth remembering,
writes an episodic memory. There is exactly one write path — no service records
events or memory on its own.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.services.episodic_memory import EpisodicMemoryService
from pb_api.cognitive.services.event_processor import EventProcessor


class WorkspaceEventProjector:
    def __init__(self, events: EventProcessor, episodic: EpisodicMemoryService) -> None:
        self._events = events
        self._episodic = episodic

    async def project(
        self,
        tenant_id: uuid.UUID,
        *,
        event_type: str,
        summary: str,
        aggregate_id: uuid.UUID | None = None,
        actor: str = "workspace",
        payload: dict[str, object] | None = None,
        memorize: bool = True,
        importance: float = 0.5,
        customer: uuid.UUID | None = None,
    ) -> None:
        await self._events.record(
            event_type=event_type,
            tenant_id=tenant_id,
            actor=actor,
            aggregate_id=aggregate_id,
            payload=payload or {},
        )
        if memorize:
            await self._episodic.record(
                tenant_id=tenant_id,
                actor=actor,
                summary=summary,
                importance=importance,
                customer=customer,
            )
