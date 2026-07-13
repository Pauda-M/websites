"""Procedural memory routes: reusable workflow definitions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import ProcedureRegisterRequest, ProcedureSeedRequest
from pb_api.cognitive.domain.procedural import Procedure

router = APIRouter(prefix="/procedures", tags=["cognitive-procedures"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_procedure(body: ProcedureRegisterRequest, core: CoreDep) -> Procedure:
    return await core.procedural.register(
        tenant_id=body.tenant_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        steps=body.steps,
        metadata=body.metadata,
    )


@router.get("")
async def list_procedures(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Procedure]:
    return await core.procedural.list(tenant_id, limit=limit)


@router.post("/seed-defaults", status_code=status.HTTP_201_CREATED)
async def seed_defaults(body: ProcedureSeedRequest, core: CoreDep) -> list[Procedure]:
    return await core.procedural.seed_defaults(body.tenant_id)


@router.get("/{slug}")
async def get_procedure(
    slug: str,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Procedure:
    procedure = await core.procedural.get_by_slug(tenant_id, slug)
    if procedure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="procedure not found")
    return procedure
