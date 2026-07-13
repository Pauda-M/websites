"""Semantic memory routes: knowledge items and typed relationships."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import (
    RelateRequest,
    SemanticAddRequest,
    SemanticUpdateRequest,
)
from pb_api.cognitive.domain.semantic import KnowledgeKind, Relationship, SemanticItem

router = APIRouter(prefix="/semantic", tags=["cognitive-semantic"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_knowledge(body: SemanticAddRequest, core: CoreDep) -> SemanticItem:
    return await core.semantic.add_knowledge(
        tenant_id=body.tenant_id,
        kind=body.kind,
        name=body.name,
        content=body.content,
        confidence=body.confidence,
        source=body.source,
        embedding=body.embedding,
        metadata=body.metadata,
    )


@router.get("")
async def list_knowledge(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    kind: Annotated[KnowledgeKind | None, Query()] = None,
    include_superseded: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SemanticItem]:
    return await core.semantic.list(
        tenant_id,
        kind=kind,
        include_superseded=include_superseded,
        limit=limit,
    )


@router.post("/relate", status_code=status.HTTP_201_CREATED)
async def relate(body: RelateRequest, core: CoreDep) -> Relationship:
    return await core.semantic.relate(
        tenant_id=body.tenant_id,
        source_id=body.source_id,
        target_id=body.target_id,
        relation=body.relation,
        confidence=body.confidence,
        source=body.source,
    )


@router.get("/{item_id}")
async def get_knowledge(
    item_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> SemanticItem:
    item = await core.semantic.get(tenant_id, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="knowledge item not found")
    return item


@router.put("/{item_id}")
async def update_knowledge(
    item_id: uuid.UUID, body: SemanticUpdateRequest, core: CoreDep
) -> SemanticItem:
    updated = await core.semantic.update_knowledge(
        tenant_id=body.tenant_id,
        item_id=item_id,
        content=body.content,
        confidence=body.confidence,
        source=body.source,
    )
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="knowledge item not found")
    return updated


@router.get("/{entity_id}/neighbors")
async def neighbors(
    entity_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[Relationship]:
    return await core.semantic.neighbors(tenant_id, entity_id)
