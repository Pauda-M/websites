"""Task planner — decomposes a determined goal into an authority-aware plan.

The planner is deterministic and dependency-free: each goal type has a canonical
decomposition into ordered :class:`PMPlanStep` s, every step declaring its
objective, dependencies, required tools, risk, expected outcome, fallback, and
the authority it needs. This mirrors the Cognitive Core's deterministic planning
and ranking — a real, testable implementation that a learned planner can later
augment without changing the contract. The produced plan is persisted so every
autonomous action is traceable to the step that authorised it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from pb_api.agents.program_manager.config import ProgramManagerSettings
from pb_api.agents.program_manager.domain.common import PMAuthorityLevel, PMGoalType, RiskLevel
from pb_api.agents.program_manager.domain.events import PMEventType
from pb_api.agents.program_manager.domain.plan import PMPlan, PMPlanStep
from pb_api.agents.program_manager.infrastructure.planning_repository import PMPlanRepository
from pb_api.cognitive.services.event_processor import EventProcessor


@dataclass(frozen=True, slots=True)
class _StepTemplate:
    key: str
    objective: str
    action: str
    authority_required: PMAuthorityLevel
    risk: RiskLevel
    expected_outcome: str
    fallback: str
    required_tools: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()


# Canonical decompositions. Keys are stable within a plan so ``depends_on`` can
# reference earlier steps. Read-only steps are L0; reversible internal actions are
# L1; outward-facing/committing actions are L2 and will escalate to approval when
# the Program Manager's tier is below them.
_PLAN_TEMPLATES: dict[PMGoalType, tuple[_StepTemplate, ...]] = {
    PMGoalType.REPLY_TO_CUSTOMER: (
        _StepTemplate(
            "gather",
            "Retrieve the customer's context and history",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "Relevant CRM records and memory are loaded",
            "Proceed with partial context and flag gaps",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "draft",
            "Draft a reply in the Program Manager's voice",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "A concise, on-brand reply is drafted",
            "Escalate to a human if intent is unclear",
            depends_on=("gather",),
        ),
        _StepTemplate(
            "send",
            "Send the reply to the customer",
            "communication.send",
            PMAuthorityLevel.ACT_BOUNDED,
            RiskLevel.MEDIUM,
            "The customer receives a timely reply",
            "Queue the draft for human approval",
            required_tools=("email",),
            depends_on=("draft",),
        ),
    ),
    PMGoalType.QUALIFY_LEAD: (
        _StepTemplate(
            "review",
            "Review the lead and its signals",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "The lead's fit and intent are assessed",
            "Request more information",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "score",
            "Score and mark the lead qualified/unqualified",
            "crm.update",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.LOW,
            "The lead's status and score are updated",
            "Leave status unchanged and add a note",
            required_tools=("crm",),
            depends_on=("review",),
        ),
    ),
    PMGoalType.FOLLOW_UP_LEAD: (
        _StepTemplate(
            "assess",
            "Assess where the lead stands",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "The right follow-up angle is chosen",
            "Default to a gentle check-in",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "reach_out",
            "Send a follow-up message",
            "communication.send",
            PMAuthorityLevel.ACT_BOUNDED,
            RiskLevel.MEDIUM,
            "The lead is re-engaged",
            "Queue the message for approval",
            required_tools=("email",),
            depends_on=("assess",),
        ),
        _StepTemplate(
            "reschedule",
            "Schedule the next follow-up touch",
            "schedule.create",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.LOW,
            "A next follow-up is queued at the right cadence",
            "Skip and revisit next cycle",
            depends_on=("reach_out",),
        ),
    ),
    PMGoalType.BOOK_MEETING: (
        _StepTemplate(
            "propose",
            "Determine suitable meeting times",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "Candidate times are identified",
            "Ask the customer for availability",
            required_tools=("calendar",),
        ),
        _StepTemplate(
            "book",
            "Book the meeting",
            "meeting.book",
            PMAuthorityLevel.ACT_BOUNDED,
            RiskLevel.MEDIUM,
            "A meeting is scheduled and confirmed",
            "Propose times and await confirmation",
            required_tools=("calendar",),
            depends_on=("propose",),
        ),
    ),
    PMGoalType.ADVANCE_OPPORTUNITY: (
        _StepTemplate(
            "review",
            "Review the opportunity's stage and signals",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "The next stage is justified",
            "Hold the opportunity and add a note",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "advance",
            "Advance the opportunity to the next stage",
            "opportunity.advance",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.MEDIUM,
            "The opportunity moves forward",
            "Request approval for the stage change",
            required_tools=("crm",),
            depends_on=("review",),
        ),
    ),
    PMGoalType.CREATE_PROPOSAL: (
        _StepTemplate(
            "requirements",
            "Gather requirements and scope",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "Requirements are understood",
            "Book a discovery call",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "draft",
            "Draft the eleven-section proposal",
            "proposal.draft",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.MEDIUM,
            "A complete proposal draft exists",
            "Draft partially and flag open sections",
            depends_on=("requirements",),
        ),
        _StepTemplate(
            "deliver",
            "Send the proposal once ready",
            "proposal.send",
            PMAuthorityLevel.ACT_BOUNDED,
            RiskLevel.HIGH,
            "The customer receives the proposal",
            "Route to a human for approval and send",
            required_tools=("email",),
            depends_on=("draft",),
        ),
    ),
    PMGoalType.UPDATE_CRM: (
        _StepTemplate(
            "update",
            "Update the CRM record",
            "crm.update",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.LOW,
            "The CRM reflects the new information",
            "Record a note instead",
            required_tools=("crm",),
        ),
    ),
    PMGoalType.COORDINATE_PROJECT: (
        _StepTemplate(
            "review",
            "Review project status and health",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "Project risks are identified",
            "Request a status update",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "act",
            "Update health and create coordination tasks",
            "task.create",
            PMAuthorityLevel.ACT_WITH_APPROVAL,
            RiskLevel.LOW,
            "Follow-up tasks are created",
            "Add a note for the delivery owner",
            required_tools=("crm",),
            depends_on=("review",),
        ),
    ),
    PMGoalType.ESCALATE_ISSUE: (
        _StepTemplate(
            "assess",
            "Assess the issue and its severity",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "The issue is characterised",
            "Escalate immediately if severity is unclear",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "escalate",
            "Escalate the issue to a human owner",
            "issue.escalate",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "A human owner is notified",
            "Record the escalation as a note",
            depends_on=("assess",),
        ),
    ),
    PMGoalType.REQUEST_APPROVAL: (
        _StepTemplate(
            "prepare",
            "Prepare the approval request with context",
            "crm.read",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "The request is ready for a human",
            "Escalate without full context",
            required_tools=("crm",),
        ),
        _StepTemplate(
            "request",
            "Submit the approval request",
            "issue.escalate",
            PMAuthorityLevel.OBSERVE_ONLY,
            RiskLevel.LOW,
            "A human is asked to decide",
            "Record the pending decision as a note",
            depends_on=("prepare",),
        ),
    ),
    PMGoalType.NO_ACTION: (),
}


@dataclass(slots=True)
class TaskPlanner:
    """Builds and persists a structured plan for a determined goal."""

    plans: PMPlanRepository
    events: EventProcessor
    settings: ProgramManagerSettings
    _templates: dict[PMGoalType, tuple[_StepTemplate, ...]] = field(
        default_factory=lambda: _PLAN_TEMPLATES, init=False
    )

    async def build_plan(
        self,
        *,
        tenant_id: uuid.UUID,
        goal_type: PMGoalType,
        objective: str,
        run_id: uuid.UUID | None = None,
        goal_id: uuid.UUID | None = None,
    ) -> PMPlan:
        templates = self._templates.get(goal_type, ())[: self.settings.max_plan_steps]
        steps = [
            PMPlanStep(
                key=template.key,
                objective=template.objective,
                goal_type=goal_type,
                depends_on=list(template.depends_on),
                required_tools=list(template.required_tools),
                risk=template.risk,
                expected_outcome=template.expected_outcome,
                fallback=template.fallback,
                authority_required=template.authority_required,
                action=template.action,
            )
            for template in templates
        ]
        plan = await self.plans.add(
            PMPlan(
                tenant_id=tenant_id,
                run_id=run_id,
                goal_id=goal_id,
                goal_type=goal_type,
                objective=objective,
                steps=steps,
            )
        )
        await self.events.record(
            event_type=PMEventType.PLAN_CREATED,
            tenant_id=tenant_id,
            aggregate_id=plan.id,
            payload={"goal_type": goal_type.value, "steps": len(steps)},
        )
        return plan
