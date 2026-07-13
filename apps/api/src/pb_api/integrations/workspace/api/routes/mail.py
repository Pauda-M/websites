"""Mailbox routes: read and thread mail, sync, search, and governed outbound replies."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep, WsMetricsDep
from pb_api.integrations.workspace.api.schemas import (
    CategorizeRequest,
    FlagRequest,
    MoveRequest,
    ReplyRequest,
    SyncRequest,
)
from pb_api.integrations.workspace.domain.approval import ApprovalDecision
from pb_api.integrations.workspace.domain.mail import WorkspaceMessage
from pb_api.integrations.workspace.domain.sync import SyncState

router = APIRouter(prefix="/mail", tags=["workspace"])


@router.get("")
async def list_messages(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
    folder: Annotated[str, Query()] = "inbox",
) -> list[WorkspaceMessage]:
    return await ctx.mailbox.list_messages(tenant_id, connection_id, folder=folder)


@router.post("/sync")
async def sync_mailbox(body: SyncRequest, ctx: WsDep) -> SyncState:
    return await ctx.mailbox.sync(body.tenant_id, body.connection_id)


@router.get("/search")
async def search_messages(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    query: Annotated[str, Query()],
) -> list[WorkspaceMessage]:
    return await ctx.mailbox.search(tenant_id, query=query)


@router.get("/conversation/{conversation_id}")
async def get_conversation(
    conversation_id: str, ctx: WsDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> list[WorkspaceMessage]:
    return await ctx.mailbox.conversation(tenant_id, conversation_id)


@router.post("/reply")
async def prepare_reply(body: ReplyRequest, ctx: WsDep, metrics: WsMetricsDep) -> dict[str, object]:
    result = await ctx.mailbox.prepare_reply(
        body.tenant_id,
        body.connection_id,
        message_provider_id=body.message_provider_id,
        body=body.body,
        kind=body.kind,
        agent_id=body.agent_id,
        actor_authority=body.actor_authority,
    )
    decision = cast(ApprovalDecision, result["decision"])
    metrics.approvals_total.labels(decision=decision.decision.value).inc()
    return result


@router.post("/{message_provider_id}/categorize")
async def categorize_message(
    message_provider_id: str, body: CategorizeRequest, ctx: WsDep
) -> dict[str, object]:
    await ctx.mailbox.categorize(
        body.tenant_id,
        body.connection_id,
        message_provider_id=message_provider_id,
        categories=body.categories,
    )
    return {"ok": True}


@router.post("/{message_provider_id}/move")
async def move_message(
    message_provider_id: str, body: MoveRequest, ctx: WsDep
) -> dict[str, object]:
    await ctx.mailbox.move(
        body.tenant_id,
        body.connection_id,
        message_provider_id=message_provider_id,
        destination_folder=body.destination_folder,
    )
    return {"ok": True}


@router.post("/{message_provider_id}/flag")
async def flag_message(
    message_provider_id: str, body: FlagRequest, ctx: WsDep
) -> dict[str, object]:
    await ctx.mailbox.set_flag(
        body.tenant_id,
        body.connection_id,
        message_provider_id=message_provider_id,
        flagged=body.flagged,
    )
    return {"ok": True}
