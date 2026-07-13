from __future__ import annotations

import uuid

from pb_api.cognitive.domain.agents import AgentStatus
from pb_api.cognitive.domain.common import AuthorityLevel
from pb_api.cognitive.domain.policy import Policy, PolicyEffect, PolicyRequest
from pb_api.cognitive.domain.tools import SideEffect, ToolHealth
from pb_api.cognitive.services import CognitiveCore


async def test_agent_register_is_idempotent_by_name_and_bumps_version(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    first = await core.agents.register(tenant_id=tenant, name="Sales Manager", role="sales_manager")
    assert first.version == 1
    again = await core.agents.register(
        tenant_id=tenant, name="Sales Manager", role="sales_manager", capabilities=["email.send"]
    )
    assert again.id == first.id
    assert again.version == 2
    assert "email.send" in again.capabilities


async def test_agent_status_transition(core: CognitiveCore, tenant: uuid.UUID) -> None:
    agent = await core.agents.register(tenant_id=tenant, name="Support", role="support")
    updated = await core.agents.set_status(tenant, agent.id, AgentStatus.ACTIVE)
    assert updated is not None
    assert updated.status is AgentStatus.ACTIVE


async def test_tool_register_and_health(core: CognitiveCore, tenant: uuid.UUID) -> None:
    tool = await core.tools.register(
        tenant_id=tenant,
        name="send_email",
        permissions=["email.send"],
        side_effect=SideEffect.EXTERNAL,
        timeout_seconds=15,
    )
    assert tool.health is ToolHealth.UNKNOWN
    assert tool.side_effect is SideEffect.EXTERNAL
    updated = await core.tools.set_health(tenant, tool.id, ToolHealth.HEALTHY)
    assert updated is not None
    assert updated.health is ToolHealth.HEALTHY


async def test_policy_default_deny(core: CognitiveCore, tenant: uuid.UUID) -> None:
    decision = await core.policies.evaluate(
        PolicyRequest(
            tenant_id=tenant, actor_authority=AuthorityLevel.ACT_BROAD, action="email.send"
        )
    )
    assert decision.allowed is False
    assert "default deny" in decision.reason


async def test_policy_allow_and_specificity(core: CognitiveCore, tenant: uuid.UUID) -> None:
    await core.policies.add_policy(
        Policy(
            tenant_id=tenant,
            name="crm-allow",
            action="crm.*",
            effect=PolicyEffect.ALLOW,
            priority=10,
        )
    )
    await core.policies.add_policy(
        Policy(
            tenant_id=tenant,
            name="crm-delete-deny",
            action="crm.delete",
            effect=PolicyEffect.DENY,
            priority=10,
        )
    )
    allow = await core.policies.evaluate(
        PolicyRequest(
            tenant_id=tenant, actor_authority=AuthorityLevel.ACT_BROAD, action="crm.update"
        )
    )
    assert allow.allowed is True
    # More specific deny wins over the broad allow.
    deny = await core.policies.evaluate(
        PolicyRequest(
            tenant_id=tenant, actor_authority=AuthorityLevel.ACT_BROAD, action="crm.delete"
        )
    )
    assert deny.allowed is False
    assert deny.effect is PolicyEffect.DENY


async def test_policy_authority_gate_escalates_to_approval(
    core: CognitiveCore, tenant: uuid.UUID
) -> None:
    await core.policies.add_policy(
        Policy(
            tenant_id=tenant,
            name="high-value",
            action="invoice.approve",
            effect=PolicyEffect.ALLOW,
            min_authority=AuthorityLevel.ACT_BROAD,
        )
    )
    decision = await core.policies.evaluate(
        PolicyRequest(
            tenant_id=tenant, actor_authority=AuthorityLevel.SUGGEST, action="invoice.approve"
        )
    )
    assert decision.allowed is False
    assert decision.requires_approval is True
