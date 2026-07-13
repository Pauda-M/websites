"""Directory capability over Microsoft Graph (``/users``, ``/groups``)."""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.directory import (
    DirectoryGroup,
    DirectoryUser,
    GroupType,
)
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.graph.client import GraphClient
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver

_USER_SELECT = (
    "id,displayName,userPrincipalName,mail,jobTitle,department," "officeLocation,accountEnabled"
)


class GraphDirectoryProvider:
    """Implements :class:`DirectoryProvider` against the tenant directory."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryUser]:
        return await self._client.paginate(
            "/users",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size, "$select": _USER_SELECT},
            cursor=cursor,
            map_item=lambda item: _to_user(item, tenant_id),
        )

    async def delta_users(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[DirectoryUser]:
        params = None if (cursor or delta_token) else {"$select": _USER_SELECT}
        return await self._client.delta(
            "/users",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params=params,
            delta_token=delta_token,
            cursor=cursor,
            map_item=lambda item: _to_user(item, tenant_id),
        )

    async def list_groups(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[DirectoryGroup]:
        return await self._client.paginate(
            "/groups",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size},
            cursor=cursor,
            map_item=lambda item: _to_group(item, tenant_id),
        )

    async def get_user(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, user_provider_id: str
    ) -> DirectoryUser | None:
        try:
            response = await self._client.get(
                f"/users/{user_provider_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params={"$select": _USER_SELECT},
            )
        except GraphError as error:
            if error.status_code == 404:
                return None
            raise
        return _to_user(response.json(), tenant_id)


def _to_user(data: Any, tenant_id: uuid.UUID) -> DirectoryUser:
    if not isinstance(data, dict):
        data = {}
    manager = data.get("manager") if isinstance(data.get("manager"), dict) else {}
    return DirectoryUser(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        display_name=str(data.get("displayName", "")),
        user_principal_name=str(data.get("userPrincipalName", "")),
        email=_optional_str(data.get("mail") or data.get("userPrincipalName")),
        job_title=_optional_str(data.get("jobTitle")),
        department=_optional_str(data.get("department")),
        office_location=_optional_str(data.get("officeLocation")),
        manager_provider_id=_optional_str(manager.get("id")),
        account_enabled=bool(data.get("accountEnabled", True)),
    )


def _to_group(data: Any, tenant_id: uuid.UUID) -> DirectoryGroup:
    if not isinstance(data, dict):
        data = {}
    return DirectoryGroup(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        display_name=str(data.get("displayName", "")),
        group_type=_group_type(data),
        description=str(data.get("description", "") or ""),
    )


def _group_type(data: dict[str, Any]) -> GroupType:
    group_types = data.get("groupTypes")
    if isinstance(group_types, list) and "Unified" in group_types:
        return GroupType.MICROSOFT_365
    mail_enabled = bool(data.get("mailEnabled", False))
    security_enabled = bool(data.get("securityEnabled", False))
    if mail_enabled and not security_enabled:
        return GroupType.DISTRIBUTION
    return GroupType.SECURITY


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
