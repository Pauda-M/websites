"""Planning routes: decompose objectives into plans (a DAG of tasks)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import PlanCreateRequest, PlanStatusRequest
from pb_api.cognitive.domain.planning import Plan, PlanStatus

router = APIRouter(prefix="/plans", tags=["cognitive-planning"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_plan(body: PlanCreateRequest, core: CoreDep) -> Plan:
    return await core.planning.create_plan(
        tenant_id=body.tenant_id,
        objective=body.objective,
        tasks=body.tasks,
        goal_id=body.goal_id,
        agent_id=body.agent_id,
    )


@router.get("")
async def list_plans(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    goal_id: Annotated[uuid.UUID | None, Query()] = None,
    agent_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[PlanStatus | None, Query(alias="status")] = None,
) -> list[Plan]:
    return await core.planning.list(
        tenant_id, goal_id=goal_id, agent_id=agent_id, status=status_filter
    )


@router.get("/{plan_id}")
async def get_plan(
    plan_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Plan:
    plan = await core.planning.get(tenant_id, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="plan not found")
    return plan


@router.post("/{plan_id}/status")
async def set_plan_status(plan_id: uuid.UUID, body: PlanStatusRequest, core: CoreDep) -> Plan:
    plan = await core.planning.set_status(body.tenant_id, plan_id, body.status)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="plan not found")
    return plan
