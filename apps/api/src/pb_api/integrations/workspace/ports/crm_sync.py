"""CRM-sync port.

The manifesto forbids one bounded context reaching into another's internals. The
workspace must "update CRM" on every email, but it must not import the Program
Manager's services directly. It depends on this narrow port; an adapter at the
composition boundary wires it to the Program Manager's ``CrmService``. A no-op
implementation exists for deployments that run the workspace without the CRM.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class CustomerRef(BaseModel):
    """A resolved link into the CRM."""

    organization_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


@runtime_checkable
class CrmSyncPort(Protocol):
    """What the workspace needs from the CRM — nothing more."""

    async def identify_customer(self, tenant_id: uuid.UUID, *, email: str) -> CustomerRef | None:
        """Resolve an email address to an existing CRM organization/contact."""
        ...

    async def ensure_customer(
        self,
        tenant_id: uuid.UUID,
        *,
        email: str,
        display_name: str = "",
        company: str | None = None,
    ) -> CustomerRef:
        """Find or create the organization/contact for an inbound correspondent."""
        ...

    async def record_interaction(
        self,
        tenant_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None,
        summary: str,
        actor: str = "workspace",
    ) -> None:
        """Record an interaction (e.g. an email) against the customer in the CRM."""
        ...
