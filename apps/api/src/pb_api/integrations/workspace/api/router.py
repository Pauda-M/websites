"""Workspace integration API composition.

Aggregates every workspace route module under a single ``/integrations/workspace``
prefix. The platform mounts routers beneath ``/api/v1`` (see ``pb_api.api.router``),
so these endpoints are addressable at ``/api/v1/integrations/workspace/...``.
"""

from __future__ import annotations

from fastapi import APIRouter

from pb_api.integrations.workspace.api.routes import (
    approvals,
    calendar,
    connections,
    contacts,
    directory,
    documents,
    health,
    mail,
    search,
    sync,
    tasks,
)

workspace_router = APIRouter(prefix="/integrations/workspace")

workspace_router.include_router(health.router)
workspace_router.include_router(connections.router)
workspace_router.include_router(sync.router)
workspace_router.include_router(mail.router)
workspace_router.include_router(calendar.router)
workspace_router.include_router(directory.router)
workspace_router.include_router(contacts.router)
workspace_router.include_router(documents.router)
workspace_router.include_router(tasks.router)
workspace_router.include_router(approvals.router)
workspace_router.include_router(search.router)

__all__ = ["workspace_router"]
