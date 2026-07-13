"""Storage capability over Microsoft Graph (SharePoint sites, OneDrive drives)."""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.files import DriveItem, SharePointSite
from pb_api.integrations.workspace.domain.page import Page
from pb_api.integrations.workspace.graph.client import (
    GraphClient,
    parse_graph_datetime,
)
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver


class GraphStorageProvider:
    """Implements :class:`StorageProvider` against SharePoint/OneDrive."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_sites(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> list[SharePointSite]:
        # ``search=*`` returns all sites the identity can enumerate.
        page = await self._client.paginate(
            "/sites",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"search": "*"},
            map_item=lambda item: _to_site(item, tenant_id),
        )
        return list(page.items)

    async def list_items(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DriveItem]:
        return await self._client.paginate(
            f"/drives/{drive_id}/root/children",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size},
            cursor=cursor,
            map_item=lambda item: _to_drive_item(item, tenant_id, drive_id),
        )

    async def download(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        item_provider_id: str,
    ) -> bytes:
        return await self._client.get_content(
            f"/drives/{drive_id}/items/{item_provider_id}/content",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )

    async def upload(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        drive_id: str,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DriveItem:
        clean_path = path.lstrip("/")
        response = await self._client.put_content(
            f"/drives/{drive_id}/root:/{clean_path}:/content",
            tenant_id=tenant_id,
            connection_id=connection_id,
            content=content,
            content_type=content_type,
        )
        return _to_drive_item(response.json(), tenant_id, drive_id)

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
    ) -> Page[DriveItem]:
        user = await self._resolver.default_user(tenant_id, connection_id)
        escaped = query.replace("'", "''")
        return await self._client.paginate(
            f"/users/{user}/drive/root/search(q='{escaped}')",
            tenant_id=tenant_id,
            connection_id=connection_id,
            cursor=cursor,
            map_item=lambda item: _to_drive_item(item, tenant_id, ""),
        )


def _to_site(data: Any, tenant_id: uuid.UUID) -> SharePointSite:
    if not isinstance(data, dict):
        data = {}
    return SharePointSite(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        display_name=str(data.get("displayName") or data.get("name") or ""),
        web_url=_optional_str(data.get("webUrl")),
    )


def _to_drive_item(data: Any, tenant_id: uuid.UUID, drive_id: str) -> DriveItem:
    if not isinstance(data, dict):
        data = {}
    file_facet = data.get("file") if isinstance(data.get("file"), dict) else {}
    parent = data.get("parentReference") if isinstance(data.get("parentReference"), dict) else {}
    resolved_drive = str(parent.get("driveId") or drive_id or "")
    return DriveItem(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        drive_id=resolved_drive,
        name=str(data.get("name", "")),
        is_folder="folder" in data,
        content_type=str(file_facet.get("mimeType", "application/octet-stream")),
        size_bytes=int(data.get("size", 0) or 0),
        web_url=_optional_str(data.get("webUrl")),
        parent_path=str(parent.get("path", "/") or "/"),
        version=_optional_str(data.get("eTag")),
        created_at=parse_graph_datetime(data.get("createdDateTime")) or utcnow(),
        modified_at=parse_graph_datetime(data.get("lastModifiedDateTime")) or utcnow(),
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
