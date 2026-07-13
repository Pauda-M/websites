"""Contacts capability over Microsoft Graph (``/users/{mailbox}/contacts``)."""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.contacts import PostalAddress, WorkspaceContact
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.graph.client import GraphClient
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver


class GraphContactsProvider:
    """Implements :class:`ContactsProvider` against a Graph mailbox's contacts."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceContact]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.paginate(
            f"/users/{mailbox}/contacts",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size},
            cursor=cursor,
            map_item=lambda item: _to_contact(item, tenant_id),
        )

    async def delta_contacts(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceContact]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.delta(
            f"/users/{mailbox}/contacts",
            tenant_id=tenant_id,
            connection_id=connection_id,
            delta_token=delta_token,
            cursor=cursor,
            map_item=lambda item: _to_contact(item, tenant_id),
        )

    async def upsert_contact(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, contact: WorkspaceContact
    ) -> str:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        body = _contact_body(contact)
        if contact.provider_id:
            response = await self._client.patch(
                f"/users/{mailbox}/contacts/{contact.provider_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
                json=body,
            )
        else:
            response = await self._client.post(
                f"/users/{mailbox}/contacts",
                tenant_id=tenant_id,
                connection_id=connection_id,
                json=body,
            )
        return str(response.json().get("id", contact.provider_id))


def _contact_body(contact: WorkspaceContact) -> dict[str, Any]:
    body: dict[str, Any] = {
        "displayName": contact.display_name,
        "givenName": contact.given_name,
        "surname": contact.surname,
        "businessPhones": contact.phones,
    }
    if contact.email:
        body["emailAddresses"] = [
            {"address": contact.email, "name": contact.display_name},
        ]
    if contact.title:
        body["jobTitle"] = contact.title
    if contact.department:
        body["department"] = contact.department
    if contact.company:
        body["companyName"] = contact.company
    if contact.addresses:
        first = contact.addresses[0]
        body["businessAddress"] = {
            "street": first.street,
            "city": first.city,
            "state": first.state,
            "postalCode": first.postal_code,
            "countryOrRegion": first.country,
        }
    return body


def _to_contact(data: Any, tenant_id: uuid.UUID) -> WorkspaceContact:
    if not isinstance(data, dict):
        data = {}
    emails = data.get("emailAddresses")
    email: str | None = None
    if isinstance(emails, list) and emails and isinstance(emails[0], dict):
        email = _optional_str(emails[0].get("address"))
    phones = [
        str(phone)
        for phone in (_as_list(data.get("businessPhones")) + _as_list(data.get("homePhones")))
    ]
    mobile = data.get("mobilePhone")
    if isinstance(mobile, str) and mobile:
        phones.append(mobile)
    return WorkspaceContact(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        display_name=str(data.get("displayName", "")),
        given_name=str(data.get("givenName", "") or ""),
        surname=str(data.get("surname", "") or ""),
        email=email,
        phones=phones,
        title=_optional_str(data.get("jobTitle")),
        department=_optional_str(data.get("department")),
        company=_optional_str(data.get("companyName")),
        addresses=_to_addresses(data),
    )


def _to_addresses(data: dict[str, Any]) -> list[PostalAddress]:
    addresses: list[PostalAddress] = []
    for key in ("businessAddress", "homeAddress", "otherAddress"):
        raw = data.get(key)
        if isinstance(raw, dict) and raw:
            addresses.append(
                PostalAddress(
                    street=str(raw.get("street", "") or ""),
                    city=str(raw.get("city", "") or ""),
                    state=str(raw.get("state", "") or ""),
                    postal_code=str(raw.get("postalCode", "") or ""),
                    country=str(raw.get("countryOrRegion", "") or ""),
                )
            )
    return addresses


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
