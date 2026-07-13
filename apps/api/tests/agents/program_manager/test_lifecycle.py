from __future__ import annotations

import uuid
from datetime import timedelta

from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.domain.common import (
    PM_LIFECYCLE_ORDER,
    PMGoalType,
    PMState,
    utcnow,
)
from pb_api.agents.program_manager.domain.run import PMTaskStatus, PMTriggerType
from pb_api.cognitive.domain.events import EventType


async def test_full_lifecycle_completes_and_visits_every_state(
    bounded_pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await bounded_pm.bootstrap(tenant)
    org = await bounded_pm.crm.create_organization(tenant_id=tenant, name="Acme")
    run = await bounded_pm.run_cycle(
        tenant_id=tenant,
        trigger=PMTriggerType.INBOUND_MESSAGE,
        input_text="I have a question about your services",
        organization_id=org.id,
    )
    assert run.goal_type is PMGoalType.REPLY_TO_CUSTOMER
    assert run.state is PMState.IDLE
    assert run.success is True
    assert run.awaiting_approval is False
    # Every happy-path state was visited, in order (IDLE bookends the run).
    happy = [s.value for s in PM_LIFECYCLE_ORDER[1:]]  # observe..schedule_next
    assert run.states_visited[: len(happy)] == happy
    assert run.states_visited[-1] == PMState.IDLE.value


async def test_l1_agent_pauses_awaiting_approval_on_outward_action(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await pm.bootstrap(tenant)
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    run = await pm.run_cycle(
        tenant_id=tenant,
        trigger=PMTriggerType.INBOUND_MESSAGE,
        input_text="please reply to me",
        organization_id=org.id,
    )
    assert run.state is PMState.AWAITING_APPROVAL
    assert run.awaiting_approval is True
    assert run.success is None
    tasks = await pm.list_tasks(tenant, run_id=run.id)
    statuses = {t.step_key: t.status for t in tasks}
    assert statuses["gather"] is PMTaskStatus.COMPLETED
    assert statuses["send"] is PMTaskStatus.AWAITING_APPROVAL
    # An approval-requested event was recorded.
    events = await pm.core.events.history(tenant, event_type="pb.pm.action.approval_requested")
    assert len(events) == 1


async def test_approve_task_clears_awaiting_flag(pm: ProgramManager, tenant: uuid.UUID) -> None:
    await pm.bootstrap(tenant)
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    run = await pm.run_cycle(tenant_id=tenant, input_text="reply please", organization_id=org.id)
    pending = [
        t
        for t in await pm.list_tasks(tenant, run_id=run.id)
        if t.status is PMTaskStatus.AWAITING_APPROVAL
    ]
    assert len(pending) == 1
    approved = await pm.approve_task(tenant, pending[0].id, approver="alice@pb")
    assert approved is not None
    assert approved.status is PMTaskStatus.COMPLETED
    assert approved.approved_by == "alice@pb"
    reloaded = await pm.get_run(tenant, run.id)
    assert reloaded is not None
    assert reloaded.awaiting_approval is False


async def test_escalation_intent_is_detected_and_creates_human_task(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await pm.bootstrap(tenant)
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme")
    run = await pm.run_cycle(
        tenant_id=tenant,
        input_text="I am unhappy and want a refund, this is urgent",
        organization_id=org.id,
    )
    assert run.goal_type is PMGoalType.ESCALATE_ISSUE
    assert run.success is True
    # A CRM task was created for a human to handle the escalation.
    crm_tasks = await pm.crm.list_tasks(tenant)
    assert any("escalat" in t.title.lower() for t in crm_tasks)


async def test_lifecycle_writes_memory_reflection_and_cognitive_goal(
    bounded_pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await bounded_pm.bootstrap(tenant)
    org = await bounded_pm.crm.create_organization(tenant_id=tenant, name="Acme")
    run = await bounded_pm.run_cycle(
        tenant_id=tenant, input_text="a question", organization_id=org.id
    )
    # A cognitive goal was created and linked.
    assert run.goal_id is not None
    assert await bounded_pm.core.goals.get(tenant, run.goal_id) is not None
    # Episodic memory captured the run.
    recent = await bounded_pm.core.episodic.recent(tenant)
    assert any("Reply to the customer" in e.summary for e in recent)
    # A reflection was recorded.
    reflections = await bounded_pm.core.reflection.list(tenant)
    assert len(reflections) >= 1
    # The relationship score moved on success.
    reloaded = await bounded_pm.crm.get_organization(tenant, org.id)
    assert reloaded is not None
    assert reloaded.relationship_score > 0.5


async def test_successful_run_schedules_a_followup(
    bounded_pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await bounded_pm.bootstrap(tenant)
    org = await bounded_pm.crm.create_organization(tenant_id=tenant, name="Acme")
    await bounded_pm.run_cycle(tenant_id=tenant, input_text="hello", organization_id=org.id)
    due_later = await bounded_pm.scheduler.due(tenant, now=utcnow() + timedelta(days=30))
    assert len(due_later) >= 1


async def test_execute_due_runs_scheduled_actions_and_marks_them_executed(
    bounded_pm: ProgramManager, tenant: uuid.UUID
) -> None:
    await bounded_pm.bootstrap(tenant)
    org = await bounded_pm.crm.create_organization(tenant_id=tenant, name="Acme")
    await bounded_pm.run_cycle(tenant_id=tenant, input_text="hello", organization_id=org.id)
    future = utcnow() + timedelta(days=30)
    runs = await bounded_pm.execute_due(tenant, now=future)
    assert len(runs) >= 1
    assert all(r.trigger is PMTriggerType.SCHEDULED_ACTION for r in runs)
    # Nothing remains due after execution.
    assert await bounded_pm.scheduler.due(tenant, now=future) == []


async def test_runs_are_tenant_isolated(
    pm: ProgramManager, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    await pm.bootstrap(tenant)
    run = await pm.run_cycle(tenant_id=tenant, input_text="hi")
    assert await pm.get_run(other_tenant, run.id) is None
    assert await pm.list_runs(other_tenant) == []


async def test_run_started_event_is_recorded(pm: ProgramManager, tenant: uuid.UUID) -> None:
    await pm.bootstrap(tenant)
    run = await pm.run_cycle(tenant_id=tenant, input_text="hi")
    started = await pm.core.events.history(tenant, event_type="pb.pm.run.started")
    assert any(e.aggregate_id == run.id for e in started)
    # The cognitive agent was registered during bootstrap.
    agent_events = await pm.core.events.history(tenant, event_type=EventType.AGENT_REGISTERED)
    assert len(agent_events) >= 1
