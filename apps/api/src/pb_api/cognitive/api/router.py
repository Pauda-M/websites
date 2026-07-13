"""Cognitive Core API composition.

Aggregates every subsystem route module under a single ``/cognitive`` prefix.
The platform mounts routers beneath ``/api/v1`` (see ``pb_api.api.router``), so
these endpoints are addressable at ``/api/v1/cognitive/...`` — the cognitive core
being the platform's "core" in the product sense.
"""

from __future__ import annotations

from fastapi import APIRouter

from pb_api.cognitive.api.routes import (
    agents,
    context,
    events,
    goals,
    health,
    memory,
    planning,
    policy,
    procedural,
    reflection,
    semantic,
    tools,
)

cognitive_router = APIRouter(prefix="/cognitive")

cognitive_router.include_router(health.router)
cognitive_router.include_router(memory.router)
cognitive_router.include_router(semantic.router)
cognitive_router.include_router(procedural.router)
cognitive_router.include_router(goals.router)
cognitive_router.include_router(agents.router)
cognitive_router.include_router(tools.router)
cognitive_router.include_router(policy.router)
cognitive_router.include_router(reflection.router)
cognitive_router.include_router(planning.router)
cognitive_router.include_router(context.router)
cognitive_router.include_router(events.router)

__all__ = ["cognitive_router"]
