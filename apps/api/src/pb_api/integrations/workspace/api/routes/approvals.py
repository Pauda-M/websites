"""Approval routes: inspect and decide pending actions, manage approval policies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.api.schemas import (
    ApprovalDecisionRequest,
    ApprovalPolicyRequest,
)
from pb_api.integrations.workspace.domain.approval import ApprovalPolicy, ApprovalRequest

router = APIRouter(prefix="/approvals", tags=["workspace"])


@router.get("/pending")
async def list_pending(
    ctx: WsDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> list[ApprovalRequest]:
    return await ctx.approvals.list_pending(tenant_id)


@router.post("/{request_id}/decide")
async def decide(
    request_id: uuid.UUID, body: ApprovalDecisionRequest, ctx: WsDep
) -> ApprovalRequest:
    request = await ctx.approvals.decide(
        body.tenant_id, request_id, approve=body.approve, decided_by=body.decided_by
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="approval request not found")
    return request


@router.get("/policies")
async def list_policies(
    ctx: WsDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> list[ApprovalPolicy]:
    return await ctx.approvals.list_policies(tenant_id)


@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def add_policy(body: ApprovalPolicyRequest, ctx: WsDep) -> ApprovalPolicy:
    policy = ApprovalPolicy(
        tenant_id=body.tenant_id,
        name=body.name,
        decision=body.decision,
        communication_type=body.communication_type,
        customer_organization_id=body.customer_organization_id,
        agent_id=body.agent_id,
        min_authority=body.min_authority,
        priority=body.priority,
    )
    return await ctx.approvals.add_policy(policy)
