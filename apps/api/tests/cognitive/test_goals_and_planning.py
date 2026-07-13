from __future__ import annotations

import uuid

import pytest

from pb_api.cognitive.domain.goals import GoalLevel, GoalStatus
from pb_api.cognitive.domain.planning import PlanStatus, PlanTask
from pb_api.cognitive.services import CognitiveCore


async def test_goal_hierarchy_and_history(core: CognitiveCore, tenant: uuid.UUID) -> None:
    company = await core.goals.create_goal(
        tenant_id=tenant, level=GoalLevel.COMPANY, title="Grow ARR 2x", priority=1
    )
    dept = await core.goals.create_goal(
        tenant_id=tenant,
        level=GoalLevel.DEPARTMENT,
        title="Sales: close 40 deals",
        parent_id=company.id,
    )
    assert dept.parent_id == company.id
    children = await core.goals.children(tenant, company.id)
    assert [g.id for g in children] == [dept.id]

    await core.goals.set_progress(tenant, dept.id, 0.5)
    updated = await core.goals.get(tenant, dept.id)
    assert updated is not None
    assert updated.progress == 0.5
    history = await core.goals.history(tenant, dept.id)
    assert any("progress" in entry.change for entry in history)


async def test_goal_unknown_parent_rejected(core: CognitiveCore, tenant: uuid.UUID) -> None:
    with pytest.raises(ValueError, match="parent goal not found"):
        await core.goals.create_goal(
            tenant_id=tenant, level=GoalLevel.TASK, title="orphan", parent_id=uuid.uuid4()
        )


async def test_goal_dependencies_gate_activation(core: CognitiveCore, tenant: uuid.UUID) -> None:
    dep = await core.goals.create_goal(tenant_id=tenant, level=GoalLevel.TASK, title="prereq")
    goal = await core.goals.create_goal(
        tenant_id=tenant, level=GoalLevel.TASK, title="blocked", depends_on=[dep.id]
    )
    with pytest.raises(ValueError, match="not achieved"):
        await core.goals.set_status(tenant, goal.id, GoalStatus.ACTIVE)

    await core.goals.set_status(tenant, dep.id, GoalStatus.ACHIEVED)
    activated = await core.goals.set_status(tenant, goal.id, GoalStatus.ACTIVE)
    assert activated is not None
    assert activated.status is GoalStatus.ACTIVE


async def test_planning_decomposes_goal_children(core: CognitiveCore, tenant: uuid.UUID) -> None:
    parent = await core.goals.create_goal(tenant_id=tenant, level=GoalLevel.AGENT, title="ship")
    await core.goals.create_goal(
        tenant_id=tenant, level=GoalLevel.TASK, title="design", parent_id=parent.id, priority=1
    )
    await core.goals.create_goal(
        tenant_id=tenant, level=GoalLevel.TASK, title="build", parent_id=parent.id, priority=2
    )
    plan = await core.planning.create_plan(
        tenant_id=tenant, objective="Ship the feature", goal_id=parent.id
    )
    assert len(plan.tasks) == 2
    assert plan.tasks[0].title == "design"  # ordered by priority
    assert plan.status is PlanStatus.DRAFT


async def test_planning_explicit_tasks_and_status(core: CognitiveCore, tenant: uuid.UUID) -> None:
    plan = await core.planning.create_plan(
        tenant_id=tenant,
        objective="Manual plan",
        tasks=[PlanTask(key="a", title="Step A"), PlanTask(key="b", title="Step B")],
    )
    assert len(plan.tasks) == 2
    activated = await core.planning.set_status(tenant, plan.id, PlanStatus.ACTIVE)
    assert activated is not None
    assert activated.status is PlanStatus.ACTIVE
