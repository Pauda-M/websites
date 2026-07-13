"""Goal routes: hierarchical goals with status, progress, and history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import (
    GoalCreateRequest,
    GoalProgressRequest,
    GoalStatusRequest,
)
from pb_api.cognitive.domain.goals import Goal, GoalHistoryEntry, GoalLevel, GoalStatus

router = APIRouter(prefix="/goals", tags=["cognitive-goals"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalCreateRequest, core: CoreDep) -> Goal:
    try:
        return await core.goals.create_goal(
            tenant_id=body.tenant_id,
            level=body.level,
            title=body.title,
            description=body.description,
            parent_id=body.parent_id,
            owner_agent_id=body.owner_agent_id,
            priority=body.priority,
            depends_on=body.depends_on,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("")
async def list_goals(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    level: Annotated[GoalLevel | None, Query()] = None,
    status_filter: Annotated[GoalStatus | None, Query(alias="status")] = None,
    owner_agent_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[Goal]:
    return await core.goals.list(
        tenant_id,
        level=level,
        status=status_filter,
        owner_agent_id=owner_agent_id,
    )


@router.get("/{goal_id}")
async def get_goal(
    goal_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Goal:
    goal = await core.goals.get(tenant_id, goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="goal not found")
    return goal


@router.get("/{goal_id}/children")
async def goal_children(
    goal_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[Goal]:
    return await core.goals.children(tenant_id, goal_id)


@router.get("/{goal_id}/history")
async def goal_history(
    goal_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[GoalHistoryEntry]:
    return await core.goals.history(tenant_id, goal_id)


@router.post("/{goal_id}/status")
async def set_goal_status(goal_id: uuid.UUID, body: GoalStatusRequest, core: CoreDep) -> Goal:
    try:
        goal = await core.goals.set_status(body.tenant_id, goal_id, body.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="goal not found")
    return goal


@router.post("/{goal_id}/progress")
async def set_goal_progress(goal_id: uuid.UUID, body: GoalProgressRequest, core: CoreDep) -> Goal:
    goal = await core.goals.set_progress(body.tenant_id, goal_id, body.progress)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="goal not found")
    return goal
