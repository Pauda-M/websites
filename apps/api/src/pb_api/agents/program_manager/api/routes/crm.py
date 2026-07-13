"""CRM routes: organizations, contacts, leads (and lead conversion), opportunities."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pb_api.agents.program_manager.api.deps import PMDep
from pb_api.agents.program_manager.api.schemas import (
    ContactCreateRequest,
    LeadConvertRequest,
    LeadCreateRequest,
    OrganizationCreateRequest,
)
from pb_api.agents.program_manager.domain.crm import (
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    Organization,
    OrganizationStatus,
)

router = APIRouter(prefix="/crm", tags=["program-manager-crm"])


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreateRequest, pm: PMDep) -> Organization:
    return await pm.crm.create_organization(
        tenant_id=body.tenant_id,
        name=body.name,
        domain=body.domain,
        industry=body.industry,
        size=body.size,
        importance_score=body.importance_score,
    )


@router.get("/organizations")
async def list_organizations(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[OrganizationStatus | None, Query(alias="status")] = None,
) -> list[Organization]:
    return await pm.crm.list_organizations(tenant_id, status=status_filter)


@router.get("/organizations/{organization_id}")
async def get_organization(
    organization_id: uuid.UUID, pm: PMDep, tenant_id: Annotated[uuid.UUID, Query()]
) -> Organization:
    org = await pm.crm.get_organization(tenant_id, organization_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="organization not found")
    return org


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def create_contact(body: ContactCreateRequest, pm: PMDep) -> Contact:
    return await pm.crm.create_contact(
        tenant_id=body.tenant_id,
        organization_id=body.organization_id,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        title=body.title,
    )


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadCreateRequest, pm: PMDep) -> Lead:
    return await pm.crm.create_lead(
        tenant_id=body.tenant_id,
        source=body.source,
        organization_id=body.organization_id,
        contact_id=body.contact_id,
        summary=body.summary,
        score=body.score,
    )


@router.get("/leads")
async def list_leads(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[LeadStatus | None, Query(alias="status")] = None,
) -> list[Lead]:
    return await pm.crm.list_leads(tenant_id, status=status_filter)


@router.post("/leads/{lead_id}/convert", status_code=status.HTTP_201_CREATED)
async def convert_lead(lead_id: uuid.UUID, body: LeadConvertRequest, pm: PMDep) -> Opportunity:
    try:
        return await pm.crm.convert_lead(
            body.tenant_id, lead_id, name=body.name, amount=body.amount, currency=body.currency
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/opportunities")
async def list_opportunities(
    pm: PMDep,
    tenant_id: Annotated[uuid.UUID, Query()],
    stage: Annotated[OpportunityStage | None, Query()] = None,
) -> list[Opportunity]:
    return await pm.crm.list_opportunities(tenant_id, stage=stage)
