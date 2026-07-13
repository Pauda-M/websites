"""CRM domain — the Program Manager's model of the outside world.

A tenant-agnostic CRM abstraction the Program Manager reasons over: Organizations
and their Contacts; Leads that qualify into Opportunities; Opportunities that win
into Projects; and the Meetings, Tasks, and Notes that hang off them. Every
aggregate is tenant-scoped and carries an ``organization_id`` spine so the graph
is navigable.

Organizations carry the three relationship scores the Program Manager maintains
as organizational memory — ``relationship_score`` (health of the relationship),
``trust_score`` (mutual reliability), and ``importance_score`` (strategic
weight) — each a bounded 0.0-1.0 float.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.agents.program_manager.domain.common import new_id, utcnow

# --- Organization -------------------------------------------------------


class OrganizationStatus(enum.StrEnum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    DORMANT = "dormant"
    CHURNED = "churned"


class Organization(BaseModel):
    """A customer or prospect organization (the CRM ``Account`` aggregate).

    Distinct from the platform *tenant* (the Company operating the Program
    Manager): an Organization is a company the Program Manager does business
    *with*, scoped under a tenant.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None  # employee-count band, e.g. "11-50"
    status: OrganizationStatus = OrganizationStatus.PROSPECT
    relationship_score: float = Field(default=0.5, ge=0.0, le=1.0)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- Contact ------------------------------------------------------------


class ContactRole(enum.StrEnum):
    DECISION_MAKER = "decision_maker"
    CHAMPION = "champion"
    INFLUENCER = "influencer"
    USER = "user"
    GATEKEEPER = "gatekeeper"
    UNKNOWN = "unknown"


class Contact(BaseModel):
    """A person at an Organization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    first_name: str
    last_name: str = ""
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    role: ContactRole = ContactRole.UNKNOWN
    is_primary: bool = False
    relationship_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


# --- Lead ---------------------------------------------------------------


class LeadSource(enum.StrEnum):
    WEBSITE = "website"
    REFERRAL = "referral"
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    EVENT = "event"
    PARTNER = "partner"
    UNKNOWN = "unknown"


class LeadStatus(enum.StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    CONVERTED = "converted"


class Lead(BaseModel):
    """An unqualified or qualifying interest, before it becomes an Opportunity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    source: LeadSource = LeadSource.UNKNOWN
    status: LeadStatus = LeadStatus.NEW
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""
    owner_agent_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None  # set once converted
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- Opportunity --------------------------------------------------------


class OpportunityStage(enum.StrEnum):
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


_OPEN_STAGES = frozenset(
    {
        OpportunityStage.DISCOVERY,
        OpportunityStage.QUALIFICATION,
        OpportunityStage.PROPOSAL,
        OpportunityStage.NEGOTIATION,
    }
)


class Opportunity(BaseModel):
    """A qualified deal in the pipeline."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    stage: OpportunityStage = OpportunityStage.DISCOVERY
    amount: float = Field(default=0.0, ge=0.0)
    currency: str = "EUR"
    probability: float = Field(default=0.1, ge=0.0, le=1.0)
    expected_close_date: date | None = None
    primary_contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    owner_agent_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def is_open(self) -> bool:
        return self.stage in _OPEN_STAGES

    @property
    def weighted_amount(self) -> float:
        return self.amount * self.probability


# --- Project ------------------------------------------------------------


class ProjectStatus(enum.StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectHealth(enum.StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class Project(BaseModel):
    """Delivery work won from an Opportunity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    status: ProjectStatus = ProjectStatus.PLANNED
    health: ProjectHealth = ProjectHealth.ON_TRACK
    opportunity_id: uuid.UUID | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    owner_agent_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- Meeting ------------------------------------------------------------


class MeetingStatus(enum.StrEnum):
    PROPOSED = "proposed"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Meeting(BaseModel):
    """A scheduled interaction with an Organization's Contacts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=1)
    status: MeetingStatus = MeetingStatus.PROPOSED
    contact_ids: list[uuid.UUID] = Field(default_factory=list)
    location: str | None = None  # physical location or a conferencing link
    agenda: str = ""
    outcome: str = ""
    opportunity_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- CRM Task -----------------------------------------------------------


class CrmTaskStatus(enum.StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class CrmTask(BaseModel):
    """A human- or agent-owned to-do attached to a CRM entity.

    Distinct from :class:`~pb_api.agents.program_manager.domain.run.PMTask`,
    which is a unit of the Program Manager's own plan execution.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    title: str
    description: str = ""
    status: CrmTaskStatus = CrmTaskStatus.OPEN
    priority: int = Field(default=3, ge=1, le=5)
    due_at: datetime | None = None
    organization_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    owner_agent_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- Note ---------------------------------------------------------------


class Note(BaseModel):
    """A free-text observation attached to any CRM entity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    author: str
    body: str
    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
