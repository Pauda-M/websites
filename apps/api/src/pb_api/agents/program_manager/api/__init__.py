"""Program Manager HTTP API layer (FastAPI).

Exposes the ``program_manager_router`` — the aggregate router mounting every
route module under ``/agents/program-manager`` — plus the per-request ``PMDep``
dependency.
"""

from pb_api.agents.program_manager.api.deps import PMDep, get_program_manager
from pb_api.agents.program_manager.api.router import program_manager_router

__all__ = ["PMDep", "get_program_manager", "program_manager_router"]
