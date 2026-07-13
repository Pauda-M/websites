"""Agent registry domain models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import AuthorityLevel, MemoryType, new_id, utcnow


class AgentStatus(enum.StrEnum):
    """Lifecycle status (subset of Genesis §7 relevant to the registry)."""

    PROVISIONED = "provisioned"
    REGISTERED = "registered"
    IDLE = "idle"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class AgentRegistration(BaseModel):
    """An AI Employee's registration record.

    Captures identity, role, capabilities, authority, tools, memory access,
    goals, policies, status, and version (Phase 7 spec).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    name: str  # identity, unique per tenant
    role: str  # e.g. "sales_manager"
    capabilities: list[str] = Field(default_factory=list)
    default_authority: AuthorityLevel = AuthorityLevel.SUGGEST
    tools: list[str] = Field(default_factory=list)  # tool names it may use
    memory_access: list[MemoryType] = Field(default_factory=list)
    goal_ids: list[uuid.UUID] = Field(default_factory=list)
    policy_ids: list[uuid.UUID] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.REGISTERED
    version: int = 1
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
