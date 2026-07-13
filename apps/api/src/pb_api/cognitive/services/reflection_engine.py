"""Reflection Engine.

Every completed task creates a reflection (objective, outcome, success/failure,
lessons learned, confidence, future recommendations). The reflection is stored,
emitted as ``pb.agent.reflection.recorded``, and written to episodic memory so
the agent can recall its own lessons later.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.reflection import Reflection
from pb_api.cognitive.repositories.reflection import ReflectionRepository
from pb_api.cognitive.services.episodic_memory import EpisodicMemoryService
from pb_api.cognitive.services.event_processor import EventProcessor


class ReflectionEngine:
    def __init__(
        self,
        repository: ReflectionRepository,
        episodic: EpisodicMemoryService,
        events: EventProcessor,
    ) -> None:
        self._repo = repository
        self._episodic = episodic
        self._events = events

    async def reflect(
        self,
        *,
        tenant_id: uuid.UUID,
        objective: str,
        outcome: str,
        success: bool,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        failure_reason: str | None = None,
        lessons_learned: list[str] | None = None,
        confidence: float = 0.5,
        future_recommendations: list[str] | None = None,
    ) -> Reflection:
        reflection = Reflection(
            tenant_id=tenant_id,
            agent_id=agent_id,
            task_id=task_id,
            objective=objective,
            outcome=outcome,
            success=success,
            failure_reason=failure_reason,
            lessons_learned=lessons_learned or [],
            confidence=confidence,
            future_recommendations=future_recommendations or [],
        )
        stored = await self._repo.add(reflection)

        verdict = "succeeded" if success else "failed"
        # Reflections on failure are more important to remember.
        importance = 0.6 if success else 0.8
        await self._episodic.record(
            tenant_id=tenant_id,
            actor=str(agent_id) if agent_id is not None else "system",
            summary=f"Reflection: '{objective}' {verdict}. {outcome}",
            importance=importance,
            confidence=confidence,
            metadata={"kind": "reflection", "reflection_id": str(stored.id)},
        )
        await self._events.record(
            event_type=EventType.AGENT_REFLECTION_RECORDED,
            tenant_id=tenant_id,
            actor=str(agent_id) if agent_id is not None else "system",
            aggregate_id=stored.id,
            payload={"success": success, "objective": objective},
        )
        return stored

    async def get(self, tenant_id: uuid.UUID, reflection_id: uuid.UUID) -> Reflection | None:
        return await self._repo.get(tenant_id, reflection_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        agent_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        success: bool | None = None,
    ) -> list[Reflection]:
        return await self._repo.list(tenant_id, agent_id=agent_id, task_id=task_id, success=success)
