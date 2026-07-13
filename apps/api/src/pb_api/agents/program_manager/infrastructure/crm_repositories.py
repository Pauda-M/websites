"""Tenant-scoped async repositories for the CRM aggregates.

One repository per CRM aggregate (Organization, Contact, Lead, Opportunity,
Project, Meeting, CrmTask, Note), each subclassing :class:`BaseRepository` and
scoping every query by ``tenant_id`` — cross-tenant access is impossible by
construction (Genesis §12.6). Notes are append-only and therefore have no
``update`` method.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from pb_api.agents.program_manager.db.models import (
    ContactRow,
    CrmTaskRow,
    LeadRow,
    MeetingRow,
    NoteRow,
    OpportunityRow,
    OrganizationRow,
    ProjectRow,
)
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
from pb_api.cognitive.domain.common import utcnow
from pb_api.cognitive.repositories.base import (
    BaseRepository,
    json_to_uuids,
    uuids_to_json,
)

# --- Organization -------------------------------------------------------


def _row_to_organization(row: OrganizationRow) -> Organization:
    return Organization(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        domain=row.domain,
        industry=row.industry,
        size=row.size,
        status=OrganizationStatus(row.status),
        relationship_score=row.relationship_score,
        trust_score=row.trust_score,
        importance_score=row.importance_score,
        tags=[str(item) for item in row.tags],
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class OrganizationRepository(BaseRepository):
    async def add(self, org: Organization) -> Organization:
        row = OrganizationRow(
            id=org.id,
            tenant_id=org.tenant_id,
            name=org.name,
            domain=org.domain,
            industry=org.industry,
            size=org.size,
            status=org.status.value,
            relationship_score=org.relationship_score,
            trust_score=org.trust_score,
            importance_score=org.importance_score,
            tags=list(org.tags),
            meta=org.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_organization(row)

    async def get(self, tenant_id: uuid.UUID, org_id: uuid.UUID) -> Organization | None:
        row = await self.session.get(OrganizationRow, org_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_organization(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: OrganizationStatus | None = None,
        limit: int = 200,
    ) -> list[Organization]:
        stmt = select(OrganizationRow).where(OrganizationRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(OrganizationRow.status == status.value)
        stmt = stmt.order_by(OrganizationRow.name.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_organization(row) for row in rows]

    async def update(self, org: Organization) -> Organization | None:
        row = await self.session.get(OrganizationRow, org.id)
        if row is None or row.tenant_id != org.tenant_id:
            return None
        row.name = org.name
        row.domain = org.domain
        row.industry = org.industry
        row.size = org.size
        row.status = org.status.value
        row.relationship_score = org.relationship_score
        row.trust_score = org.trust_score
        row.importance_score = org.importance_score
        row.tags = list(org.tags)
        row.meta = org.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_organization(row)


# --- Contact ------------------------------------------------------------


def _row_to_contact(row: ContactRow) -> Contact:
    return Contact(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone=row.phone,
        title=row.title,
        role=ContactRole(row.role),
        is_primary=row.is_primary,
        relationship_score=row.relationship_score,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ContactRepository(BaseRepository):
    async def add(self, contact: Contact) -> Contact:
        row = ContactRow(
            id=contact.id,
            tenant_id=contact.tenant_id,
            organization_id=contact.organization_id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            email=contact.email,
            phone=contact.phone,
            title=contact.title,
            role=contact.role.value,
            is_primary=contact.is_primary,
            relationship_score=contact.relationship_score,
            meta=contact.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_contact(row)

    async def get(self, tenant_id: uuid.UUID, contact_id: uuid.UUID) -> Contact | None:
        row = await self.session.get(ContactRow, contact_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_contact(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Contact]:
        stmt = select(ContactRow).where(ContactRow.tenant_id == tenant_id)
        if organization_id is not None:
            stmt = stmt.where(ContactRow.organization_id == organization_id)
        stmt = stmt.order_by(ContactRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_contact(row) for row in rows]

    async def update(self, contact: Contact) -> Contact | None:
        row = await self.session.get(ContactRow, contact.id)
        if row is None or row.tenant_id != contact.tenant_id:
            return None
        row.organization_id = contact.organization_id
        row.first_name = contact.first_name
        row.last_name = contact.last_name
        row.email = contact.email
        row.phone = contact.phone
        row.title = contact.title
        row.role = contact.role.value
        row.is_primary = contact.is_primary
        row.relationship_score = contact.relationship_score
        row.meta = contact.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_contact(row)


# --- Lead ---------------------------------------------------------------


def _row_to_lead(row: LeadRow) -> Lead:
    return Lead(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        contact_id=row.contact_id,
        source=LeadSource(row.source),
        status=LeadStatus(row.status),
        score=row.score,
        summary=row.summary,
        owner_agent_id=row.owner_agent_id,
        opportunity_id=row.opportunity_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class LeadRepository(BaseRepository):
    async def add(self, lead: Lead) -> Lead:
        row = LeadRow(
            id=lead.id,
            tenant_id=lead.tenant_id,
            organization_id=lead.organization_id,
            contact_id=lead.contact_id,
            source=lead.source.value,
            status=lead.status.value,
            score=lead.score,
            summary=lead.summary,
            owner_agent_id=lead.owner_agent_id,
            opportunity_id=lead.opportunity_id,
            meta=lead.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_lead(row)

    async def get(self, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        row = await self.session.get(LeadRow, lead_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_lead(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: LeadStatus | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Lead]:
        stmt = select(LeadRow).where(LeadRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(LeadRow.status == status.value)
        if organization_id is not None:
            stmt = stmt.where(LeadRow.organization_id == organization_id)
        stmt = stmt.order_by(LeadRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_lead(row) for row in rows]

    async def update(self, lead: Lead) -> Lead | None:
        row = await self.session.get(LeadRow, lead.id)
        if row is None or row.tenant_id != lead.tenant_id:
            return None
        row.organization_id = lead.organization_id
        row.contact_id = lead.contact_id
        row.source = lead.source.value
        row.status = lead.status.value
        row.score = lead.score
        row.summary = lead.summary
        row.owner_agent_id = lead.owner_agent_id
        row.opportunity_id = lead.opportunity_id
        row.meta = lead.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_lead(row)


# --- Opportunity --------------------------------------------------------


def _row_to_opportunity(row: OpportunityRow) -> Opportunity:
    return Opportunity(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        name=row.name,
        stage=OpportunityStage(row.stage),
        amount=row.amount,
        currency=row.currency,
        probability=row.probability,
        expected_close_date=row.expected_close_date,
        primary_contact_id=row.primary_contact_id,
        lead_id=row.lead_id,
        owner_agent_id=row.owner_agent_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class OpportunityRepository(BaseRepository):
    async def add(self, opp: Opportunity) -> Opportunity:
        row = OpportunityRow(
            id=opp.id,
            tenant_id=opp.tenant_id,
            organization_id=opp.organization_id,
            name=opp.name,
            stage=opp.stage.value,
            amount=opp.amount,
            currency=opp.currency,
            probability=opp.probability,
            expected_close_date=opp.expected_close_date,
            primary_contact_id=opp.primary_contact_id,
            lead_id=opp.lead_id,
            owner_agent_id=opp.owner_agent_id,
            meta=opp.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_opportunity(row)

    async def get(self, tenant_id: uuid.UUID, opp_id: uuid.UUID) -> Opportunity | None:
        row = await self.session.get(OpportunityRow, opp_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_opportunity(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        stage: OpportunityStage | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Opportunity]:
        stmt = select(OpportunityRow).where(OpportunityRow.tenant_id == tenant_id)
        if stage is not None:
            stmt = stmt.where(OpportunityRow.stage == stage.value)
        if organization_id is not None:
            stmt = stmt.where(OpportunityRow.organization_id == organization_id)
        stmt = stmt.order_by(OpportunityRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_opportunity(row) for row in rows]

    async def update(self, opp: Opportunity) -> Opportunity | None:
        row = await self.session.get(OpportunityRow, opp.id)
        if row is None or row.tenant_id != opp.tenant_id:
            return None
        row.organization_id = opp.organization_id
        row.name = opp.name
        row.stage = opp.stage.value
        row.amount = opp.amount
        row.currency = opp.currency
        row.probability = opp.probability
        row.expected_close_date = opp.expected_close_date
        row.primary_contact_id = opp.primary_contact_id
        row.lead_id = opp.lead_id
        row.owner_agent_id = opp.owner_agent_id
        row.meta = opp.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_opportunity(row)


# --- Project ------------------------------------------------------------


def _row_to_project(row: ProjectRow) -> Project:
    return Project(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        name=row.name,
        status=ProjectStatus(row.status),
        health=ProjectHealth(row.health),
        opportunity_id=row.opportunity_id,
        start_date=row.start_date,
        target_end_date=row.target_end_date,
        owner_agent_id=row.owner_agent_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectRepository(BaseRepository):
    async def add(self, project: Project) -> Project:
        row = ProjectRow(
            id=project.id,
            tenant_id=project.tenant_id,
            organization_id=project.organization_id,
            name=project.name,
            status=project.status.value,
            health=project.health.value,
            opportunity_id=project.opportunity_id,
            start_date=project.start_date,
            target_end_date=project.target_end_date,
            owner_agent_id=project.owner_agent_id,
            meta=project.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_project(row)

    async def get(self, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project | None:
        row = await self.session.get(ProjectRow, project_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_project(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Project]:
        stmt = select(ProjectRow).where(ProjectRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(ProjectRow.status == status.value)
        if organization_id is not None:
            stmt = stmt.where(ProjectRow.organization_id == organization_id)
        stmt = stmt.order_by(ProjectRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_project(row) for row in rows]

    async def update(self, project: Project) -> Project | None:
        row = await self.session.get(ProjectRow, project.id)
        if row is None or row.tenant_id != project.tenant_id:
            return None
        row.organization_id = project.organization_id
        row.name = project.name
        row.status = project.status.value
        row.health = project.health.value
        row.opportunity_id = project.opportunity_id
        row.start_date = project.start_date
        row.target_end_date = project.target_end_date
        row.owner_agent_id = project.owner_agent_id
        row.meta = project.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_project(row)


# --- Meeting ------------------------------------------------------------


def _row_to_meeting(row: MeetingRow) -> Meeting:
    return Meeting(
        id=row.id,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        title=row.title,
        scheduled_at=row.scheduled_at,
        duration_minutes=row.duration_minutes,
        status=MeetingStatus(row.status),
        contact_ids=json_to_uuids(row.contact_ids),
        location=row.location,
        agenda=row.agenda,
        outcome=row.outcome,
        opportunity_id=row.opportunity_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class MeetingRepository(BaseRepository):
    async def add(self, meeting: Meeting) -> Meeting:
        row = MeetingRow(
            id=meeting.id,
            tenant_id=meeting.tenant_id,
            organization_id=meeting.organization_id,
            title=meeting.title,
            scheduled_at=meeting.scheduled_at,
            duration_minutes=meeting.duration_minutes,
            status=meeting.status.value,
            contact_ids=uuids_to_json(meeting.contact_ids),
            location=meeting.location,
            agenda=meeting.agenda,
            outcome=meeting.outcome,
            opportunity_id=meeting.opportunity_id,
            meta=meeting.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_meeting(row)

    async def get(self, tenant_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting | None:
        row = await self.session.get(MeetingRow, meeting_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_meeting(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        status: MeetingStatus | None = None,
        limit: int = 200,
    ) -> list[Meeting]:
        stmt = select(MeetingRow).where(MeetingRow.tenant_id == tenant_id)
        if organization_id is not None:
            stmt = stmt.where(MeetingRow.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(MeetingRow.status == status.value)
        stmt = stmt.order_by(MeetingRow.scheduled_at.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_meeting(row) for row in rows]

    async def update(self, meeting: Meeting) -> Meeting | None:
        row = await self.session.get(MeetingRow, meeting.id)
        if row is None or row.tenant_id != meeting.tenant_id:
            return None
        row.organization_id = meeting.organization_id
        row.title = meeting.title
        row.scheduled_at = meeting.scheduled_at
        row.duration_minutes = meeting.duration_minutes
        row.status = meeting.status.value
        row.contact_ids = list(uuids_to_json(meeting.contact_ids))
        row.location = meeting.location
        row.agenda = meeting.agenda
        row.outcome = meeting.outcome
        row.opportunity_id = meeting.opportunity_id
        row.meta = meeting.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_meeting(row)


# --- CRM Task -----------------------------------------------------------


def _row_to_crm_task(row: CrmTaskRow) -> CrmTask:
    return CrmTask(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        description=row.description,
        status=CrmTaskStatus(row.status),
        priority=row.priority,
        due_at=row.due_at,
        organization_id=row.organization_id,
        opportunity_id=row.opportunity_id,
        project_id=row.project_id,
        owner_agent_id=row.owner_agent_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CrmTaskRepository(BaseRepository):
    async def add(self, task: CrmTask) -> CrmTask:
        row = CrmTaskRow(
            id=task.id,
            tenant_id=task.tenant_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority,
            due_at=task.due_at,
            organization_id=task.organization_id,
            opportunity_id=task.opportunity_id,
            project_id=task.project_id,
            owner_agent_id=task.owner_agent_id,
            meta=task.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_crm_task(row)

    async def get(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> CrmTask | None:
        row = await self.session.get(CrmTaskRow, task_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_crm_task(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: CrmTaskStatus | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[CrmTask]:
        stmt = select(CrmTaskRow).where(CrmTaskRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(CrmTaskRow.status == status.value)
        if organization_id is not None:
            stmt = stmt.where(CrmTaskRow.organization_id == organization_id)
        stmt = stmt.order_by(CrmTaskRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_crm_task(row) for row in rows]

    async def update(self, task: CrmTask) -> CrmTask | None:
        row = await self.session.get(CrmTaskRow, task.id)
        if row is None or row.tenant_id != task.tenant_id:
            return None
        row.title = task.title
        row.description = task.description
        row.status = task.status.value
        row.priority = task.priority
        row.due_at = task.due_at
        row.organization_id = task.organization_id
        row.opportunity_id = task.opportunity_id
        row.project_id = task.project_id
        row.owner_agent_id = task.owner_agent_id
        row.meta = task.metadata
        row.updated_at = utcnow()
        await self.session.flush()
        return _row_to_crm_task(row)


# --- Note ---------------------------------------------------------------


def _row_to_note(row: NoteRow) -> Note:
    return Note(
        id=row.id,
        tenant_id=row.tenant_id,
        author=row.author,
        body=row.body,
        organization_id=row.organization_id,
        contact_id=row.contact_id,
        opportunity_id=row.opportunity_id,
        project_id=row.project_id,
        metadata=dict(row.meta),
        created_at=row.created_at,
    )


class NoteRepository(BaseRepository):
    async def add(self, note: Note) -> Note:
        row = NoteRow(
            id=note.id,
            tenant_id=note.tenant_id,
            author=note.author,
            body=note.body,
            organization_id=note.organization_id,
            contact_id=note.contact_id,
            opportunity_id=note.opportunity_id,
            project_id=note.project_id,
            meta=note.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _row_to_note(row)

    async def get(self, tenant_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        row = await self.session.get(NoteRow, note_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _row_to_note(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        opportunity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[Note]:
        stmt = select(NoteRow).where(NoteRow.tenant_id == tenant_id)
        if organization_id is not None:
            stmt = stmt.where(NoteRow.organization_id == organization_id)
        if opportunity_id is not None:
            stmt = stmt.where(NoteRow.opportunity_id == opportunity_id)
        if project_id is not None:
            stmt = stmt.where(NoteRow.project_id == project_id)
        if contact_id is not None:
            stmt = stmt.where(NoteRow.contact_id == contact_id)
        stmt = stmt.order_by(NoteRow.created_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_row_to_note(row) for row in rows]
