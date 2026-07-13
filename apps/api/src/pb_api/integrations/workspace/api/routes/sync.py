"""Synchronization routes: run a full connection sync, inspect recent sync jobs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep, WsMetricsDep
from pb_api.integrations.workspace.api.schemas import SyncRequest
from pb_api.integrations.workspace.domain.sync import SyncJob

router = APIRouter(prefix="/sync", tags=["workspace"])


@router.post("/run")
async def run_sync(body: SyncRequest, ctx: WsDep, metrics: WsMetricsDep) -> dict[str, object]:
    jobs = await ctx.sync.sync_all(body.tenant_id, body.connection_id)
    for job in jobs:
        metrics.sync_runs_total.labels(resource=job.resource.value, outcome=job.status.value).inc()
        metrics.sync_items_total.labels(resource=job.resource.value).inc(job.items_processed)
    return {"jobs": jobs}


@router.get("/status")
async def sync_status(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[SyncJob]:
    return await ctx.sync.last_jobs(tenant_id, connection_id=connection_id)
