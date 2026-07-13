"""Policy engine routes: manage rules and evaluate actions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import PolicyCreateRequest, PolicyEvaluateRequest
from pb_api.cognitive.domain.common import AuthorityLevel
from pb_api.cognitive.domain.policy import Policy, PolicyDecision, PolicyRequest

router = APIRouter(prefix="/policies", tags=["cognitive-policies"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_policy(body: PolicyCreateRequest, core: CoreDep) -> Policy:
    policy = Policy(
        tenant_id=body.tenant_id,
        name=body.name,
        action=body.action,
        resource=body.resource,
        effect=body.effect,
        min_authority=AuthorityLevel(body.min_authority),
        priority=body.priority,
        enabled=body.enabled,
        description=body.description,
        metadata=body.metadata,
    )
    return await core.policies.add_policy(policy)


@router.get("")
async def list_policies(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    enabled_only: Annotated[bool, Query()] = True,
) -> list[Policy]:
    return await core.policies.list_policies(tenant_id, enabled_only=enabled_only)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    deleted = await core.policies.remove_policy(tenant_id, policy_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="policy not found")


@router.post("/evaluate")
async def evaluate_policy(body: PolicyEvaluateRequest, core: CoreDep) -> PolicyDecision:
    request = PolicyRequest(
        tenant_id=body.tenant_id,
        actor_authority=AuthorityLevel(body.actor_authority),
        action=body.action,
        resource=body.resource,
    )
    return await core.policies.evaluate(request)
