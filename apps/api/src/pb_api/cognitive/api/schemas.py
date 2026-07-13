"""Request bodies for the Cognitive Core HTTP API (Pydantic v2).

There is no tenant authentication yet, so every write body carries an explicit
``tenant_id``. Bodies hold only the fields a caller sets — server-assigned
identifiers, versions, and timestamps are never accepted from the client. Domain
enums and value objects (``ProcedureStep``, ``PlanTask``, ``MemoryType`` …) are
reused directly so the HTTP contract and the domain stay in lock-step.

``AuthorityLevel`` is transported as a plain integer (0-5) and converted to the
enum in the route layer, keeping the wire format friendly to non-Python callers.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from pb_api.cognitive.domain.agents import AgentStatus
from pb_api.cognitive.domain.common import AuthorityLevel, MemoryType
from pb_api.cognitive.domain.goals import GoalLevel, GoalStatus
from pb_api.cognitive.domain.planning import PlanStatus, PlanTask
from pb_api.cognitive.domain.policy import PolicyEffect
from pb_api.cognitive.domain.procedural import ProcedureStep
from pb_api.cognitive.domain.semantic import KnowledgeKind
from pb_api.cognitive.domain.tools import SideEffect, ToolHealth

# --- Working memory -----------------------------------------------------


class WorkingRememberRequest(BaseModel):
    tenant_id: uuid.UUID
    scope_key: str
    content: str
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "observation"
    ttl_seconds: int | None = Field(default=None, ge=1)


class WorkingMergeRequest(BaseModel):
    tenant_id: uuid.UUID
    source_scopes: list[str]


# --- Episodic memory ----------------------------------------------------


class EpisodicRecordRequest(BaseModel):
    tenant_id: uuid.UUID
    actor: str
    summary: str
    conversation: uuid.UUID | None = None
    customer: uuid.UUID | None = None
    project: uuid.UUID | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    related_entities: list[uuid.UUID] = Field(default_factory=list)


class ConsolidateRequest(BaseModel):
    tenant_id: uuid.UUID


# --- Semantic memory ----------------------------------------------------


class SemanticAddRequest(BaseModel):
    tenant_id: uuid.UUID
    kind: KnowledgeKind
    name: str
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str | None = None
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SemanticUpdateRequest(BaseModel):
    tenant_id: uuid.UUID
    content: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None


class RelateRequest(BaseModel):
    tenant_id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str | None = None


# --- Procedural memory --------------------------------------------------


class ProcedureRegisterRequest(BaseModel):
    tenant_id: uuid.UUID
    slug: str
    name: str
    description: str = ""
    steps: list[ProcedureStep] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ProcedureSeedRequest(BaseModel):
    tenant_id: uuid.UUID


# --- Goals --------------------------------------------------------------


class GoalCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    level: GoalLevel
    title: str
    description: str = ""
    parent_id: uuid.UUID | None = None
    owner_agent_id: uuid.UUID | None = None
    priority: int = Field(default=3, ge=1, le=5)
    depends_on: list[uuid.UUID] = Field(default_factory=list)


class GoalStatusRequest(BaseModel):
    tenant_id: uuid.UUID
    status: GoalStatus


class GoalProgressRequest(BaseModel):
    tenant_id: uuid.UUID
    progress: float = Field(ge=0.0, le=1.0)


# --- Agents -------------------------------------------------------------


class AgentRegisterRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str
    role: str
    capabilities: list[str] = Field(default_factory=list)
    default_authority: int = Field(default=int(AuthorityLevel.SUGGEST), ge=0, le=5)
    tools: list[str] = Field(default_factory=list)
    memory_access: list[MemoryType] = Field(default_factory=list)
    goal_ids: list[uuid.UUID] = Field(default_factory=list)
    policy_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentStatusRequest(BaseModel):
    tenant_id: uuid.UUID
    status: AgentStatus


# --- Tools --------------------------------------------------------------


class ToolRegisterRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str
    version: str = "1.0.0"
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    side_effect: SideEffect = SideEffect.READ_ONLY
    timeout_seconds: int = Field(default=30, ge=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class ToolHealthRequest(BaseModel):
    tenant_id: uuid.UUID
    health: ToolHealth


# --- Policies -----------------------------------------------------------


class PolicyCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str
    action: str
    resource: str = "*"
    effect: PolicyEffect = PolicyEffect.ALLOW
    min_authority: int = Field(default=int(AuthorityLevel.OBSERVE), ge=0, le=5)
    priority: int = Field(default=100, ge=0)
    enabled: bool = True
    description: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class PolicyEvaluateRequest(BaseModel):
    tenant_id: uuid.UUID
    actor_authority: int = Field(ge=0, le=5)
    action: str
    resource: str = "*"


# --- Reflection ---------------------------------------------------------


class ReflectRequest(BaseModel):
    tenant_id: uuid.UUID
    objective: str
    outcome: str
    success: bool
    agent_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    failure_reason: str | None = None
    lessons_learned: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    future_recommendations: list[str] = Field(default_factory=list)


# --- Planning -----------------------------------------------------------


class PlanCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    objective: str
    tasks: list[PlanTask] = Field(default_factory=list)
    goal_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None


class PlanStatusRequest(BaseModel):
    tenant_id: uuid.UUID
    status: PlanStatus


# --- Context / prompt ---------------------------------------------------


class ContextBuildRequest(BaseModel):
    tenant_id: uuid.UUID
    scope_key: str
    query: str | None = None
    goal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    token_budget: int | None = Field(default=None, ge=1)
    max_memories: int | None = Field(default=None, ge=1)


class PromptBuildRequest(BaseModel):
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    task: str
    scope_key: str | None = None
    query: str | None = None
    token_budget: int | None = Field(default=None, ge=1)
    output_requirements: str | None = None
