"""Contacts routes: list contacts synchronized from the provider (port read)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.integrations.workspace.api.deps import WsDep
from pb_api.integrations.workspace.domain.contacts import WorkspaceContact

router = APIRouter(prefix="/contacts", tags=["workspace"])


@router.get("")
async def list_contacts(
    ctx: WsDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    connection_id: Annotated[uuid.UUID, Query()],
) -> list[WorkspaceContact]:
    page = await ctx.provider.contacts.list_contacts(tenant_id, connection_id)
    return list(page.items)
