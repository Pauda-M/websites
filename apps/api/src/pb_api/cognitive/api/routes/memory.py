"""Memory routes: working memory, episodic memory, and consolidation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import (
    ConsolidateRequest,
    EpisodicRecordRequest,
    WorkingMergeRequest,
    WorkingRememberRequest,
)
from pb_api.cognitive.domain.episodic import EpisodicEvent
from pb_api.cognitive.domain.memory import WorkingMemoryEntry, WorkingSet
from pb_api.cognitive.services.consolidation import ConsolidationReport

router = APIRouter(prefix="/memory", tags=["cognitive-memory"])


# --- Working memory -----------------------------------------------------


@router.post("/working", status_code=status.HTTP_201_CREATED)
async def remember(body: WorkingRememberRequest, core: CoreDep) -> WorkingMemoryEntry:
    return await core.working_memory.remember(
        body.tenant_id,
        body.scope_key,
        body.content,
        relevance=body.relevance,
        source=body.source,
        ttl_seconds=body.ttl_seconds,
    )


@router.get("/working/{scope_key}")
async def build_working_set(
    scope_key: str,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    token_budget: Annotated[int | None, Query(ge=1)] = None,
) -> WorkingSet:
    return await core.working_memory.build_set(tenant_id, scope_key, token_budget=token_budget)


@router.post("/working/{scope_key}/merge")
async def merge_working_scopes(
    scope_key: str, body: WorkingMergeRequest, core: CoreDep
) -> dict[str, int]:
    merged = await core.working_memory.merge_scopes(body.tenant_id, body.source_scopes, scope_key)
    return {"merged": merged}


@router.delete("/working/{scope_key}")
async def clear_working_scope(
    scope_key: str,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> dict[str, int]:
    cleared = await core.working_memory.clear(tenant_id, scope_key)
    return {"cleared": cleared}


# --- Episodic memory ----------------------------------------------------


@router.post("/episodic", status_code=status.HTTP_201_CREATED)
async def record_episode(body: EpisodicRecordRequest, core: CoreDep) -> EpisodicEvent:
    return await core.episodic.record(
        tenant_id=body.tenant_id,
        actor=body.actor,
        summary=body.summary,
        conversation=body.conversation,
        customer=body.customer,
        project=body.project,
        importance=body.importance,
        confidence=body.confidence,
        embedding=body.embedding,
        metadata=body.metadata,
        related_entities=body.related_entities,
    )


@router.get("/episodic")
async def list_episodes(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    conversation: Annotated[uuid.UUID | None, Query()] = None,
    customer: Annotated[uuid.UUID | None, Query()] = None,
    project: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EpisodicEvent]:
    return await core.episodic.list(
        tenant_id,
        conversation=conversation,
        customer=customer,
        project=project,
        limit=limit,
    )


@router.get("/episodic/recent")
async def recent_episodes(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
) -> list[EpisodicEvent]:
    return await core.episodic.recent(tenant_id, limit=limit)


# --- Consolidation ------------------------------------------------------


@router.post("/consolidate")
async def consolidate(body: ConsolidateRequest, core: CoreDep) -> ConsolidationReport:
    return await core.consolidation.consolidate(body.tenant_id)
