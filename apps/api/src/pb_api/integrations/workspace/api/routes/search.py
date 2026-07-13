"""Search route: one semantic query across every indexed workspace surface."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.domain.search import SearchHit

router = APIRouter(prefix="/search", tags=["workspace"])


@router.get("")
async def search(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    query: Annotated[str, Query()],
    kinds: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query()] = 20,
) -> list[SearchHit]:
    return await ctx.search.search(tenant_id, query=query, kinds=kinds, limit=limit)
