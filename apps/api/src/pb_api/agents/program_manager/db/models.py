"""SQLAlchemy ORM models for the Program Manager.

All tables share the platform ``Base`` (`pb_api.db.base`) so a single Alembic
chain and ``metadata.create_all`` cover the whole platform. Every row is
tenant-scoped (``tenant_id``). Portable column types (Uuid, JSON, String, Date,
non-native enums as String) keep the suite runnable on SQLite while production
runs PostgreSQL — the same portability contract the Cognitive Core follows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from pb_api.db.base import Base

JsonList = list[object]
JsonDict = dict[str, object]


class _PMBase(Base):
    """Abstract base: primary key, tenant scope, created timestamp."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- CRM ----------------------------------------------------------------


class OrganizationRow(_PMBase):
    __tablename__ = "pm_organization"

    name: Mapped[str] = mapped_column(String(500), index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="prospect", index=True)
    relationship_score: Mapped[float] = mapped_column(Float, default=0.5)
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    tags: Mapped[JsonList] = mapped_column(JSON, default=list)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContactRow(_PMBase):
    __tablename__ = "pm_contact"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="unknown")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    relationship_score: Mapped[float] = mapped_column(Float, default=0.5)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeadRow(_PMBase):
    __tablename__ = "pm_lead"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text, default="")
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OpportunityRow(_PMBase):
    __tablename__ = "pm_opportunity"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(500))
    stage: Mapped[str] = mapped_column(String(20), default="discovery", index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    probability: Mapped[float] = mapped_column(Float, default=0.1)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectRow(_PMBase):
    __tablename__ = "pm_project"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    health: Mapped[str] = mapped_column(String(20), default="on_track")
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MeetingRow(_PMBase):
    __tablename__ = "pm_meeting"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    title: Mapped[str] = mapped_column(String(500))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    contact_ids: Mapped[JsonList] = mapped_column(JSON, default=list)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agenda: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmTaskRow(_PMBase):
    __tablename__ = "pm_crm_task"

    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NoteRow(_PMBase):
    __tablename__ = "pm_note"

    author: Mapped[str] = mapped_column(String(255), index=True)
    body: Mapped[str] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


# --- Proposal -----------------------------------------------------------


class ProposalRow(_PMBase):
    __tablename__ = "pm_proposal"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[JsonList] = mapped_column(JSON, default=list)
    total_value: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Scheduling ---------------------------------------------------------


class ScheduledActionRow(_PMBase):
    __tablename__ = "pm_scheduled_action"

    kind: Mapped[str] = mapped_column(String(20), default="followup", index=True)
    goal_type: Mapped[str] = mapped_column(String(30), default="follow_up_lead")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    subject_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    cadence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Planning & runs ----------------------------------------------------


class PMPlanRow(_PMBase):
    __tablename__ = "pm_plan"

    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    goal_type: Mapped[str] = mapped_column(String(30))
    objective: Mapped[str] = mapped_column(Text)
    steps: Mapped[JsonList] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class PMRunRow(_PMBase):
    __tablename__ = "pm_run"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    trigger_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(20), default="idle", index=True)
    goal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    states_visited: Mapped[JsonList] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(Text, default="")
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    awaiting_approval: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PMTaskRow(_PMBase):
    __tablename__ = "pm_task"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    step_key: Mapped[str] = mapped_column(String(100))
    goal_type: Mapped[str] = mapped_column(String(30))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    authority_required: Mapped[int] = mapped_column(Integer, default=1)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
