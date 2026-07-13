"""Contacts domain — people and organizations synchronized from the workspace."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class PostalAddress(BaseModel):
    street: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""


class WorkspaceContact(BaseModel):
    """A person synchronized from the provider's contacts/directory."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    display_name: str
    given_name: str = ""
    surname: str = ""
    email: str | None = None
    phones: list[str] = Field(default_factory=list)
    title: str | None = None
    department: str | None = None
    company: str | None = None
    addresses: list[PostalAddress] = Field(default_factory=list)
    crm_contact_id: uuid.UUID | None = None  # link into the PM CRM once matched
    crm_organization_id: uuid.UUID | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)
