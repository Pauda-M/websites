"""Request/response bodies for the Program Manager HTTP API (Pydantic v2).

There is no tenant authentication in the platform yet, so every write body
carries an explicit ``tenant_id``. Domain enums and models are reused directly so
the wire contract and the domain never drift. Server-assigned identifiers,
versions, timestamps, and computed state are never accepted from clients.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from pb_api.agents.program_manager.domain.common import PMGoalType
from pb_api.agents.program_manager.domain.crm import LeadSource
from pb_api.agents.program_manager.domain.proposal import ProposalSectionKind
from pb_api.agents.program_manager.domain.run import PMRun, PMTriggerType

# --- Bootstrap & lifecycle ---------------------------------------------


class TenantBody(BaseModel):
    tenant_id: uuid.UUID


class BootstrapResponse(BaseModel):
    tenant_id: uuid.UUID
    agent_id: uuid.UUID


class RunRequest(BaseModel):
    tenant_id: uuid.UUID
    trigger: PMTriggerType = PMTriggerType.MANUAL
    input_text: str = ""
    agent_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    goal_type: PMGoalType | None = None


class ApproveRequest(BaseModel):
    tenant_id: uuid.UUID
    approver: str = Field(min_length=1)


class ExecuteDueResponse(BaseModel):
    executed: int
    runs: list[PMRun]


# --- CRM ---------------------------------------------------------------


class OrganizationCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(min_length=1)
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class ContactCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    first_name: str = Field(min_length=1)
    last_name: str = ""
    email: str | None = None
    phone: str | None = None
    title: str | None = None


class LeadCreateRequest(BaseModel):
    tenant_id: uuid.UUID
    source: LeadSource = LeadSource.UNKNOWN
    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    summary: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class LeadConvertRequest(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(min_length=1)
    amount: float = Field(default=0.0, ge=0.0)
    currency: str = "EUR"


# --- Proposals ---------------------------------------------------------


class ProposalDraftRequest(BaseModel):
    tenant_id: uuid.UUID
    organization_id: uuid.UUID
    title: str = Field(min_length=1)
    opportunity_id: uuid.UUID | None = None
    total_value: float = Field(default=0.0, ge=0.0)
    currency: str = "EUR"
    sections: dict[ProposalSectionKind, str] | None = None


class ProposalReadyRequest(BaseModel):
    tenant_id: uuid.UUID
    approved_by: str | None = None
