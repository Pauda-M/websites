from __future__ import annotations

import uuid

import pytest

from pb_api.cognitive.domain.events import EventType
from pb_api.cognitive.domain.goals import GoalLevel, GoalStatus
from pb_api.cognitive.services import CognitiveCore


async def test_reflection_stores_event_and_episodic_memory(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    agent = await core.agents.register(tenant_id=tenant, name="QA", role="qa")
    reflection = await core.reflection.reflect(
        tenant_id=tenant,
        agent_id=agent.id,
        objective="Run the regression suite",
        outcome="12 tests failed",
        success=False,
        lessons_learned=["flaky fixture in payments"],
        future_recommendations=["quarantine the flaky test"],
    )
    assert reflection.success is False
    events = await core.events.history(tenant, event_type=EventType.AGENT_REFLECTION_RECORDED)
    assert len(events) == 1
    # A reflection is also written to episodic memory for later recall.
    recent = await core.episodic.recent(tenant)
    assert any("Reflection" in event.summary for event in recent)


async def test_context_builder_assembles_sections_within_budget(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    await core.goals.create_goal(
        tenant_id=tenant, level=GoalLevel.COMPANY, title="Delight customers"
    )
    goal = (await core.goals.list(tenant))[0]
    await core.goals.set_status(tenant, goal.id, GoalStatus.ACTIVE)
    await core.episodic.record(tenant_id=tenant, actor="a", summary="Customer praised support")

    built = await core.context_builder.build(
        tenant_id=tenant, scope_key="s", query="customer support"
    )
    names = {section.name for section in built.sections}
    assert "goals" in names
    assert "memories" in names
    assert built.total_tokens <= built.token_budget
    # Recall emitted events for the recalled memories.
    recalled = await core.events.history(tenant, event_type=EventType.MEMORY_ITEM_RECALLED)
    assert len(recalled) >= 1


async def test_prompt_builder_is_dynamic_and_complete(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    agent = await core.agents.register(
        tenant_id=tenant,
        name="Solutions Architect",
        role="solutions_architect",
        metadata={"mission": "Design winning solutions."},
    )
    await core.episodic.record(tenant_id=tenant, actor="a", summary="Discovery call completed")
    prompt = await core.prompt_builder.build(
        tenant_id=tenant, agent_id=agent.id, task="Draft a solution outline"
    )
    assert "Solutions Architect" in prompt.system
    assert "Design winning solutions." in prompt.system
    assert "# Current Task" in prompt.system
    assert "# Output Requirements" in prompt.system
    assert "identity" in prompt.sections_included
    assert "current_task" in prompt.sections_included
    assert prompt.token_estimate > 0


async def test_prompt_builder_unknown_agent_raises(core: CognitiveCore, tenant: uuid.UUID) -> None:
    with pytest.raises(ValueError, match="agent not registered"):
        await core.prompt_builder.build(
            tenant_id=tenant, agent_id=uuid.uuid4(), task="do something"
        )
