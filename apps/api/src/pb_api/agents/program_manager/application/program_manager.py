"""ProgramManager — composition root and cognitive lifecycle orchestrator.

This is the single composition root for the Program Manager AI Employee: it wires
the Cognitive Core and every Program-Manager repository and service from one
``AsyncSession`` and drives the governed cognitive lifecycle
(``OBSERVE → UNDERSTAND → RETRIEVE_MEMORY → DETERMINE_GOAL → BUILD_CONTEXT →
REASON → PLAN → EXECUTE → REFLECT → STORE_MEMORY → SCHEDULE_NEXT``).

Every consequential action passes an authority gate before it runs; actions that
exceed the Program Manager's tier pause the run in ``AWAITING_APPROVAL`` rather
than executing. The Program Manager reuses the Cognitive Core for memory, goals,
planning-grade reasoning inputs, policy, reflection, and events — it never
re-implements them.
"""

from __future__ import annotations

import builtins
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.agents.program_manager.application.authority import AuthorityService
from pb_api.agents.program_manager.application.crm_service import CrmService
from pb_api.agents.program_manager.application.followup_engine import FollowUpEngine
from pb_api.agents.program_manager.application.personality import (
    DEFAULT_COMMUNICATION_STYLE,
    DEFAULT_PERSONALITY,
    CommunicationStyle,
    PersonalityProfile,
)
from pb_api.agents.program_manager.application.proposal_service import ProposalService
from pb_api.agents.program_manager.application.scheduler import Scheduler
from pb_api.agents.program_manager.application.task_planner import TaskPlanner
from pb_api.agents.program_manager.config import (
    ProgramManagerSettings,
    get_program_manager_settings,
)
from pb_api.agents.program_manager.domain.common import (
    FollowUpCadence,
    PMAuthorityLevel,
    PMGoalType,
    PMState,
    utcnow,
)
from pb_api.agents.program_manager.domain.crm import OpportunityStage
from pb_api.agents.program_manager.domain.events import PMEventType
from pb_api.agents.program_manager.domain.plan import PMPlan, PMPlanStep
from pb_api.agents.program_manager.domain.run import (
    PMRun,
    PMTask,
    PMTaskStatus,
    PMTriggerType,
)
from pb_api.agents.program_manager.domain.scheduling import ScheduledAction, SubjectType
from pb_api.agents.program_manager.infrastructure.crm_repositories import (
    ContactRepository,
    CrmTaskRepository,
    LeadRepository,
    MeetingRepository,
    NoteRepository,
    OpportunityRepository,
    OrganizationRepository,
    ProjectRepository,
)
from pb_api.agents.program_manager.infrastructure.planning_repository import PMPlanRepository
from pb_api.agents.program_manager.infrastructure.proposal_repository import ProposalRepository
from pb_api.agents.program_manager.infrastructure.run_repositories import (
    PMRunRepository,
    PMTaskRepository,
)
from pb_api.agents.program_manager.infrastructure.scheduling_repository import (
    ScheduledActionRepository,
)
from pb_api.cognitive.domain.goals import GoalLevel, GoalStatus
from pb_api.cognitive.services import CognitiveCore

# Deterministic intent keywords → goal. Order matters: the first matching group
# wins, so escalation and proposals take precedence over a generic reply.
_INTENT_KEYWORDS: tuple[tuple[PMGoalType, tuple[str, ...]], ...] = (
    (PMGoalType.ESCALATE_ISSUE, ("complaint", "unhappy", "refund", "angry", "escalate", "urgent")),
    (PMGoalType.CREATE_PROPOSAL, ("proposal", "quote", "pricing", "estimate", "sow")),
    (PMGoalType.BOOK_MEETING, ("meeting", "call", "demo", "schedule a", "book a")),
    (PMGoalType.FOLLOW_UP_LEAD, ("follow up", "following up", "checking in", "any update")),
)

# The next open stage in the pipeline (never auto-closes an opportunity).
_NEXT_OPEN_STAGE: dict[OpportunityStage, OpportunityStage] = {
    OpportunityStage.DISCOVERY: OpportunityStage.QUALIFICATION,
    OpportunityStage.QUALIFICATION: OpportunityStage.PROPOSAL,
    OpportunityStage.PROPOSAL: OpportunityStage.NEGOTIATION,
}


@dataclass(slots=True)
class RunContext:
    """The situational inputs a single lifecycle run reasons and acts over."""

    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    tier: PMAuthorityLevel
    trigger: PMTriggerType
    input_text: str = ""
    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    now: datetime = field(default_factory=utcnow)
    artifacts: dict[str, str] = field(default_factory=dict)


class ProgramManager:
    """Composition root + lifecycle orchestrator for the Program Manager."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: ProgramManagerSettings | None = None,
        core: CognitiveCore | None = None,
        personality: PersonalityProfile | None = None,
        style: CommunicationStyle | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_program_manager_settings()
        self.core = core or CognitiveCore(session)
        self.personality = personality or DEFAULT_PERSONALITY
        self.style = style or DEFAULT_COMMUNICATION_STYLE

        # Repositories.
        self._runs = PMRunRepository(session)
        self._tasks = PMTaskRepository(session)

        # Services.
        self.crm = CrmService(
            organizations=OrganizationRepository(session),
            contacts=ContactRepository(session),
            leads=LeadRepository(session),
            opportunities=OpportunityRepository(session),
            projects=ProjectRepository(session),
            meetings=MeetingRepository(session),
            tasks=CrmTaskRepository(session),
            notes=NoteRepository(session),
            events=self.core.events,
        )
        self.proposals = ProposalService(
            ProposalRepository(session), self.core.events, self.settings
        )
        self.scheduler = Scheduler(ScheduledActionRepository(session), self.core.events)
        self.followups = FollowUpEngine(self.scheduler, self.settings)
        self.planner = TaskPlanner(PMPlanRepository(session), self.core.events, self.settings)
        self.authority = AuthorityService(self.core.policies)

    # --- Bootstrap -----------------------------------------------------

    async def bootstrap(self, tenant_id: uuid.UUID) -> uuid.UUID:
        """Idempotently register the Program Manager and seed its governance.

        Registers the agent (carrying its mission and authority tier), seeds the
        default policy set, and seeds the Cognitive Core's default procedures.
        Returns the agent id. Safe to call repeatedly.
        """
        agent = await self.core.agents.register(
            tenant_id=tenant_id,
            name=self.settings.agent_name,
            role=self.settings.agent_role,
            default_authority=AuthorityService.to_cognitive(self.settings.default_authority),
            capabilities=["crm", "proposals", "scheduling", "communication"],
            metadata={
                "mission": self.personality.summary(),
                "pm_authority_level": int(self.settings.default_authority),
            },
        )
        await self.authority.seed_default_policies(tenant_id)
        await self.core.procedural.seed_defaults(tenant_id)
        return agent.id

    async def _resolve_agent(
        self, tenant_id: uuid.UUID, agent_id: uuid.UUID | None
    ) -> tuple[uuid.UUID, PMAuthorityLevel]:
        """Return the effective agent id and its authority tier, bootstrapping if needed."""
        if agent_id is not None:
            agent = await self.core.agents.get(tenant_id, agent_id)
        else:
            agent = await self.core.agents.get_by_name(tenant_id, self.settings.agent_name)
        if agent is None:
            resolved_id = await self.bootstrap(tenant_id)
            return resolved_id, self.settings.default_authority
        raw = agent.metadata.get("pm_authority_level")
        tier = (
            PMAuthorityLevel(int(raw)) if isinstance(raw, int) else self.settings.default_authority
        )
        return agent.id, tier

    # --- Lifecycle -----------------------------------------------------

    async def run_cycle(
        self,
        *,
        tenant_id: uuid.UUID,
        trigger: PMTriggerType = PMTriggerType.MANUAL,
        agent_id: uuid.UUID | None = None,
        input_text: str = "",
        organization_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        goal_type: PMGoalType | None = None,
        trigger_ref: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> PMRun:
        """Run one governed cognitive lifecycle pass and return its record."""
        resolved_agent_id, tier = await self._resolve_agent(tenant_id, agent_id)
        ctx = RunContext(
            tenant_id=tenant_id,
            agent_id=resolved_agent_id,
            tier=tier,
            trigger=trigger,
            input_text=input_text,
            organization_id=organization_id,
            contact_id=contact_id,
            lead_id=lead_id,
            opportunity_id=opportunity_id,
            project_id=project_id,
            now=now or utcnow(),
        )
        run = await self._runs.add(
            PMRun(
                tenant_id=tenant_id,
                agent_id=resolved_agent_id,
                trigger=trigger,
                trigger_ref=trigger_ref,
                input_summary=input_text[:500],
                organization_id=organization_id,
                state=PMState.IDLE,
                started_at=ctx.now,
            )
        )
        await self.core.events.record(
            event_type=PMEventType.RUN_STARTED,
            tenant_id=tenant_id,
            aggregate_id=run.id,
            actor=self.settings.agent_role,
            payload={"trigger": trigger.value},
        )
        try:
            return await self._drive(run, ctx, goal_type)
        except Exception as exc:
            run.state = PMState.ERROR
            run.success = False
            run.error = str(exc)
            run.ended_at = utcnow()
            self._visit(run, PMState.ERROR)
            await self._runs.update(run)
            await self.core.events.record(
                event_type=PMEventType.RUN_FAILED,
                tenant_id=tenant_id,
                aggregate_id=run.id,
                payload={"error": str(exc)},
            )
            return run

    async def _drive(self, run: PMRun, ctx: RunContext, goal_override: PMGoalType | None) -> PMRun:
        # OBSERVE.
        self._visit(run, PMState.OBSERVE)

        # UNDERSTAND.
        self._visit(run, PMState.UNDERSTAND)

        # RETRIEVE_MEMORY — recent episodic memory + the organization's scores.
        self._visit(run, PMState.RETRIEVE_MEMORY)
        recent = await self.core.episodic.recent(ctx.tenant_id, limit=10)
        run.metadata["recalled_memories"] = len(recent)
        if ctx.organization_id is not None:
            org = await self.crm.get_organization(ctx.tenant_id, ctx.organization_id)
            if org is not None:
                run.metadata["relationship_score"] = org.relationship_score
                await self.core.working_memory.remember(
                    ctx.tenant_id,
                    f"pm:run:{run.id}",
                    f"Organization {org.name}: relationship {org.relationship_score:.2f}, "
                    f"trust {org.trust_score:.2f}, importance {org.importance_score:.2f}.",
                    relevance=0.8,
                    source="crm",
                )

        # DETERMINE_GOAL.
        self._visit(run, PMState.DETERMINE_GOAL)
        goal_type = goal_override or self._determine_goal(ctx)
        objective = self._objective_for(goal_type, ctx)
        run.goal_type = goal_type
        cognitive_goal = await self.core.goals.create_goal(
            tenant_id=ctx.tenant_id,
            level=GoalLevel.AGENT,
            title=objective,
            owner_agent_id=ctx.agent_id,
        )
        await self.core.goals.set_status(ctx.tenant_id, cognitive_goal.id, GoalStatus.ACTIVE)
        run.goal_id = cognitive_goal.id
        await self.core.events.record(
            event_type=PMEventType.GOAL_DETERMINED,
            tenant_id=ctx.tenant_id,
            aggregate_id=run.id,
            payload={"goal_type": goal_type.value},
        )

        # BUILD_CONTEXT — assemble a dynamic prompt via the Cognitive Core.
        self._visit(run, PMState.BUILD_CONTEXT)
        prompt = await self.core.prompt_builder.build(
            tenant_id=ctx.tenant_id,
            agent_id=ctx.agent_id,
            task=objective,
            query=ctx.input_text or objective,
            token_budget=self.settings.reasoning_token_budget,
            output_requirements=self.style.guidance(),
        )
        run.metadata["context_tokens"] = prompt.token_estimate

        # REASON.
        self._visit(run, PMState.REASON)

        # PLAN.
        self._visit(run, PMState.PLAN)
        plan = await self.planner.build_plan(
            tenant_id=ctx.tenant_id,
            goal_type=goal_type,
            objective=objective,
            run_id=run.id,
            goal_id=cognitive_goal.id,
        )
        run.plan_id = plan.id

        # EXECUTE.
        self._visit(run, PMState.EXECUTE)
        awaiting, executed_results, success = await self._execute_plan(run, ctx, plan)

        # REFLECT.
        self._visit(run, PMState.REFLECT)
        outcome = (
            "Awaiting human approval to proceed."
            if awaiting
            else "; ".join(executed_results) or "No action required."
        )
        await self.core.reflection.reflect(
            tenant_id=ctx.tenant_id,
            agent_id=ctx.agent_id,
            objective=objective,
            outcome=outcome,
            success=success,
            lessons_learned=[] if success else ["A step required approval or was blocked."],
            future_recommendations=(
                ["Request the required authority up front."] if awaiting else []
            ),
        )

        # STORE_MEMORY — episodic record + relationship-score movement.
        self._visit(run, PMState.STORE_MEMORY)
        await self.core.episodic.record(
            tenant_id=ctx.tenant_id,
            actor=self.settings.agent_role,
            summary=f"{objective} — {outcome}",
            importance=0.6 if success else 0.5,
        )
        if ctx.organization_id is not None and goal_type is not PMGoalType.NO_ACTION:
            await self.crm.adjust_scores(
                ctx.tenant_id,
                ctx.organization_id,
                relationship_delta=0.02 if success else 0.0,
                trust_delta=0.01 if success else 0.0,
                reason=f"run:{run.id}",
            )

        # SCHEDULE_NEXT.
        self._visit(run, PMState.SCHEDULE_NEXT)
        if not awaiting:
            await self._maybe_schedule_followup(ctx, goal_type)

        # Finalise.
        if awaiting:
            run.state = PMState.AWAITING_APPROVAL
            run.awaiting_approval = True
            run.success = None
        else:
            self._visit(run, PMState.IDLE)
            run.state = PMState.IDLE
            run.success = success
        run.outcome = outcome
        run.ended_at = utcnow()
        await self._runs.update(run)
        await self.core.events.record(
            event_type=PMEventType.RUN_COMPLETED,
            tenant_id=ctx.tenant_id,
            aggregate_id=run.id,
            payload={"success": bool(success), "awaiting_approval": awaiting},
        )
        return run

    # --- Execution -----------------------------------------------------

    async def _execute_plan(
        self, run: PMRun, ctx: RunContext, plan: PMPlan
    ) -> tuple[bool, builtins.list[str], bool]:
        """Execute plan steps in order, gating each on authority.

        Returns ``(awaiting_approval, results, success)``. Stops at the first step
        that requires approval or is denied — the Program Manager never performs a
        partial outward action past its authority bound.
        """
        results: builtins.list[str] = []
        for step in plan.steps:
            decision = await self.authority.authorize(
                tenant_id=ctx.tenant_id,
                actor_level=ctx.tier,
                action=step.action,
                resource=step.resource,
            )
            if decision.allowed:
                result = await self._execute_step(ctx, step)
                await self._record_task(run, ctx, step, PMTaskStatus.COMPLETED, result=result)
                results.append(result)
                await self.core.events.record(
                    event_type=PMEventType.ACTION_EXECUTED,
                    tenant_id=ctx.tenant_id,
                    aggregate_id=run.id,
                    payload={"step": step.key, "action": step.action},
                )
                continue
            if decision.requires_approval:
                await self._record_task(
                    run,
                    ctx,
                    step,
                    PMTaskStatus.AWAITING_APPROVAL,
                    requires_approval=True,
                    result=decision.reason,
                )
                await self.core.events.record(
                    event_type=PMEventType.APPROVAL_REQUESTED,
                    tenant_id=ctx.tenant_id,
                    aggregate_id=run.id,
                    payload={"step": step.key, "action": step.action, "reason": decision.reason},
                )
                return True, results, False
            # Hard policy denial.
            await self._record_task(run, ctx, step, PMTaskStatus.FAILED, error=decision.reason)
            return False, results, False
        return False, results, True

    async def _record_task(
        self,
        run: PMRun,
        ctx: RunContext,
        step: PMPlanStep,
        status: PMTaskStatus,
        *,
        requires_approval: bool = False,
        result: str = "",
        error: str | None = None,
    ) -> PMTask:
        return await self._tasks.add(
            PMTask(
                tenant_id=ctx.tenant_id,
                run_id=run.id,
                step_key=step.key,
                goal_type=step.goal_type,
                objective=step.objective,
                status=status,
                authority_required=step.authority_required,
                requires_approval=requires_approval,
                result=result,
                error=error,
            )
        )

    async def _execute_step(self, ctx: RunContext, step: PMPlanStep) -> str:
        """Perform a single plan step's real, persisted effect.

        Outward-transport actions (sending a message, booking externally) record
        the prepared artifact and emit the event; the transmission itself is a
        channel port fulfilled by a future adapter — no vendor is assumed here.
        """
        action = step.action
        if action == "crm.read":
            return await self._read_context(ctx)
        if action == "communication.send":
            return await self._prepare_message(ctx)
        if action == "schedule.create":
            scheduled = await self._maybe_schedule_followup(ctx, PMGoalType.FOLLOW_UP_LEAD)
            return f"Scheduled follow-up {scheduled.id}" if scheduled else "No subject to follow up"
        if action == "meeting.book":
            return await self._book_meeting(ctx)
        if action == "opportunity.advance":
            return await self._advance_opportunity(ctx)
        if action == "proposal.draft":
            return await self._draft_proposal(ctx)
        if action == "proposal.send":
            return await self._send_proposal(ctx)
        if action == "crm.update":
            return await self._update_crm(ctx)
        if action == "task.create":
            return await self._create_task(ctx, step.objective)
        if action == "issue.escalate":
            return await self._escalate(ctx)
        # Unknown actions are recorded as a note rather than silently ignored.
        return await self._create_note(ctx, f"Executed {action}: {step.objective}")

    async def _read_context(self, ctx: RunContext) -> str:
        if ctx.organization_id is None:
            return "No organization in context"
        org = await self.crm.get_organization(ctx.tenant_id, ctx.organization_id)
        if org is None:
            return "Organization not found"
        notes = await self.crm.list_notes(ctx.tenant_id, organization_id=ctx.organization_id)
        return f"Loaded {org.name} with {len(notes)} note(s)"

    async def _prepare_message(self, ctx: RunContext) -> str:
        message = self._draft_message(ctx)
        note = await self.crm.record_note(
            tenant_id=ctx.tenant_id,
            author=self.settings.agent_role,
            body=f"[outbound draft] {message}",
            organization_id=ctx.organization_id,
            contact_id=ctx.contact_id,
        )
        ctx.artifacts["message_note_id"] = str(note.id)
        return "Reply prepared and recorded (delivery via channel port)"

    async def _book_meeting(self, ctx: RunContext) -> str:
        if ctx.organization_id is None:
            return "No organization to book a meeting with"
        meeting = await self.crm.schedule_meeting(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            title="Introductory call",
            scheduled_at=ctx.now + timedelta(days=2),
            contact_ids=[ctx.contact_id] if ctx.contact_id else None,
            agenda="Discovery and next steps",
            opportunity_id=ctx.opportunity_id,
        )
        return f"Meeting {meeting.id} scheduled"

    async def _advance_opportunity(self, ctx: RunContext) -> str:
        if ctx.opportunity_id is None:
            return "No opportunity to advance"
        opportunity = await self.crm.get_opportunity(ctx.tenant_id, ctx.opportunity_id)
        if opportunity is None:
            return "Opportunity not found"
        nxt = _NEXT_OPEN_STAGE.get(opportunity.stage)
        if nxt is None:
            return f"Opportunity already at {opportunity.stage.value}"
        await self.crm.advance_opportunity(ctx.tenant_id, ctx.opportunity_id, stage=nxt)
        return f"Opportunity advanced to {nxt.value}"

    async def _draft_proposal(self, ctx: RunContext) -> str:
        if ctx.organization_id is None:
            return "No organization for a proposal"
        opportunity = (
            await self.crm.get_opportunity(ctx.tenant_id, ctx.opportunity_id)
            if ctx.opportunity_id
            else None
        )
        value = opportunity.amount if opportunity is not None else 0.0
        proposal = await self.proposals.draft_proposal(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            title=f"Proposal for {opportunity.name if opportunity else 'engagement'}",
            opportunity_id=ctx.opportunity_id,
            total_value=value,
            owner_agent_id=ctx.agent_id,
        )
        ctx.artifacts["proposal_id"] = str(proposal.id)
        return f"Proposal {proposal.id} drafted ({len(proposal.sections)} sections)"

    async def _send_proposal(self, ctx: RunContext) -> str:
        proposal_id = ctx.artifacts.get("proposal_id")
        if proposal_id is None:
            return "No proposal prepared to send"
        return f"Proposal {proposal_id} prepared; awaiting readiness before delivery"

    async def _update_crm(self, ctx: RunContext) -> str:
        if ctx.lead_id is not None:
            lead = await self.crm.get_lead(ctx.tenant_id, ctx.lead_id)
            if lead is not None:
                await self.crm.qualify_lead(ctx.tenant_id, ctx.lead_id)
                return f"Lead {ctx.lead_id} qualified"
        return await self._create_note(ctx, "CRM reviewed and updated")

    async def _create_task(self, ctx: RunContext, objective: str) -> str:
        task = await self.crm.create_task(
            tenant_id=ctx.tenant_id,
            title=objective,
            organization_id=ctx.organization_id,
            opportunity_id=ctx.opportunity_id,
            project_id=ctx.project_id,
            owner_agent_id=ctx.agent_id,
        )
        return f"Task {task.id} created"

    async def _escalate(self, ctx: RunContext) -> str:
        await self.crm.record_note(
            tenant_id=ctx.tenant_id,
            author=self.settings.agent_role,
            body=f"[ESCALATION] {ctx.input_text or 'Issue requires human attention.'}",
            organization_id=ctx.organization_id,
        )
        task = await self.crm.create_task(
            tenant_id=ctx.tenant_id,
            title="Review escalated issue",
            description=ctx.input_text,
            priority=1,
            organization_id=ctx.organization_id,
        )
        return f"Escalated to human via task {task.id}"

    async def _create_note(self, ctx: RunContext, body: str) -> str:
        note = await self.crm.record_note(
            tenant_id=ctx.tenant_id,
            author=self.settings.agent_role,
            body=body,
            organization_id=ctx.organization_id,
        )
        return f"Note {note.id} recorded"

    async def _maybe_schedule_followup(
        self, ctx: RunContext, goal_type: PMGoalType
    ) -> ScheduledAction | None:
        """Schedule a follow-up when there is a concrete subject to chase."""
        subject_type, subject_id = self._subject(ctx)
        if subject_id is None or subject_type is None:
            return None
        return await self.followups.schedule_followup(
            tenant_id=ctx.tenant_id,
            subject_type=subject_type,
            subject_id=subject_id,
            cadence=FollowUpCadence.SECOND_TOUCH,
            goal_type=PMGoalType.FOLLOW_UP_LEAD,
            created_by_agent_id=ctx.agent_id,
            now=ctx.now,
        )

    # --- Scheduled execution & approvals -------------------------------

    async def execute_due(
        self, tenant_id: uuid.UUID, *, now: datetime | None = None, limit: int = 50
    ) -> builtins.list[PMRun]:
        """Run a lifecycle pass for every scheduled action that is due."""
        moment = now or utcnow()
        due = await self.scheduler.due(tenant_id, now=moment, limit=limit)
        runs: builtins.list[PMRun] = []
        for action in due:
            run = await self.run_cycle(
                tenant_id=tenant_id,
                trigger=PMTriggerType.SCHEDULED_ACTION,
                goal_type=action.goal_type,
                organization_id=self._subject_org(action),
                lead_id=action.subject_id if action.subject_type is SubjectType.LEAD else None,
                opportunity_id=(
                    action.subject_id if action.subject_type is SubjectType.OPPORTUNITY else None
                ),
                trigger_ref=action.id,
                now=moment,
            )
            if run.state is PMState.ERROR:
                await self.scheduler.mark_failed(
                    tenant_id, action.id, error=run.error or "run failed"
                )
            else:
                await self.scheduler.mark_executed(tenant_id, action.id, now=moment)
            runs.append(run)
        return runs

    async def approve_task(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID, *, approver: str
    ) -> PMTask | None:
        """Approve a task that was awaiting approval and mark it completed.

        Approval records the decision and closes the task; the approved action is
        then re-driven on the next run for its subject. Emits an approval event so
        the grant is auditable.
        """
        task = await self._tasks.get(tenant_id, task_id)
        if task is None:
            return None
        if task.status is not PMTaskStatus.AWAITING_APPROVAL:
            return task
        task.status = PMTaskStatus.COMPLETED
        task.approved_by = approver
        task.result = f"Approved by {approver}"
        updated = await self._tasks.update(task)
        if updated is not None and updated.run_id is not None:
            run = await self._runs.get(tenant_id, updated.run_id)
            if run is not None and run.awaiting_approval:
                run.awaiting_approval = False
                await self._runs.update(run)
        await self.core.events.record(
            event_type=PMEventType.APPROVAL_GRANTED,
            tenant_id=tenant_id,
            aggregate_id=task_id,
            payload={"approver": approver},
        )
        return updated

    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        status: PMTaskStatus | None = None,
    ) -> builtins.list[PMTask]:
        return await self._tasks.list(tenant_id, run_id=run_id, status=status)

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> PMRun | None:
        return await self._runs.get(tenant_id, run_id)

    async def list_runs(
        self, tenant_id: uuid.UUID, *, awaiting_approval: bool | None = None
    ) -> builtins.list[PMRun]:
        return await self._runs.list(tenant_id, awaiting_approval=awaiting_approval)

    # --- Reasoning helpers ---------------------------------------------

    def _determine_goal(self, ctx: RunContext) -> PMGoalType:
        text = ctx.input_text.lower()
        if text:
            for goal, keywords in _INTENT_KEYWORDS:
                if any(keyword in text for keyword in keywords):
                    return goal
        if ctx.opportunity_id is not None:
            return PMGoalType.ADVANCE_OPPORTUNITY
        if ctx.lead_id is not None:
            return PMGoalType.QUALIFY_LEAD
        if ctx.project_id is not None:
            return PMGoalType.COORDINATE_PROJECT
        if text:
            return PMGoalType.REPLY_TO_CUSTOMER
        return PMGoalType.NO_ACTION

    def _objective_for(self, goal_type: PMGoalType, ctx: RunContext) -> str:
        objectives = {
            PMGoalType.REPLY_TO_CUSTOMER: "Reply to the customer's message",
            PMGoalType.QUALIFY_LEAD: "Qualify the lead",
            PMGoalType.FOLLOW_UP_LEAD: "Follow up with the lead",
            PMGoalType.BOOK_MEETING: "Book a meeting with the customer",
            PMGoalType.ADVANCE_OPPORTUNITY: "Advance the opportunity",
            PMGoalType.CREATE_PROPOSAL: "Prepare a proposal",
            PMGoalType.UPDATE_CRM: "Update the CRM record",
            PMGoalType.COORDINATE_PROJECT: "Coordinate the project",
            PMGoalType.ESCALATE_ISSUE: "Escalate the issue to a human",
            PMGoalType.REQUEST_APPROVAL: "Request human approval",
            PMGoalType.NO_ACTION: "Observe; no action required",
        }
        return objectives[goal_type]

    def _draft_message(self, ctx: RunContext) -> str:
        opener = "Hello" if not self.style.greeting_by_name else "Hi there"
        return (
            f"{opener}, thank you for reaching out. I've reviewed your note and want to make "
            "sure we move this forward quickly. Here is what I propose as the next step, and "
            "I'll take care of the details from here."
        )

    @staticmethod
    def _subject(ctx: RunContext) -> tuple[SubjectType | None, uuid.UUID | None]:
        if ctx.opportunity_id is not None:
            return SubjectType.OPPORTUNITY, ctx.opportunity_id
        if ctx.lead_id is not None:
            return SubjectType.LEAD, ctx.lead_id
        if ctx.organization_id is not None:
            return SubjectType.ORGANIZATION, ctx.organization_id
        return None, None

    @staticmethod
    def _subject_org(action: ScheduledAction) -> uuid.UUID | None:
        return action.subject_id if action.subject_type is SubjectType.ORGANIZATION else None

    @staticmethod
    def _visit(run: PMRun, state: PMState) -> None:
        run.state = state
        run.states_visited.append(state.value)
