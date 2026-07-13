"""Cognitive Core HTTP API layer (FastAPI).

Exposes the ``cognitive_router`` — the aggregate router mounting every subsystem
under ``/cognitive`` — plus the per-request ``CoreDep`` dependency.
"""

from pb_api.cognitive.api.deps import CoreDep, get_cognitive_core
from pb_api.cognitive.api.router import cognitive_router

__all__ = ["CoreDep", "cognitive_router", "get_cognitive_core"]
