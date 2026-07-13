"""Files domain — SharePoint sites/libraries and OneDrive/Drive documents."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pb_api.integrations.workspace.domain.common import new_id, utcnow


class DriveItem(BaseModel):
    """A file or folder in a drive (OneDrive or a SharePoint document library)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    drive_id: str
    name: str
    is_folder: bool = False
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    web_url: str | None = None
    parent_path: str = "/"
    version: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    modified_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)


class SharePointSite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    provider_id: str
    display_name: str
    web_url: str | None = None
    drive_ids: list[str] = Field(default_factory=list)


class IndexedDocument(BaseModel):
    """A document ingested into the knowledge index.

    ``embedding`` is a deterministic feature-hash vector (the same portable
    representation the Cognitive Core uses); ``chunk_index`` supports chunked docs.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    drive_item_provider_id: str
    title: str
    text: str
    chunk_index: int = 0
    web_url: str | None = None
    embedding: list[float] = Field(default_factory=list)
    indexed_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, object] = Field(default_factory=dict)
