"""Approval engine — governs every outbound workspace action (manifesto: Autonomy).

Every action that leaves the building is evaluated here before it is performed.
Evaluation is deterministic: among enabled policies that match the action's facets
(communication type, customer organization, customer contact, agent), the most
specific + highest-priority rule wins; ties resolve to the most restrictive
decision. An ``APPROVE_AUTOMATICALLY`` whose ``min_authority`` exceeds the actor's
authority is downgraded to ``REQUIRE_HUMAN_APPROVAL`` — autonomy never silently
exceeds its bound. With no matching policy the engine is conservative and requires
human approval (secure by default).
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.cognitive.services.event_processor import EventProcessor
from pb_api.integrations.workspace.domain.approval import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalRequestStatus,
    CommunicationType,
    OutboundAction,
)
from pb_api.integrations.workspace.domain.common import ApprovalDecisionType, utcnow
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.infrastructure.repositories import (
    ApprovalPolicyRepository,
    ApprovalRequestRepository,
)
from pb_api.integrations.workspace.security.audit import AuditLog

# Most-restrictive-first ordering, used to break ties between equally-ranked rules.
_RESTRICTIVENESS = {
    ApprovalDecisionType.REJECT: 3,
    ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL: 2,
    ApprovalDecisionType.CREATE_DRAFT: 1,
    ApprovalDecisionType.APPROVE_AUTOMATICALLY: 0,
}


def _matches(policy: ApprovalPolicy, action: OutboundAction) -> bool:
    if (
        policy.communication_type is not None
        and policy.communication_type != action.communication_type
    ):
        return False
    if (
        policy.customer_organization_id is not None
        and policy.customer_organization_id != action.customer_organization_id
    ):
        return False
    if (
        policy.customer_contact_id is not None
        and policy.customer_contact_id != action.customer_contact_id
    ):
        return False
    return not (policy.agent_id is not None and policy.agent_id != action.agent_id)


def _specificity(policy: ApprovalPolicy) -> int:
    return sum(
        facet is not None
        for facet in (
            policy.communication_type,
            policy.customer_organization_id,
            policy.customer_contact_id,
            policy.agent_id,
        )
    )


class ApprovalEngine:
    def __init__(
        self,
        policies: ApprovalPolicyRepository,
        requests: ApprovalRequestRepository,
        events: EventProcessor,
        audit: AuditLog,
    ) -> None:
        self._policies = policies
        self._requests = requests
        self._events = events
        self._audit = audit

    async def add_policy(self, policy: ApprovalPolicy) -> ApprovalPolicy:
        return await self._policies.add(policy)

    async def list_policies(self, tenant_id: uuid.UUID) -> builtins.list[ApprovalPolicy]:
        return await self._policies.list(tenant_id, enabled_only=False)

    async def seed_default_policies(self, tenant_id: uuid.UUID) -> builtins.list[ApprovalPolicy]:
        """Install a conservative default policy set if none exists.

        Read-like categories are not outbound; the outbound defaults require human
        approval, except low-risk meeting responses which are drafted for review.
        Idempotent: does nothing if the tenant already has policies.
        """
        if await self._policies.list(tenant_id, enabled_only=False):
            return []
        created: builtins.list[ApprovalPolicy] = []
        created.append(
            await self._policies.add(
                ApprovalPolicy(
                    tenant_id=tenant_id,
                    name="default-require-approval",
                    decision=ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL,
                    priority=10,
                    description="Fallback: all outbound actions require human approval.",
                )
            )
        )
        created.append(
            await self._policies.add(
                ApprovalPolicy(
                    tenant_id=tenant_id,
                    name="default-draft-replies",
                    decision=ApprovalDecisionType.CREATE_DRAFT,
                    communication_type=CommunicationType.MAIL_REPLY,
                    priority=20,
                    description="Draft mail replies for human review by default.",
                )
            )
        )
        return created

    async def evaluate(self, action: OutboundAction) -> ApprovalDecision:
        candidates = [
            policy
            for policy in await self._policies.list(action.tenant_id, enabled_only=True)
            if _matches(policy, action)
        ]
        if not candidates:
            return ApprovalDecision(
                decision=ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL,
                reason="No matching approval policy; requiring human approval.",
            )

        def rank(policy: ApprovalPolicy) -> tuple[int, int, int]:
            return (policy.priority, _specificity(policy), _RESTRICTIVENESS[policy.decision])

        winner = max(candidates, key=rank)
        decision = winner.decision
        reason = f"Policy '{winner.name}' → {decision.value}."
        if (
            decision is ApprovalDecisionType.APPROVE_AUTOMATICALLY
            and action.actor_authority < winner.min_authority
        ):
            decision = ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL
            reason = (
                f"Policy '{winner.name}' auto-approves, but actor authority "
                f"{action.actor_authority} is below required {winner.min_authority}; "
                "requiring human approval."
            )
        return ApprovalDecision(decision=decision, reason=reason, matched_policy_id=winner.id)

    async def submit(
        self, action: OutboundAction
    ) -> tuple[ApprovalDecision, ApprovalRequest | None]:
        """Evaluate and, when a human must decide, enqueue an approval request."""
        decision = await self.evaluate(action)
        await self._audit.emit(
            action.tenant_id,
            "approval.evaluated",
            resource=action.communication_type.value,
            outcome=decision.decision.value,
            detail={"reason": decision.reason},
        )
        request: ApprovalRequest | None = None
        if decision.decision in (
            ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL,
            ApprovalDecisionType.CREATE_DRAFT,
        ):
            request = await self._requests.add(
                ApprovalRequest(
                    tenant_id=action.tenant_id,
                    communication_type=action.communication_type,
                    summary=action.summary,
                    customer_organization_id=action.customer_organization_id,
                    agent_id=action.agent_id,
                    payload=action.payload,
                )
            )
            await self._events.record(
                event_type=WorkspaceEventType.APPROVAL_REQUESTED,
                tenant_id=action.tenant_id,
                aggregate_id=request.id,
                payload={"communication_type": action.communication_type.value},
            )
        elif decision.decision is ApprovalDecisionType.REJECT:
            await self._events.record(
                event_type=WorkspaceEventType.APPROVAL_REJECTED,
                tenant_id=action.tenant_id,
                payload={"reason": decision.reason},
            )
        return decision, request

    async def list_pending(self, tenant_id: uuid.UUID) -> builtins.list[ApprovalRequest]:
        return await self._requests.list(tenant_id, status=ApprovalRequestStatus.PENDING)

    async def decide(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, *, approve: bool, decided_by: str
    ) -> ApprovalRequest | None:
        request = await self._requests.get(tenant_id, request_id)
        if request is None or request.status is not ApprovalRequestStatus.PENDING:
            return request
        request.status = (
            ApprovalRequestStatus.APPROVED if approve else ApprovalRequestStatus.REJECTED
        )
        request.decided_by = decided_by
        request.decided_at = utcnow()
        updated = await self._requests.update(request)
        await self._events.record(
            event_type=(
                WorkspaceEventType.APPROVAL_GRANTED
                if approve
                else WorkspaceEventType.APPROVAL_REJECTED
            ),
            tenant_id=tenant_id,
            aggregate_id=request_id,
            payload={"decided_by": decided_by},
        )
        await self._audit.emit(
            tenant_id,
            "approval.decided",
            actor=decided_by,
            resource=str(request_id),
            outcome="approved" if approve else "rejected",
        )
        return updated
