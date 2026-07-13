"""Prompt Builder.

Never uses static prompts. Dynamically assembles Identity, Mission, Goals,
Working Memory, Policies, Relevant Knowledge, Recent Events, Current Task,
Reflection, and Output Requirements (Phase 7 spec) into a system prompt tailored
to the agent, tenant, and task at hand.
"""

from __future__ import annotations

import uuid

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.domain.common import estimate_tokens
from pb_api.cognitive.domain.context import AssembledPrompt
from pb_api.cognitive.services.agent_registry import AgentRegistry
from pb_api.cognitive.services.context_builder import ContextBuilder
from pb_api.cognitive.services.reflection_engine import ReflectionEngine
from pb_api.cognitive.services.working_memory import WorkingMemoryService

_DEFAULT_OUTPUT_REQUIREMENTS = (
    "Respond with the next action or answer only. Stay within your authority and "
    "the policies above; if an action exceeds your authority or a policy requires "
    "approval, request approval instead of acting. Cite the memory or knowledge you "
    "relied on."
)


class PromptBuilder:
    def __init__(
        self,
        agents: AgentRegistry,
        context_builder: ContextBuilder,
        working_memory: WorkingMemoryService,
        reflection: ReflectionEngine,
        settings: CognitiveSettings | None = None,
    ) -> None:
        self._agents = agents
        self._context = context_builder
        self._working = working_memory
        self._reflection = reflection
        self._settings = settings or get_cognitive_settings()

    async def build(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID,
        task: str,
        scope_key: str | None = None,
        query: str | None = None,
        token_budget: int | None = None,
        output_requirements: str | None = None,
    ) -> AssembledPrompt:
        agent = await self._agents.get(tenant_id, agent_id)
        if agent is None:
            raise ValueError("agent not registered")
        scope = scope_key or f"agent:{agent_id}:task"
        budget = token_budget or self._settings.default_token_budget

        context = await self._context.build(
            tenant_id=tenant_id,
            scope_key=scope,
            query=query or task,
            token_budget=budget,
        )
        working = await self._working.build_set(tenant_id, scope, token_budget=budget)
        recent_reflections = await self._reflection.list(tenant_id, agent_id=agent_id)
        mission = str(agent.metadata.get("mission", f"Operate as the {agent.role}."))

        blocks: list[str] = []
        included: list[str] = []

        blocks.append(
            f"# Identity\nYou are {agent.name}, the {agent.role} (authority level "
            f"A{int(agent.default_authority)})."
        )
        included.append("identity")

        blocks.append(f"# Mission\n{mission}")
        included.append("mission")

        section_titles = {
            "goals": "# Goals",
            "memories": "# Relevant Memories",
            "knowledge": "# Relevant Knowledge",
            "policies": "# Policies",
            "recent_events": "# Recent Events",
        }
        by_name = {section.name: section for section in context.sections}
        for name, title in section_titles.items():
            section = by_name.get(name)
            if section is not None:
                blocks.append(f"{title}\n{section.content}")
                included.append(name)

        if working.entries:
            working_lines = "\n".join(f"- {entry.content}" for entry in working.entries)
            blocks.append(f"# Working Memory\n{working_lines}")
            included.append("working_memory")

        if recent_reflections:
            latest = recent_reflections[0]
            verdict = "succeeded" if latest.success else "failed"
            lessons = "; ".join(latest.lessons_learned) or "none recorded"
            blocks.append(
                f"# Reflection\nLast task '{latest.objective}' {verdict}. Lessons: {lessons}."
            )
            included.append("reflection")

        blocks.append(f"# Current Task\n{task}")
        included.append("current_task")

        blocks.append(
            f"# Output Requirements\n{output_requirements or _DEFAULT_OUTPUT_REQUIREMENTS}"
        )
        included.append("output_requirements")

        system = "\n\n".join(blocks)
        return AssembledPrompt(
            tenant_id=tenant_id,
            system=system,
            context=context,
            token_estimate=estimate_tokens(system, self._settings.chars_per_token),
            sections_included=included,
        )
