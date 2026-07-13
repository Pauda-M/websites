"""Context + prompt assembly routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from pb_api.cognitive.api.deps import CoreDep
from pb_api.cognitive.api.schemas import ContextBuildRequest, PromptBuildRequest
from pb_api.cognitive.domain.context import AssembledPrompt, BuiltContext

router = APIRouter(prefix="/context", tags=["cognitive-context"])


@router.post("/build")
async def build_context(body: ContextBuildRequest, core: CoreDep) -> BuiltContext:
    return await core.context_builder.build(
        tenant_id=body.tenant_id,
        scope_key=body.scope_key,
        query=body.query,
        goal_id=body.goal_id,
        customer_id=body.customer_id,
        project_id=body.project_id,
        conversation_id=body.conversation_id,
        token_budget=body.token_budget,
        max_memories=body.max_memories,
    )


@router.post("/prompt")
async def build_prompt(body: PromptBuildRequest, core: CoreDep) -> AssembledPrompt:
    try:
        return await core.prompt_builder.build(
            tenant_id=body.tenant_id,
            agent_id=body.agent_id,
            task=body.task,
            scope_key=body.scope_key,
            query=body.query,
            token_budget=body.token_budget,
            output_requirements=body.output_requirements,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
