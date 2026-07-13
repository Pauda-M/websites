"""Lifecycle routes: bootstrap, trigger runs, inspect runs/tasks, approvals.

These endpoints are the control surface of the AI Employee — they start a
governed cognitive run, expose its execution record and per-step tasks, let a
human approve a paused action, and drive the due scheduled actions.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.agents.program_manager.api.deps import PMDep, PMMetricsDep
from pb_api.agents.program_manager.api.schemas import (
    ApproveRequest,
    BootstrapResponse,
    ExecuteDueResponse,
    RunRequest,
    TenantBody,
)
from pb_api.agents.program_manager.domain.common import PMState
from pb_api.agents.program_manager.domain.run import PMRun, PMTask, PMTaskStatus

router = APIRouter(tags=["program-manager"])


def _run_outcome(run: PMRun) -> str:
    if run.state is PMState.ERROR:
        return "error"
    if run.awaiting_approval:
        return "awaiting_approval"
    return "success" if run.success else "failed"


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap(body: TenantBody, pm: PMDep) -> BootstrapResponse:
    agent_id = await pm.bootstrap(body.tenant_id)
    return BootstrapResponse(tenant_id=body.tenant_id, agent_id=agent_id)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def trigger_run(body: RunRequest, pm: PMDep, metrics: PMMetricsDep) -> PMRun:
    started = time.perf_counter()
    run = await pm.run_cycle(
        tenant_id=body.tenant_id,
        trigger=body.trigger,
        agent_id=body.agent_id,
        input_text=body.input_text,
        organization_id=body.organization_id,
        contact_id=body.contact_id,
        lead_id=body.lead_id,
        opportunity_id=body.opportunity_id,
        project_id=body.project_id,
        goal_type=body.goal_type,
    )
    outcome = _run_outcome(run)
    goal = run.goal_type.value if run.goal_type is not None else "none"
    metrics.runs_total.labels(goal=goal, outcome=outcome).inc()
    metrics.run_duration_seconds.observe(time.perf_counter() - started)
    if run.awaiting_approval:
        metrics.approvals_requested_total.inc()
    return run


@router.get("/runs")
async def list_runs(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    awaiting_approval: Annotated[bool | None, Query()] = None,
) -> list[PMRun]:
    return await pm.list_runs(tenant_id, awaiting_approval=awaiting_approval)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, pm: PMDep, tenant_id: Annotated[uuid.UUID, Query()]) -> PMRun:
    run = await pm.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="run not found")
    return run


@router.get("/runs/{run_id}/tasks")
async def list_run_tasks(
    run_id: uuid.UUID,
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[PMTaskStatus | None, Query(alias="status")] = None,
) -> list[PMTask]:
    return await pm.list_tasks(tenant_id, run_id=run_id, status=status_filter)


@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: uuid.UUID, body: ApproveRequest, pm: PMDep) -> PMTask:
    task = await pm.approve_task(body.tenant_id, task_id, approver=body.approver)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return task


@router.post("/scheduled-actions/execute-due")
async def execute_due(body: TenantBody, pm: PMDep, metrics: PMMetricsDep) -> ExecuteDueResponse:
    runs = await pm.execute_due(body.tenant_id)
    for run in runs:
        outcome = _run_outcome(run)
        goal = run.goal_type.value if run.goal_type is not None else "none"
        metrics.runs_total.labels(goal=goal, outcome=outcome).inc()
        if run.awaiting_approval:
            metrics.approvals_requested_total.inc()
    return ExecuteDueResponse(executed=len(runs), runs=runs)
