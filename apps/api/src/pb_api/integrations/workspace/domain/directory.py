"""Directory domain — users, groups, and the reporting structure of the tenant."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class DirectoryUser(BaseModel):
    """A member of the customer's own organization (their staff)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    display_name: str
    user_principal_name: str
    email: str | None = None
    job_title: str | None = None
    department: str | None = None
    office_location: str | None = None
    manager_provider_id: str | None = None
    account_enabled: bool = True
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)


class GroupType(enum.StrEnum):
    SECURITY = "security"
    MICROSOFT_365 = "microsoft_365"
    DISTRIBUTION = "distribution"


class DirectoryGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    display_name: str
    group_type: GroupType = GroupType.SECURITY
    description: str = ""
    member_provider_ids: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
