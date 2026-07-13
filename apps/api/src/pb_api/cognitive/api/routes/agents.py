"""Agent registry routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import AgentRegisterRequest, AgentStatusRequest
from pb_api.cognitive.domain.agents import AgentRegistration, AgentStatus
from pb_api.cognitive.domain.common import AuthorityLevel

router = APIRouter(prefix="/agents", tags=["cognitive-agents"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_agent(body: AgentRegisterRequest, core: CoreDep) -> AgentRegistration:
    return await core.agents.register(
        tenant_id=body.tenant_id,
        name=body.name,
        role=body.role,
        capabilities=body.capabilities,
        default_authority=AuthorityLevel(body.default_authority),
        tools=body.tools,
        memory_access=body.memory_access,
        goal_ids=body.goal_ids,
        policy_ids=body.policy_ids,
        metadata=body.metadata,
    )


@router.get("")
async def list_agents(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    role: Annotated[str | None, Query()] = None,
    status_filter: Annotated[AgentStatus | None, Query(alias="status")] = None,
) -> list[AgentRegistration]:
    return await core.agents.list(tenant_id, role=role, status=status_filter)


@router.get("/{agent_id}")
async def get_agent(
    agent_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> AgentRegistration:
    agent = await core.agents.get(tenant_id, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
    return agent


@router.post("/{agent_id}/status")
async def set_agent_status(
    agent_id: uuid.UUID, body: AgentStatusRequest, core: CoreDep
) -> AgentRegistration:
    agent = await core.agents.set_status(body.tenant_id, agent_id, body.status)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
    return agent
