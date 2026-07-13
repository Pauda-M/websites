"""Program Manager API composition.

Aggregates every Program Manager route module under a single
``/agents/program-manager`` prefix. The platform mounts routers beneath
``/api/v1`` (see ``pb_api.api.router``), so these endpoints are addressable at
``/api/v1/agents/program-manager/...``.
"""

from __future__ import annotations

from fastapi import APIRouter

from pb_api.agents.program_manager.api.routes import (
    crm,
    health,
    lifecycle,
    proposals,
    scheduling,
)

program_manager_router = APIRouter(prefix="/agents/program-manager")

program_manager_router.include_router(health.router)
program_manager_router.include_router(lifecycle.router)
program_manager_router.include_router(crm.router)
program_manager_router.include_router(proposals.router)
program_manager_router.include_router(scheduling.router)

__all__ = ["program_manager_router"]
