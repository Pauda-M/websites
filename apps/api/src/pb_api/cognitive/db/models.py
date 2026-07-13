"""SQLAlchemy ORM models for the Cognitive Core.

All tables share the platform ``Base`` (`pb_api.db.base`) so a single Alembic
chain and ``metadata.create_all`` cover them. Every row is tenant-scoped
(`tenant_id`). Portable column types (Uuid, JSON, String, non-native enums as
String) keep the suite runnable on SQLite while production runs PostgreSQL.
Embeddings and list/dict fields are stored as JSON — the default ``VectorStore``
adapter; pgvector is the production scale-up (`docs/genesis/004_Company_Brain.md`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from pb_api.db.base import Base

JsonList = list[object]
JsonDict = dict[str, object]


class _Base(Base):
    """Abstract base: primary key, tenant scope, created timestamp."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryItemRow(_Base):
    __tablename__ = "cog_memory_item"

    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[JsonList | None] = mapped_column(JSON, nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    related_entity_ids: Mapped[JsonList] = mapped_column(JSON, default=list)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkingEntryRow(_Base):
    __tablename__ = "cog_working_entry"

    scope_key: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    relevance: Mapped[float] = mapped_column(Float, default=0.5)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(50), default="unknown")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class EpisodicEventRow(_Base):
    __tablename__ = "cog_episodic_event"

    # `organization` in the domain maps to tenant_id (already on _Base).
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(255), index=True)
    conversation: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    customer: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    project: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    summary: Mapped[str] = mapped_column(Text)
    embedding: Mapped[JsonList | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    related_entities: Mapped[JsonList] = mapped_column(JSON, default=list)


class SemanticItemRow(_Base):
    __tablename__ = "cog_semantic_item"

    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    embedding: Mapped[JsonList | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class RelationshipRow(_Base):
    __tablename__ = "cog_relationship"

    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    relation: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class ProcedureRow(_Base):
    __tablename__ = "cog_procedure"

    slug: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[JsonList] = mapped_column(JSON, default=list)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class GoalRow(_Base):
    __tablename__ = "cog_goal"

    level: Mapped[str] = mapped_column(String(20), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    depends_on: Mapped[JsonList] = mapped_column(JSON, default=list)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GoalHistoryRow(_Base):
    __tablename__ = "cog_goal_history"

    goal_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    change: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRow(_Base):
    __tablename__ = "cog_agent"

    name: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(100), index=True)
    capabilities: Mapped[JsonList] = mapped_column(JSON, default=list)
    default_authority: Mapped[int] = mapped_column(Integer, default=1)
    tools: Mapped[JsonList] = mapped_column(JSON, default=list)
    memory_access: Mapped[JsonList] = mapped_column(JSON, default=list)
    goal_ids: Mapped[JsonList] = mapped_column(JSON, default=list)
    policy_ids: Mapped[JsonList] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="registered", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ToolRow(_Base):
    __tablename__ = "cog_tool"

    name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    description: Mapped[str] = mapped_column(Text, default="")
    permissions: Mapped[JsonList] = mapped_column(JSON, default=list)
    input_schema: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    side_effect: Mapped[str] = mapped_column(String(20), default="read_only")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolicyRow(_Base):
    __tablename__ = "cog_policy"

    name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(200), index=True)
    resource: Mapped[str] = mapped_column(String(200), default="*")
    effect: Mapped[str] = mapped_column(String(20), default="allow")
    min_authority: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class ReflectionRow(_Base):
    __tablename__ = "cog_reflection"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[JsonList] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    future_recommendations: Mapped[JsonList] = mapped_column(JSON, default=list)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class PlanRow(_Base):
    __tablename__ = "cog_plan"

    goal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text)
    tasks: Mapped[JsonList] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    meta: Mapped[JsonDict] = mapped_column(JSON, default=dict)


class EventRow(_Base):
    __tablename__ = "cog_event"

    type: Mapped[str] = mapped_column(String(120), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(255), default="system")
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
