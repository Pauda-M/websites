"""Connection routes: register a workspace connection, list them, health snapshot."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.api.schemas import ConnectRequest
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection

router = APIRouter(prefix="/connections", tags=["workspace"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_connection(body: ConnectRequest, ctx: WsDep) -> WorkspaceConnection:
    return await ctx.bootstrap_connection(
        body.tenant_id,
        display_name=body.display_name,
        mailbox=body.mailbox,
        provider_tenant_id=body.provider_tenant_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        refresh_token=body.refresh_token,
        scopes=body.scopes,
    )


@router.get("")
async def list_connections(
    ctx: WsDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> list[WorkspaceConnection]:
    return await ctx.list_connections(tenant_id)


@router.get("/health")
async def connection_health(
    ctx: WsDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> dict[str, object]:
    return await ctx.health(tenant_id)
