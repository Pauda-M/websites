"""Reflection routes: capture and recall task reflections."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import ReflectRequest
from pb_api.cognitive.domain.reflection import Reflection

router = APIRouter(prefix="/reflections", tags=["cognitive-reflections"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def reflect(body: ReflectRequest, core: CoreDep) -> Reflection:
    return await core.reflection.reflect(
        tenant_id=body.tenant_id,
        objective=body.objective,
        outcome=body.outcome,
        success=body.success,
        agent_id=body.agent_id,
        task_id=body.task_id,
        failure_reason=body.failure_reason,
        lessons_learned=body.lessons_learned,
        confidence=body.confidence,
        future_recommendations=body.future_recommendations,
    )


@router.get("")
async def list_reflections(
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    agent_id: Annotated[uuid.UUID | None, Query()] = None,
    task_id: Annotated[uuid.UUID | None, Query()] = None,
    success: Annotated[bool | None, Query()] = None,
) -> list[Reflection]:
    return await core.reflection.list(
        tenant_id, agent_id=agent_id, task_id=task_id, success=success
    )


@router.get("/{reflection_id}")
async def get_reflection(
    reflection_id: uuid.UUID,
    core: CoreDep,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Reflection:
    reflection = await core.reflection.get(tenant_id, reflection_id)
    if reflection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="reflection not found")
    return reflection
