"""Program Manager domain events.

Reuses the Cognitive Core's immutable :class:`CognitiveEvent` envelope and its
append-only Event Processor as the single write path — the Program Manager never
builds a second event store. This module only declares the Program Manager's own
event *type* constants, following the canonical Genesis pattern
``pb.<context>.<aggregate>.<past-verb>`` (`docs/genesis/005_Event_Model.md`). The
contexts ``crm``, ``proposal``, and ``pm`` correspond to reserved module
namespaces in the platform module registry.
"""

from __future__ import annotations


class PMEventType:
    """Canonical Program Manager event type constants."""

    # --- CRM context ---------------------------------------------------
    ORGANIZATION_CREATED = "pb.crm.organization.created"
    ORGANIZATION_UPDATED = "pb.crm.organization.updated"
    ORGANIZATION_SCORED = "pb.crm.organization.scored"
    CONTACT_CREATED = "pb.crm.contact.created"
    CONTACT_UPDATED = "pb.crm.contact.updated"
    LEAD_CREATED = "pb.crm.lead.created"
    LEAD_QUALIFIED = "pb.crm.lead.qualified"
    LEAD_CONVERTED = "pb.crm.lead.converted"
    OPPORTUNITY_CREATED = "pb.crm.opportunity.created"
    OPPORTUNITY_ADVANCED = "pb.crm.opportunity.advanced"
    OPPORTUNITY_WON = "pb.crm.opportunity.won"
    OPPORTUNITY_LOST = "pb.crm.opportunity.lost"
    PROJECT_CREATED = "pb.crm.project.created"
    PROJECT_UPDATED = "pb.crm.project.updated"
    MEETING_SCHEDULED = "pb.crm.meeting.scheduled"
    MEETING_COMPLETED = "pb.crm.meeting.completed"
    TASK_CREATED = "pb.crm.task.created"
    TASK_COMPLETED = "pb.crm.task.completed"
    NOTE_RECORDED = "pb.crm.note.recorded"

    # --- Proposal context ---------------------------------------------
    PROPOSAL_DRAFTED = "pb.proposal.draft.created"
    PROPOSAL_SECTION_UPDATED = "pb.proposal.section.updated"
    PROPOSAL_READY = "pb.proposal.ready"
    PROPOSAL_SENT = "pb.proposal.sent"
    PROPOSAL_ACCEPTED = "pb.proposal.accepted"
    PROPOSAL_REJECTED = "pb.proposal.rejected"

    # --- Program Manager lifecycle context -----------------------------
    RUN_STARTED = "pb.pm.run.started"
    GOAL_DETERMINED = "pb.pm.goal.determined"
    PLAN_CREATED = "pb.pm.plan.created"
    ACTION_EXECUTED = "pb.pm.action.executed"
    APPROVAL_REQUESTED = "pb.pm.action.approval_requested"
    APPROVAL_GRANTED = "pb.pm.action.approval_granted"
    RUN_COMPLETED = "pb.pm.run.completed"
    RUN_FAILED = "pb.pm.run.failed"

    # --- Scheduling context -------------------------------------------
    ACTION_SCHEDULED = "pb.pm.schedule.created"
    ACTION_DUE_EXECUTED = "pb.pm.schedule.executed"
    ACTION_CANCELLED = "pb.pm.schedule.cancelled"
