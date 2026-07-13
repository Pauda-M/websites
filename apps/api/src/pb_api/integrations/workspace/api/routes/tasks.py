"""Task routes: list To Do / Planner tasks (provider port read)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.domain.tasks import WorkspaceTask

router = APIRouter(prefix="/tasks", tags=["workspace"])


@router.get("")
async def list_tasks(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
    source: Annotated[str, Query()] = "todo",
) -> list[WorkspaceTask]:
    page = await ctx.provider.tasks.list_tasks(tenant_id, connection_id, source=source)
    return list(page.items)
