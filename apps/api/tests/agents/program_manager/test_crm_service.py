from __future__ import annotations

import uuid

import pytest

from pb_api.agents.program_manager.application import ProgramManager
from pb_api.agents.program_manager.domain.crm import LeadSource, LeadStatus, OpportunityStage


async def test_create_organization_and_clamp_scores(pm: ProgramManager, tenant: uuid.UUID) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Acme", importance_score=1.5)
    # importance is clamped into [0, 1].
    assert org.importance_score == 1.0
    updated = await pm.crm.adjust_scores(
        tenant, org.id, relationship_delta=0.6, trust_delta=-2.0, reason="test"
    )
    assert updated is not None
    assert updated.relationship_score == pytest.approx(min(1.0, 0.5 + 0.6))
    assert updated.trust_score == 0.0  # clamped at the floor


async def test_convert_lead_creates_opportunity_and_links_back(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Beta")
    lead = await pm.crm.create_lead(
        tenant_id=tenant, source=LeadSource.REFERRAL, organization_id=org.id, summary="interested"
    )
    opp = await pm.crm.convert_lead(tenant, lead.id, name="Beta Deal", amount=5000.0)
    assert opp.organization_id == org.id
    assert opp.lead_id == lead.id
    reloaded = await pm.crm.get_lead(tenant, lead.id)
    assert reloaded is not None
    assert reloaded.status is LeadStatus.CONVERTED
    assert reloaded.opportunity_id == opp.id


async def test_convert_lead_requires_organization_and_rejects_double_convert(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    orgless = await pm.crm.create_lead(tenant_id=tenant, source=LeadSource.WEBSITE)
    with pytest.raises(ValueError, match="no organization"):
        await pm.crm.convert_lead(tenant, orgless.id, name="X")

    org = await pm.crm.create_organization(tenant_id=tenant, name="Gamma")
    lead = await pm.crm.create_lead(tenant_id=tenant, organization_id=org.id)
    await pm.crm.convert_lead(tenant, lead.id, name="Gamma Deal")
    with pytest.raises(ValueError, match="already converted"):
        await pm.crm.convert_lead(tenant, lead.id, name="Gamma Deal 2")


async def test_advance_opportunity_sets_probability_on_close(
    pm: ProgramManager, tenant: uuid.UUID
) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Delta")
    opp = await pm.crm.create_opportunity(
        tenant_id=tenant, organization_id=org.id, name="Delta Deal", amount=1000.0
    )
    won = await pm.crm.advance_opportunity(tenant, opp.id, stage=OpportunityStage.CLOSED_WON)
    assert won is not None
    assert won.stage is OpportunityStage.CLOSED_WON
    assert won.probability == 1.0


async def test_crm_is_tenant_isolated(
    pm: ProgramManager, tenant: uuid.UUID, other_tenant: uuid.UUID
) -> None:
    org = await pm.crm.create_organization(tenant_id=tenant, name="Owned")
    assert await pm.crm.get_organization(other_tenant, org.id) is None
    assert await pm.crm.list_organizations(other_tenant) == []
