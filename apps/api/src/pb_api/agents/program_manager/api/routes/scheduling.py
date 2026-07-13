"""Scheduling routes: inspect and cancel the Program Manager's scheduled actions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.agents.program_manager.api.deps import PMDep
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledAction,
    ScheduledActionKind,
    ScheduledActionStatus,
)

router = APIRouter(prefix="/scheduled-actions", tags=["program-manager-scheduling"])


@router.get("")
async def list_scheduled_actions(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[ScheduledActionStatus | None, Query(alias="status")] = None,
    kind: Annotated[ScheduledActionKind | None, Query()] = None,
) -> list[ScheduledAction]:
    return await pm.scheduler.list(tenant_id, status=status_filter, kind=kind)


@router.post("/{action_id}/cancel")
async def cancel_scheduled_action(
    action_id: uuid.UUID, pm: PMDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> ScheduledAction:
    action = await pm.scheduler.cancel(tenant_id, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scheduled action not found")
    return action
