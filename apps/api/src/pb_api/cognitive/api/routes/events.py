"""Event store routes: read the append-only cognitive event history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.domain.events import CognitiveEvent

router = APIRouter(prefix="/events", tags=["cognitive-events"])


@router.get("")
async def list_events(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    event_type: Annotated[str | None, Query()] = None,
    aggregate_id: Annotated[uuid.UUID | None, Query()] = None,
    correlation_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[CognitiveEvent]:
    return await core.events.history(
        tenant_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        limit=limit,
    )
