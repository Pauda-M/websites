"""Workspace integration HTTP API layer (FastAPI).

Exposes the ``workspace_router`` — the aggregate router mounting every route module
under ``/integrations/workspace`` — the per-request ``WsDep`` dependency, and the
app-scoped resource lifecycle hooks the application lifespan drives.
"""

from pb_api.integrations.workspace.api.deps import (
    WsDep,
    close_workspace_state,
    get_workspace_context,
    init_workspace_state,
)
from pb_api.integrations.workspace.api.router import workspace_router

__all__ = [
    "WsDep",
    "close_workspace_state",
    "get_workspace_context",
    "init_workspace_state",
    "workspace_router",
]
