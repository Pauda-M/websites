"""CRM service — the Program Manager's operations over the CRM graph.

Owns creation and mutation of Organizations, Contacts, Leads, Opportunities,
Projects, Meetings, Tasks, and Notes, and maintains the three organizational
relationship scores. Every consequential mutation is recorded as an immutable
event through the Cognitive Core's Event Processor, so the CRM's history is fully
reconstructable. Business rules that matter (lead conversion, opportunity
advancement, score clamping) live here — not in the repositories, which are pure
persistence.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from pb_api.agents.program_manager.domain.crm import (
    Contact,
    ContactRole,
    CrmTask,
    CrmTaskStatus,
    Lead,
    LeadSource,
    LeadStatus,
    Meeting,
    MeetingStatus,
    Note,
    Opportunity,
    OpportunityStage,
    Organization,
    OrganizationStatus,
    Project,
    ProjectHealth,
    ProjectStatus,
)
from pb_api.agents.program_manager.domain.events import PMEventType
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
from pb_api.cognitive.services.event_processor import EventProcessor


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class CrmService:
    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        contacts: ContactRepository,
        leads: LeadRepository,
        opportunities: OpportunityRepository,
        projects: ProjectRepository,
        meetings: MeetingRepository,
        tasks: CrmTaskRepository,
        notes: NoteRepository,
        events: EventProcessor,
    ) -> None:
        self._orgs = organizations
        self._contacts = contacts
        self._leads = leads
        self._opps = opportunities
        self._projects = projects
        self._meetings = meetings
        self._tasks = tasks
        self._notes = notes
        self._events = events

    # --- Organizations -------------------------------------------------

    async def create_organization(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        domain: str | None = None,
        industry: str | None = None,
        size: str | None = None,
        importance_score: float = 0.5,
    ) -> Organization:
        org = await self._orgs.add(
            Organization(
                tenant_id=tenant_id,
                name=name,
                domain=domain,
                industry=industry,
                size=size,
                importance_score=_clamp(importance_score),
            )
        )
        await self._events.record(
            event_type=PMEventType.ORGANIZATION_CREATED,
            tenant_id=tenant_id,
            aggregate_id=org.id,
            payload={"name": name},
        )
        return org

    async def get_organization(
        self, tenant_id: uuid.UUID, org_id: uuid.UUID
    ) -> Organization | None:
        return await self._orgs.get(tenant_id, org_id)

    async def list_organizations(
        self, tenant_id: uuid.UUID, *, status: OrganizationStatus | None = None
    ) -> builtins.list[Organization]:
        return await self._orgs.list(tenant_id, status=status)

    async def set_organization_status(
        self, tenant_id: uuid.UUID, org_id: uuid.UUID, status: OrganizationStatus
    ) -> Organization | None:
        org = await self._orgs.get(tenant_id, org_id)
        if org is None:
            return None
        org.status = status
        updated = await self._orgs.update(org)
        await self._events.record(
            event_type=PMEventType.ORGANIZATION_UPDATED,
            tenant_id=tenant_id,
            aggregate_id=org_id,
            payload={"status": status.value},
        )
        return updated

    async def adjust_scores(
        self,
        tenant_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        relationship_delta: float = 0.0,
        trust_delta: float = 0.0,
        importance_delta: float = 0.0,
        reason: str = "",
    ) -> Organization | None:
        """Apply bounded deltas to an organization's relationship scores.

        Scores are the Program Manager's durable read on a relationship; they move
        in small increments as interactions succeed or stall, and are always
        clamped to [0, 1].
        """
        org = await self._orgs.get(tenant_id, org_id)
        if org is None:
            return None
        org.relationship_score = _clamp(org.relationship_score + relationship_delta)
        org.trust_score = _clamp(org.trust_score + trust_delta)
        org.importance_score = _clamp(org.importance_score + importance_delta)
        updated = await self._orgs.update(org)
        await self._events.record(
            event_type=PMEventType.ORGANIZATION_SCORED,
            tenant_id=tenant_id,
            aggregate_id=org_id,
            payload={
                "relationship": org.relationship_score,
                "trust": org.trust_score,
                "importance": org.importance_score,
                "reason": reason,
            },
        )
        return updated

    # --- Contacts ------------------------------------------------------

    async def create_contact(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        first_name: str,
        last_name: str = "",
        email: str | None = None,
        phone: str | None = None,
        title: str | None = None,
        role: ContactRole = ContactRole.UNKNOWN,
        is_primary: bool = False,
    ) -> Contact:
        contact = await self._contacts.add(
            Contact(
                tenant_id=tenant_id,
                organization_id=organization_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                title=title,
                role=role,
                is_primary=is_primary,
            )
        )
        await self._events.record(
            event_type=PMEventType.CONTACT_CREATED,
            tenant_id=tenant_id,
            aggregate_id=contact.id,
            payload={"organization_id": str(organization_id), "name": contact.full_name},
        )
        return contact

    async def get_contact(self, tenant_id: uuid.UUID, contact_id: uuid.UUID) -> Contact | None:
        return await self._contacts.get(tenant_id, contact_id)

    async def list_contacts(
        self, tenant_id: uuid.UUID, *, organization_id: uuid.UUID | None = None
    ) -> builtins.list[Contact]:
        return await self._contacts.list(tenant_id, organization_id=organization_id)

    # --- Leads ---------------------------------------------------------

    async def create_lead(
        self,
        *,
        tenant_id: uuid.UUID,
        source: LeadSource = LeadSource.UNKNOWN,
        organization_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        summary: str = "",
        score: float = 0.0,
        owner_agent_id: uuid.UUID | None = None,
    ) -> Lead:
        lead = await self._leads.add(
            Lead(
                tenant_id=tenant_id,
                source=source,
                organization_id=organization_id,
                contact_id=contact_id,
                summary=summary,
                score=_clamp(score),
                owner_agent_id=owner_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.LEAD_CREATED,
            tenant_id=tenant_id,
            aggregate_id=lead.id,
            payload={"source": source.value},
        )
        return lead

    async def get_lead(self, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        return await self._leads.get(tenant_id, lead_id)

    async def list_leads(
        self,
        tenant_id: uuid.UUID,
        *,
        status: LeadStatus | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> builtins.list[Lead]:
        return await self._leads.list(tenant_id, status=status, organization_id=organization_id)

    async def qualify_lead(
        self, tenant_id: uuid.UUID, lead_id: uuid.UUID, *, score: float | None = None
    ) -> Lead | None:
        lead = await self._leads.get(tenant_id, lead_id)
        if lead is None:
            return None
        lead.status = LeadStatus.QUALIFIED
        if score is not None:
            lead.score = _clamp(score)
        updated = await self._leads.update(lead)
        await self._events.record(
            event_type=PMEventType.LEAD_QUALIFIED,
            tenant_id=tenant_id,
            aggregate_id=lead_id,
            payload={"score": lead.score},
        )
        return updated

    async def convert_lead(
        self,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        name: str,
        amount: float = 0.0,
        currency: str = "EUR",
    ) -> Opportunity:
        """Convert a lead into an Opportunity.

        Requires the lead to reference an organization; marks the lead converted
        and back-links the created opportunity so the funnel stays traceable.
        """
        lead = await self._leads.get(tenant_id, lead_id)
        if lead is None:
            raise ValueError("lead not found")
        if lead.status is LeadStatus.CONVERTED:
            raise ValueError("lead already converted")
        if lead.organization_id is None:
            raise ValueError("lead has no organization to convert into an opportunity")
        opportunity = await self._opps.add(
            Opportunity(
                tenant_id=tenant_id,
                organization_id=lead.organization_id,
                name=name,
                amount=max(0.0, amount),
                currency=currency,
                primary_contact_id=lead.contact_id,
                lead_id=lead.id,
                owner_agent_id=lead.owner_agent_id,
            )
        )
        lead.status = LeadStatus.CONVERTED
        lead.opportunity_id = opportunity.id
        await self._leads.update(lead)
        await self._events.record(
            event_type=PMEventType.LEAD_CONVERTED,
            tenant_id=tenant_id,
            aggregate_id=lead.id,
            payload={"opportunity_id": str(opportunity.id)},
        )
        await self._events.record(
            event_type=PMEventType.OPPORTUNITY_CREATED,
            tenant_id=tenant_id,
            aggregate_id=opportunity.id,
            payload={"name": name, "amount": opportunity.amount},
        )
        return opportunity

    # --- Opportunities -------------------------------------------------

    async def create_opportunity(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        name: str,
        amount: float = 0.0,
        currency: str = "EUR",
        primary_contact_id: uuid.UUID | None = None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> Opportunity:
        opportunity = await self._opps.add(
            Opportunity(
                tenant_id=tenant_id,
                organization_id=organization_id,
                name=name,
                amount=max(0.0, amount),
                currency=currency,
                primary_contact_id=primary_contact_id,
                owner_agent_id=owner_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.OPPORTUNITY_CREATED,
            tenant_id=tenant_id,
            aggregate_id=opportunity.id,
            payload={"name": name, "amount": opportunity.amount},
        )
        return opportunity

    async def get_opportunity(
        self, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
    ) -> Opportunity | None:
        return await self._opps.get(tenant_id, opportunity_id)

    async def list_opportunities(
        self,
        tenant_id: uuid.UUID,
        *,
        stage: OpportunityStage | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> builtins.list[Opportunity]:
        return await self._opps.list(tenant_id, stage=stage, organization_id=organization_id)

    async def advance_opportunity(
        self, tenant_id: uuid.UUID, opportunity_id: uuid.UUID, *, stage: OpportunityStage
    ) -> Opportunity | None:
        """Move an opportunity to a new stage and emit the appropriate event."""
        opportunity = await self._opps.get(tenant_id, opportunity_id)
        if opportunity is None:
            return None
        previous = opportunity.stage
        opportunity.stage = stage
        if stage is OpportunityStage.CLOSED_WON:
            opportunity.probability = 1.0
        elif stage is OpportunityStage.CLOSED_LOST:
            opportunity.probability = 0.0
        updated = await self._opps.update(opportunity)
        event_type = {
            OpportunityStage.CLOSED_WON: PMEventType.OPPORTUNITY_WON,
            OpportunityStage.CLOSED_LOST: PMEventType.OPPORTUNITY_LOST,
        }.get(stage, PMEventType.OPPORTUNITY_ADVANCED)
        await self._events.record(
            event_type=event_type,
            tenant_id=tenant_id,
            aggregate_id=opportunity_id,
            payload={"from": previous.value, "to": stage.value},
        )
        return updated

    # --- Projects ------------------------------------------------------

    async def create_project(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        name: str,
        opportunity_id: uuid.UUID | None = None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> Project:
        project = await self._projects.add(
            Project(
                tenant_id=tenant_id,
                organization_id=organization_id,
                name=name,
                opportunity_id=opportunity_id,
                owner_agent_id=owner_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.PROJECT_CREATED,
            tenant_id=tenant_id,
            aggregate_id=project.id,
            payload={"name": name},
        )
        return project

    async def get_project(self, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project | None:
        return await self._projects.get(tenant_id, project_id)

    async def list_projects(
        self,
        tenant_id: uuid.UUID,
        *,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> builtins.list[Project]:
        return await self._projects.list(tenant_id, status=status, organization_id=organization_id)

    async def update_project_health(
        self,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        status: ProjectStatus | None = None,
        health: ProjectHealth | None = None,
    ) -> Project | None:
        project = await self._projects.get(tenant_id, project_id)
        if project is None:
            return None
        if status is not None:
            project.status = status
        if health is not None:
            project.health = health
        updated = await self._projects.update(project)
        await self._events.record(
            event_type=PMEventType.PROJECT_UPDATED,
            tenant_id=tenant_id,
            aggregate_id=project_id,
            payload={"status": project.status.value, "health": project.health.value},
        )
        return updated

    # --- Meetings ------------------------------------------------------

    async def schedule_meeting(
        self,
        *,
        tenant_id: uuid.UUID,
        organization_id: uuid.UUID,
        title: str,
        scheduled_at: datetime,
        duration_minutes: int = 30,
        contact_ids: builtins.list[uuid.UUID] | None = None,
        agenda: str = "",
        location: str | None = None,
        opportunity_id: uuid.UUID | None = None,
    ) -> Meeting:
        meeting = await self._meetings.add(
            Meeting(
                tenant_id=tenant_id,
                organization_id=organization_id,
                title=title,
                scheduled_at=scheduled_at,
                duration_minutes=duration_minutes,
                status=MeetingStatus.SCHEDULED,
                contact_ids=contact_ids or [],
                agenda=agenda,
                location=location,
                opportunity_id=opportunity_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.MEETING_SCHEDULED,
            tenant_id=tenant_id,
            aggregate_id=meeting.id,
            payload={"title": title, "scheduled_at": scheduled_at.isoformat()},
        )
        return meeting

    async def get_meeting(self, tenant_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting | None:
        return await self._meetings.get(tenant_id, meeting_id)

    async def list_meetings(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        status: MeetingStatus | None = None,
    ) -> builtins.list[Meeting]:
        return await self._meetings.list(tenant_id, organization_id=organization_id, status=status)

    async def complete_meeting(
        self, tenant_id: uuid.UUID, meeting_id: uuid.UUID, *, outcome: str
    ) -> Meeting | None:
        meeting = await self._meetings.get(tenant_id, meeting_id)
        if meeting is None:
            return None
        meeting.status = MeetingStatus.COMPLETED
        meeting.outcome = outcome
        updated = await self._meetings.update(meeting)
        await self._events.record(
            event_type=PMEventType.MEETING_COMPLETED,
            tenant_id=tenant_id,
            aggregate_id=meeting_id,
            payload={"outcome": outcome},
        )
        return updated

    # --- CRM tasks -----------------------------------------------------

    async def create_task(
        self,
        *,
        tenant_id: uuid.UUID,
        title: str,
        description: str = "",
        priority: int = 3,
        due_at: datetime | None = None,
        organization_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        owner_agent_id: uuid.UUID | None = None,
    ) -> CrmTask:
        task = await self._tasks.add(
            CrmTask(
                tenant_id=tenant_id,
                title=title,
                description=description,
                priority=priority,
                due_at=due_at,
                organization_id=organization_id,
                opportunity_id=opportunity_id,
                project_id=project_id,
                owner_agent_id=owner_agent_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.TASK_CREATED,
            tenant_id=tenant_id,
            aggregate_id=task.id,
            payload={"title": title},
        )
        return task

    async def get_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> CrmTask | None:
        return await self._tasks.get(tenant_id, task_id)

    async def complete_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> CrmTask | None:
        task = await self._tasks.get(tenant_id, task_id)
        if task is None:
            return None
        task.status = CrmTaskStatus.DONE
        updated = await self._tasks.update(task)
        await self._events.record(
            event_type=PMEventType.TASK_COMPLETED,
            tenant_id=tenant_id,
            aggregate_id=task_id,
            payload={},
        )
        return updated

    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        *,
        status: CrmTaskStatus | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> builtins.list[CrmTask]:
        return await self._tasks.list(tenant_id, status=status, organization_id=organization_id)

    # --- Notes ---------------------------------------------------------

    async def record_note(
        self,
        *,
        tenant_id: uuid.UUID,
        author: str,
        body: str,
        organization_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> Note:
        note = await self._notes.add(
            Note(
                tenant_id=tenant_id,
                author=author,
                body=body,
                organization_id=organization_id,
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                project_id=project_id,
            )
        )
        await self._events.record(
            event_type=PMEventType.NOTE_RECORDED,
            tenant_id=tenant_id,
            aggregate_id=note.id,
            payload={"author": author},
        )
        return note

    async def list_notes(
        self, tenant_id: uuid.UUID, *, organization_id: uuid.UUID | None = None
    ) -> builtins.list[Note]:
        return await self._notes.list(tenant_id, organization_id=organization_id)
