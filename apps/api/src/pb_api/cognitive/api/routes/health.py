"""Cognitive Core liveness + self-description.

A static probe: it answers "is the cognitive module loaded and which subsystems
does it expose" without touching the database, so it needs no ``CoreDep``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from pb_api.cognitive import __version__

router = APIRouter(tags=["cognitive-health"])

# The 15 cognitive subsystems assembled by the CognitiveCore facade.
SUBSYSTEMS: list[str] = [
    "working_memory",
    "episodic",
    "semantic",
    "procedural",
    "consolidation",
    "ranker",
    "goals",
    "agents",
    "tools",
    "policies",
    "reflection",
    "planning",
    "context_builder",
    "prompt_builder",
    "events",
]


class CognitiveHealth(BaseModel):
    status: Literal["ok"]
    module: Literal["cognitive"]
    version: str
    subsystems: list[str]


@router.get("/health", response_model=CognitiveHealth)
async def health() -> CognitiveHealth:
    return CognitiveHealth(
        status="ok",
        module="cognitive",
        version=__version__,
        subsystems=SUBSYSTEMS,
    )
