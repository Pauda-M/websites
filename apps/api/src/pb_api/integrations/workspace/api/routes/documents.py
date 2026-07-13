"""Document routes: list sites and drive items, ingest a drive into the index."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.api.schemas import IngestRequest
from pb_api.integrations.workspace.domain.files import DriveItem, SharePointSite

router = APIRouter(prefix="/documents", tags=["workspace"])


@router.get("/sites")
async def list_sites(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
) -> list[SharePointSite]:
    return await ctx.documents.list_sites(tenant_id, connection_id)


@router.get("")
async def list_items(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
    drive_id: Annotated[str, Query()],
) -> list[DriveItem]:
    return await ctx.documents.list_items(tenant_id, connection_id, drive_id=drive_id)


@router.post("/ingest")
async def ingest_drive(body: IngestRequest, ctx: WsDep) -> dict[str, object]:
    ingested = await ctx.documents.ingest_drive(
        body.tenant_id, body.connection_id, drive_id=body.drive_id
    )
    return {"ingested": ingested}
