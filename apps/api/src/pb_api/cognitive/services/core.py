"""CognitiveCore facade.

Assembles every repository and service from a single ``AsyncSession`` and exposes
them as attributes. This is the single composition root the API layer and tests
use, so wiring lives in exactly one place.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.repositories.agents import AgentRepository
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
from pb_api.cognitive.services.agent_registry import AgentRegistry
from pb_api.cognitive.services.consolidation import MemoryConsolidationService
from pb_api.cognitive.services.context_builder import ContextBuilder
from pb_api.cognitive.services.episodic_memory import EpisodicMemoryService
from pb_api.cognitive.services.event_processor import EventProcessor
from pb_api.cognitive.services.goal_manager import GoalManager
from pb_api.cognitive.services.planning_engine import PlanningEngine
from pb_api.cognitive.services.policy_engine import PolicyEngine
from pb_api.cognitive.services.procedural_memory import ProceduralMemoryService
from pb_api.cognitive.services.prompt_builder import PromptBuilder
from pb_api.cognitive.services.ranking import HeuristicMemoryRanker
from pb_api.cognitive.services.reflection_engine import ReflectionEngine
from pb_api.cognitive.services.semantic_memory import SemanticMemoryService
from pb_api.cognitive.services.tool_registry import ToolRegistry
from pb_api.cognitive.services.working_memory import WorkingMemoryService


class CognitiveCore:
    """Composition root: all cognitive services wired to one session."""

    def __init__(self, session: AsyncSession, settings: CognitiveSettings | None = None) -> None:
        self.session = session
        self.settings = settings or get_cognitive_settings()

        # Repositories.
        self.memory_repo = MemoryRepository(session)
        goal_repo = GoalRepository(session)

        # Cross-cutting.
        self.events = EventProcessor(EventRepository(session))
        self.ranker = HeuristicMemoryRanker(self.settings)

        # Memory subsystems.
        self.working_memory = WorkingMemoryService(WorkingMemoryRepository(session), self.settings)
        self.episodic = EpisodicMemoryService(
            EpisodicRepository(session), self.memory_repo, self.events
        )
        self.semantic = SemanticMemoryService(SemanticRepository(session), self.events)
        self.procedural = ProceduralMemoryService(ProcedureRepository(session), self.events)
        self.consolidation = MemoryConsolidationService(
            self.memory_repo, self.events, self.settings
        )

        # Cognition.
        self.goals = GoalManager(goal_repo, GoalHistoryRepository(session), self.events)
        self.agents = AgentRegistry(AgentRepository(session), self.events)
        self.tools = ToolRegistry(ToolRepository(session))
        self.policies = PolicyEngine(PolicyRepository(session))
        self.reflection = ReflectionEngine(
            ReflectionRepository(session), self.episodic, self.events
        )
        self.planning = PlanningEngine(PlanRepository(session), goal_repo, self.events)

        self.context_builder = ContextBuilder(
            memory_repo=self.memory_repo,
            goal_repo=goal_repo,
            policy_repo=PolicyRepository(session),
            semantic_repo=SemanticRepository(session),
            episodic_repo=EpisodicRepository(session),
            ranker=self.ranker,
            events=self.events,
            settings=self.settings,
        )
        self.prompt_builder = PromptBuilder(
            self.agents, self.context_builder, self.working_memory, self.reflection, self.settings
        )
