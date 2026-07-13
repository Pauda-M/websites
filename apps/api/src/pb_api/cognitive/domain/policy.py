"""Policy engine domain models.

Policies determine what agents may do, approval requirements, authority limits,
communication rules, and security constraints. Evaluation is deterministic:
the most specific matching rule wins; ties resolve deny-over-allow.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.cognitive.domain.common import AuthorityLevel, new_id, utcnow


class PolicyEffect(enum.StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class Policy(BaseModel):
    """A single policy rule.

    ``action`` and ``resource`` support a trailing ``*`` wildcard. ``min_authority``
    is the authority an actor must hold for the action; if the actor holds less,
    the effect is escalated to ``require_approval`` (never silently allowed).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    name: str
    action: str  # e.g. "email.send", "crm.*"
    resource: str = "*"
    effect: PolicyEffect = PolicyEffect.ALLOW
    min_authority: AuthorityLevel = AuthorityLevel.OBSERVE
    priority: int = Field(default=100, ge=0)  # higher = evaluated first
    enabled: bool = True
    description: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class PolicyRequest(BaseModel):
    """A request to evaluate whether an actor may perform an action."""

    tenant_id: uuid.UUID
    actor_authority: AuthorityLevel
    action: str
    resource: str = "*"


class PolicyDecision(BaseModel):
    """The engine's ruling, with the deciding rule and a human-readable reason."""

    allowed: bool
    requires_approval: bool
    effect: PolicyEffect
    reason: str
    matched_policy_id: uuid.UUID | None = None
