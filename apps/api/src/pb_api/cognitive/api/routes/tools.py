"""Tool registry routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import ToolHealthRequest, ToolRegisterRequest
from pb_api.cognitive.domain.tools import ToolDefinition

router = APIRouter(prefix="/tools", tags=["cognitive-tools"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_tool(body: ToolRegisterRequest, core: CoreDep) -> ToolDefinition:
    return await core.tools.register(
        tenant_id=body.tenant_id,
        name=body.name,
        version=body.version,
        description=body.description,
        permissions=body.permissions,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        side_effect=body.side_effect,
        timeout_seconds=body.timeout_seconds,
        metadata=body.metadata,
    )


@router.get("")
async def list_tools(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[ToolDefinition]:
    return await core.tools.list(tenant_id)


@router.get("/{tool_id}")
async def get_tool(
    tool_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ToolDefinition:
    tool = await core.tools.get(tenant_id, tool_id)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="tool not found")
    return tool


@router.post("/{tool_id}/health")
async def set_tool_health(
    tool_id: uuid.UUID, body: ToolHealthRequest, core: CoreDep
) -> ToolDefinition:
    tool = await core.tools.set_health(body.tenant_id, tool_id, body.health)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="tool not found")
    return tool
