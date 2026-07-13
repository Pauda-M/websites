"""Tool registry domain models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import new_id, utcnow


class ToolHealth(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class SideEffect(enum.StrEnum):
    """How consequential invoking a tool is — drives approval requirements."""

    READ_ONLY = "read_only"
    MUTATING = "mutating"
    EXTERNAL = "external"  # contacts the outside world (e.g. sends email)


class ToolDefinition(BaseModel):
    """A registered tool a capability can execute.

    Exposes name, version, permissions, input/output schemas, health, and
    timeout (Phase 7 spec).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID | None = None  # None => platform-global tool
    name: str
    version: str = "1.0.0"
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    input_schema: dict[str, object] = Field(default_factory=dict)  # JSON Schema
    output_schema: dict[str, object] = Field(default_factory=dict)
    side_effect: SideEffect = SideEffect.READ_ONLY
    timeout_seconds: int = Field(default=30, ge=1)
    health: ToolHealth = ToolHealth.UNKNOWN
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
