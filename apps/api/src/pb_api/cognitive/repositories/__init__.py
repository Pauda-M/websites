"""Async, tenant-scoped SQLAlchemy repositories for the Cognitive Core.

Every repository subclasses :class:`BaseRepository`, is constructed with an
``AsyncSession``, and scopes every query by ``tenant_id`` — cross-tenant access
is impossible by construction (Genesis §12.6).
"""

from __future__ import annotations

from pb_api.cognitive.repositories.agents import AgentRepository
from pb_api.cognitive.repositories.base import BaseRepository
from pb_api.cognitive.repositories.episodic import EpisodicRepository
from pb_api.cognitive.repositories.events import EventRepository
from pb_api.cognitive.repositories.goals import GoalHistoryRepository, GoalRepository
from pb_api.cognitive.repositories.memory import MemoryRepository, WorkingMemoryRepository
from pb_api.cognitive.repositories.planning import PlanRepository
from pb_api.cognitive.repositories.policy import PolicyRepository
from pb_api.cognitive.repositories.procedural import ProcedureRepository
from pb_api.cognitive.repositories.reflection import ReflectionRepository
from pb_api.cognitive.repositories.semantic import SemanticRepository
from pb_api.cognitive.repositories.tools import ToolRepository

__all__ = [
    "AgentRepository",
    "BaseRepository",
    "EpisodicRepository",
    "EventRepository",
    "GoalHistoryRepository",
    "GoalRepository",
    "MemoryRepository",
    "PlanRepository",
    "PolicyRepository",
    "ProcedureRepository",
    "ReflectionRepository",
    "SemanticRepository",
    "ToolRepository",
    "WorkingMemoryRepository",
]
