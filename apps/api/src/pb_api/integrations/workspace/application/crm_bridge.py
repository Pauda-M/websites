"""CRM bridge — implements the workspace ``CrmSyncPort`` over the Program Manager.

This adapter lives at the composition boundary between two bounded contexts. The
workspace's business logic depends only on :class:`CrmSyncPort`; this class wires
that port to the Program Manager's ``CrmService`` public API. The workspace never
imports Program-Manager internals, satisfying the manifesto's rule that no module
reach into another's implementation.
"""

from __future__ import annotations

import uuid

from pb_api.agents.program_manager.application.crm_service import CrmService
from pb_api.integrations.workspace.ports.crm_sync import CustomerRef


class ProgramManagerCrmBridge:
    """A ``CrmSyncPort`` backed by the Program Manager's CRM."""

    def __init__(self, crm: CrmService) -> None:
        self._crm = crm

    async def identify_customer(self, tenant_id: uuid.UUID, *, email: str) -> CustomerRef | None:
        needle = email.strip().lower()
        if not needle:
            return None
        for contact in await self._crm.list_contacts(tenant_id):
            if contact.email and contact.email.strip().lower() == needle:
                return CustomerRef(organization_id=contact.organization_id, contact_id=contact.id)
        return None

    async def ensure_customer(
        self,
        tenant_id: uuid.UUID,
        *,
        email: str,
        display_name: str = "",
        company: str | None = None,
    ) -> CustomerRef:
        existing = await self.identify_customer(tenant_id, email=email)
        if existing is not None:
            return existing
        org_name = company or _org_name_from_email(email)
        organization = await self._crm.create_organization(tenant_id=tenant_id, name=org_name)
        first, last = _split_name(display_name or email.split("@", 1)[0])
        contact = await self._crm.create_contact(
            tenant_id=tenant_id,
            organization_id=organization.id,
            first_name=first,
            last_name=last,
            email=email,
        )
        return CustomerRef(organization_id=organization.id, contact_id=contact.id)

    async def record_interaction(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None,
        summary: str,
        actor: str = "workspace",
    ) -> None:
        if organization_id is None:
            return
        await self._crm.record_note(
            tenant_id=tenant_id,
            author=actor,
            body=summary,
            organization_id=organization_id,
        )


def _org_name_from_email(email: str) -> str:
    domain = email.split("@", 1)[-1] if "@" in email else email
    label = domain.split(".", 1)[0] if domain else email
    return label.capitalize() or email


def _split_name(display_name: str) -> tuple[str, str]:
    parts = display_name.strip().split()
    if not parts:
        return "Unknown", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])
