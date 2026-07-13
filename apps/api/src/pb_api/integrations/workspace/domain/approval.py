"""Approval domain — policies and decisions for every outbound workspace action.

Every action that leaves the building (send mail, accept a meeting, post to Teams,
create a task assigned to a human) passes the approval engine. A policy matches on
customer, organization, communication type, agent, and minimum authority, and
yields one of four decisions. The most specific enabled policy wins; with no match
the engine is conservative and requires human approval.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import (
    ApprovalDecisionType,
    new_id,
    utcnow,
)


class CommunicationType(enum.StrEnum):
    MAIL_REPLY = "mail_reply"
    MAIL_FORWARD = "mail_forward"
    MAIL_NEW = "mail_new"
    MEETING_INVITE = "meeting_invite"
    MEETING_RESPONSE = "meeting_response"
    TEAMS_MESSAGE = "teams_message"
    TASK_ASSIGNMENT = "task_assignment"
    NOTIFICATION = "notification"


class ApprovalPolicy(BaseModel):
    """A rule mapping a matched action to an approval decision.

    ``communication_type`` / ``customer_organization_id`` / ``customer_contact_id`` /
    ``agent_id`` are optional match facets — ``None`` means "any". ``min_authority`` is
    the authority an actor must hold for the decision to apply as-is; below it, an
    ``APPROVE_AUTOMATICALLY`` is downgraded to ``REQUIRE_HUMAN_APPROVAL``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    name: str
    decision: ApprovalDecisionType = ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL
    communication_type: CommunicationType | None = None
    customer_organization_id: uuid.UUID | None = None
    customer_contact_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    min_authority: int = 0
    priority: int = Field(default=100, ge=0)
    enabled: bool = True
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class OutboundAction(BaseModel):
    """A description of an action the agent wants to take, submitted for evaluation."""

    tenant_id: uuid.UUID
    communication_type: CommunicationType
    actor_authority: int = 0
    agent_id: uuid.UUID | None = None
    customer_organization_id: uuid.UUID | None = None
    customer_contact_id: uuid.UUID | None = None
    summary: str = ""
    payload: dict[str, object] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: ApprovalDecisionType
    reason: str
    matched_policy_id: uuid.UUID | None = None

    @property
    def is_automatic(self) -> bool:
        return self.decision is ApprovalDecisionType.APPROVE_AUTOMATICALLY


class ApprovalRequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalRequest(BaseModel):
    """A queued action awaiting a human decision."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    communication_type: CommunicationType
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING
    summary: str = ""
    customer_organization_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
