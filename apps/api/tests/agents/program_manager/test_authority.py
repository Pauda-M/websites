from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.agents.program_manager.application.authority import (
    ACTION_CATALOG,
    AuthorityService,
    required_authority,
)
from pb_api.agents.program_manager.domain.common import AuthorityLevel, PMAuthorityLevel
from pb_api.cognitive.services import CognitiveCore


def test_pm_tiers_map_onto_cognitive_levels() -> None:
    assert AuthorityService.to_cognitive(PMAuthorityLevel.OBSERVE_ONLY) is AuthorityLevel.OBSERVE
    assert (
        AuthorityService.to_cognitive(PMAuthorityLevel.ACT_WITH_APPROVAL)
        is AuthorityLevel.ACT_WITH_APPROVAL
    )
    assert AuthorityService.to_cognitive(PMAuthorityLevel.ACT_BOUNDED) is AuthorityLevel.ACT_BOUNDED


def test_required_authority_defaults_unknown_actions_to_top_tier() -> None:
    assert required_authority("crm.read") is PMAuthorityLevel.OBSERVE_ONLY
    assert required_authority("communication.send") is PMAuthorityLevel.ACT_BOUNDED
    assert required_authority("totally.unknown") is PMAuthorityLevel.ACT_BOUNDED


async def test_seed_default_policies_is_idempotent(
    session: AsyncSession, tenant: uuid.UUID
) -> None:
    core = CognitiveCore(session)
    authority = AuthorityService(core.policies)
    created = await authority.seed_default_policies(tenant)
    assert len(created) == len(ACTION_CATALOG)
    # Seeding again creates nothing new.
    assert await authority.seed_default_policies(tenant) == []


async def test_authorize_allows_at_or_above_tier_and_escalates_below(
    session: AsyncSession, tenant: uuid.UUID
) -> None:
    core = CognitiveCore(session)
    authority = AuthorityService(core.policies)
    await authority.seed_default_policies(tenant)

    # An L1 actor may take an internal reversible action (crm.update requires L1).
    allow = await authority.authorize(
        tenant_id=tenant, actor_level=PMAuthorityLevel.ACT_WITH_APPROVAL, action="crm.update"
    )
    assert allow.allowed is True

    # The same L1 actor cannot send outward communication (requires L2) — escalates.
    escalate = await authority.authorize(
        tenant_id=tenant,
        actor_level=PMAuthorityLevel.ACT_WITH_APPROVAL,
        action="communication.send",
    )
    assert escalate.allowed is False
    assert escalate.requires_approval is True

    # An L2 actor may send.
    bounded = await authority.authorize(
        tenant_id=tenant, actor_level=PMAuthorityLevel.ACT_BOUNDED, action="communication.send"
    )
    assert bounded.allowed is True


async def test_authorize_denies_unseeded_action_by_default(
    session: AsyncSession, tenant: uuid.UUID
) -> None:
    core = CognitiveCore(session)
    authority = AuthorityService(core.policies)
    # No policies seeded → default deny (secure by default).
    decision = await authority.authorize(
        tenant_id=tenant, actor_level=PMAuthorityLevel.ACT_BOUNDED, action="crm.read"
    )
    assert decision.allowed is False
    assert decision.requires_approval is False
