"""Context Builder.

Collects memories, goals, policies, knowledge, and recent events, ranks the
memories, and assembles a token-bounded context optimised for an LLM call
(Phase 7 spec). Sections are added in priority order; once the token budget is
exhausted, later sections are truncated (never silently — ``truncated`` is set).
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.domain.common import estimate_tokens, hash_embedding
from pb_api.cognitive.domain.context import BuiltContext, ContextSection
from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.goals import GoalStatus
from pb_api.cognitive.domain.ranking import RankingContext
from pb_api.cognitive.repositories.episodic import EpisodicRepository
from pb_api.cognitive.repositories.goals import GoalRepository
from pb_api.cognitive.repositories.memory import MemoryRepository
from pb_api.cognitive.repositories.policy import PolicyRepository
from pb_api.cognitive.repositories.semantic import SemanticRepository
from pb_api.cognitive.services.event_processor import EventProcessor
from pb_api.cognitive.services.ranking import HeuristicMemoryRanker


class ContextBuilder:
    def __init__(
        self,
        *,
        memory_repo: MemoryRepository,
        goal_repo: GoalRepository,
        policy_repo: PolicyRepository,
        semantic_repo: SemanticRepository,
        episodic_repo: EpisodicRepository,
        ranker: HeuristicMemoryRanker,
        events: EventProcessor,
        settings: CognitiveSettings | None = None,
    ) -> None:
        self._memory = memory_repo
        self._goals = goal_repo
        self._policies = policy_repo
        self._semantic = semantic_repo
        self._episodic = episodic_repo
        self._ranker = ranker
        self._events = events
        self._settings = settings or get_cognitive_settings()

    async def build(
        self,
        *,
        tenant_id: uuid.UUID,
        scope_key: str,
        query: str | None = None,
        goal_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        token_budget: int | None = None,
        max_memories: int | None = None,
    ) -> BuiltContext:
        budget = token_budget or self._settings.default_token_budget
        limit = max_memories or self._settings.default_recall_limit

        sections: list[ContextSection] = []
        total = 0
        truncated = False

        def add_section(name: str, lines: list[str], item_count: int) -> None:
            nonlocal total, truncated
            if not lines:
                return
            content = "\n".join(lines)
            tokens = estimate_tokens(content, self._settings.chars_per_token)
            if total + tokens > budget:
                truncated = True
                return
            sections.append(
                ContextSection(
                    name=name, content=content, token_estimate=tokens, item_count=item_count
                )
            )
            total += tokens

        # 1. Goals (active first) — highest priority context.
        goals = await self._goals.list(tenant_id, status=GoalStatus.ACTIVE)
        add_section(
            "goals", [f"[{g.level.value}] {g.title} (p{g.priority})" for g in goals], len(goals)
        )

        # 2. Ranked memories relevant to the query/context.
        memories = await self._memory.list(tenant_id, include_archived=False, limit=500)
        ranking_context = RankingContext(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            goal_id=goal_id,
            customer_id=customer_id,
            project_id=project_id,
            query=query,
            query_embedding=hash_embedding(query) if query else None,
        )
        ranked = self._ranker.rank(memories, ranking_context).ranked[:limit]
        add_section(
            "memories",
            [
                f"- ({r.memory.memory_type.value}) {r.memory.summary or r.memory.content}"
                for r in ranked
            ],
            len(ranked),
        )
        # Recall reinforces the recalled memories and emits events.
        for r in ranked:
            await self._memory.touch(tenant_id, r.memory.id)
            await self._events.record(
                event_type=EventType.MEMORY_ITEM_RECALLED,
                tenant_id=tenant_id,
                aggregate_id=r.memory.id,
                payload={"scope": scope_key, "score": r.score},
            )

        # 3. Knowledge (semantic facts/concepts).
        knowledge = await self._semantic.list_items(tenant_id, limit=limit)
        add_section("knowledge", [f"- {k.name}: {k.content}" for k in knowledge], len(knowledge))

        # 4. Policies in force.
        policies = await self._policies.list(tenant_id, enabled_only=True)
        add_section(
            "policies",
            [f"- {p.effect.value.upper()} {p.action} on {p.resource}" for p in policies],
            len(policies),
        )

        # 5. Recent events (episodic timeline).
        recent = await self._episodic.recent(tenant_id, limit=limit)
        add_section("recent_events", [f"- {e.summary}" for e in recent], len(recent))

        return BuiltContext(
            tenant_id=tenant_id,
            scope_key=scope_key,
            sections=sections,
            total_tokens=total,
            token_budget=budget,
            truncated=truncated,
        )
