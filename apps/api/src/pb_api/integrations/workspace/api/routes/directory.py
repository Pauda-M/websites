"""Directory routes: list the tenant's own users and groups (provider port reads)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.domain.directory import DirectoryGroup, DirectoryUser

router = APIRouter(prefix="/directory", tags=["workspace"])


@router.get("/users")
async def list_users(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
) -> list[DirectoryUser]:
    page = await ctx.provider.directory.list_users(tenant_id, connection_id)
    return list(page.items)


@router.get("/groups")
async def list_groups(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
) -> list[DirectoryGroup]:
    page = await ctx.provider.directory.list_groups(tenant_id, connection_id)
    return list(page.items)
