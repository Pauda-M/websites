from __future__ import annotations

import uuid

from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.domain.common import PMAuthorityLevel, PMGoalType


async def test_reply_plan_has_read_draft_send_with_escalating_authority(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    plan = await pm.planner.build_plan(
        tenant_id=tenant, goal_type=PMGoalType.REPLY_TO_CUSTOMER, objective="Reply"
    )
    keys = [step.key for step in plan.steps]
    assert keys == ["gather", "draft", "send"]
    send = plan.steps[-1]
    assert send.action == "communication.send"
    assert send.authority_required is PMAuthorityLevel.ACT_BOUNDED
    # Dependencies form a chain.
    assert plan.steps[1].depends_on == ["gather"]
    assert send.depends_on == ["draft"]


async def test_create_proposal_plan_drafts_then_delivers(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    plan = await pm.planner.build_plan(
        tenant_id=tenant, goal_type=PMGoalType.CREATE_PROPOSAL, objective="Propose"
    )
    actions = [step.action for step in plan.steps]
    assert actions == ["crm.read", "proposal.draft", "proposal.send"]
    assert plan.steps[-1].authority_required is PMAuthorityLevel.ACT_BOUNDED


async def test_no_action_plan_is_empty(pm: ProgramManager, tenant: uuid.UUID) -> None:
    plan = await pm.planner.build_plan(
        tenant_id=tenant, goal_type=PMGoalType.NO_ACTION, objective="Observe"
    )
    assert plan.steps == []


async def test_plan_is_capped_at_max_steps(pm: ProgramManager, tenant: uuid.UUID) -> None:
    pm.settings.max_plan_steps = 1
    plan = await pm.planner.build_plan(
        tenant_id=tenant, goal_type=PMGoalType.REPLY_TO_CUSTOMER, objective="Reply"
    )
    assert len(plan.steps) == 1


async def test_every_goal_type_produces_a_persisted_plan(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    for goal in PMGoalType:
        plan = await pm.planner.build_plan(tenant_id=tenant, goal_type=goal, objective=goal.value)
        assert isinstance(plan.id, uuid.UUID)
        assert plan.goal_type is goal
        # Persisted and retrievable.
        assert await pm.planner.plans.get(tenant, plan.id) is not None
