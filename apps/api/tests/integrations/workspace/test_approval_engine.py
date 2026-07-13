from __future__ import annotations

import uuid

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.approval import (
    ApprovalPolicy,
    ApprovalRequestStatus,
    CommunicationType,
    OutboundAction,
)
from pb_api.integrations.workspace.domain.common import ApprovalDecisionType


async def test_default_deny_requires_human_approval(
    ctx: WorkspaceContext, tenant: uuid.UUID
) -> None:
    decision = await ctx.approvals.evaluate(
        OutboundAction(tenant_id=tenant, communication_type=CommunicationType.MAIL_REPLY)
    )
    assert decision.decision is ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL


async def test_seed_defaults_drafts_replies(ctx: WorkspaceContext, tenant: uuid.UUID) -> None:
    created = await ctx.approvals.seed_default_policies(tenant)
    assert created
    assert await ctx.approvals.seed_default_policies(tenant) == []  # idempotent
    decision = await ctx.approvals.evaluate(
        OutboundAction(tenant_id=tenant, communication_type=CommunicationType.MAIL_REPLY)
    )
    assert decision.decision is ApprovalDecisionType.CREATE_DRAFT


async def test_more_specific_policy_wins(ctx: WorkspaceContext, tenant: uuid.UUID) -> None:
    org = uuid.uuid4()
    await ctx.approvals.add_policy(
        ApprovalPolicy(
            tenant_id=tenant,
            name="general-approval",
            decision=ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL,
            priority=10,
        )
    )
    await ctx.approvals.add_policy(
        ApprovalPolicy(
            tenant_id=tenant,
            name="trusted-customer-auto",
            decision=ApprovalDecisionType.APPROVE_AUTOMATICALLY,
            communication_type=CommunicationType.MAIL_REPLY,
            customer_organization_id=org,
            priority=10,
        )
    )
    decision = await ctx.approvals.evaluate(
        OutboundAction(
            tenant_id=tenant,
            communication_type=CommunicationType.MAIL_REPLY,
            customer_organization_id=org,
        )
    )
    assert decision.decision is ApprovalDecisionType.APPROVE_AUTOMATICALLY


async def test_authority_below_minimum_downgrades_auto_approve(
    ctx: WorkspaceContext, tenant: uuid.UUID
) -> None:
    await ctx.approvals.add_policy(
        ApprovalPolicy(
            tenant_id=tenant,
            name="auto-with-authority",
            decision=ApprovalDecisionType.APPROVE_AUTOMATICALLY,
            communication_type=CommunicationType.MAIL_REPLY,
            min_authority=2,
            priority=50,
        )
    )
    decision = await ctx.approvals.evaluate(
        OutboundAction(
            tenant_id=tenant,
            communication_type=CommunicationType.MAIL_REPLY,
            actor_authority=0,
        )
    )
    assert decision.decision is ApprovalDecisionType.REQUIRE_HUMAN_APPROVAL


async def test_submit_enqueues_and_decide_resolves(
    ctx: WorkspaceContext, tenant: uuid.UUID
) -> None:
    await ctx.approvals.seed_default_policies(tenant)
    decision, request = await ctx.approvals.submit(
        OutboundAction(
            tenant_id=tenant,
            communication_type=CommunicationType.MAIL_REPLY,
            summary="reply to jane",
        )
    )
    assert decision.decision is ApprovalDecisionType.CREATE_DRAFT
    assert request is not None
    pending = await ctx.approvals.list_pending(tenant)
    assert len(pending) == 1
    resolved = await ctx.approvals.decide(tenant, request.id, approve=True, decided_by="alice@pb")
    assert resolved is not None
    assert resolved.status is ApprovalRequestStatus.APPROVED
    assert await ctx.approvals.list_pending(tenant) == []
    # The grant is auditable via the event log.
    granted = await ctx.core.events.history(tenant, event_type="pb.workspace.approval.granted")
    assert len(granted) == 1
