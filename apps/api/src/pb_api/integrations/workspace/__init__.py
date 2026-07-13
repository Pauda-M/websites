"""Enterprise Digital Workspace integration (Epic 009).

Makes Genesis an active digital employee inside the customer's collaboration
tools — mailbox, calendar, contacts, directory, Teams, SharePoint/OneDrive, and
tasks — while remaining provider-agnostic. Business logic depends only on the
provider *ports* (`ports/`); Microsoft Graph is the primary *adapter* (`graph/`),
and a fully-functional in-memory adapter (`local/`) supports development,
air-gapped operation, and tests. Every workspace activity becomes an immutable
Genesis event and updates memory and CRM; every outbound action passes the
approval engine before it leaves the building.

The composition root is :class:`WorkspaceContext`; the HTTP surface is
:data:`workspace_router`.
"""

from pb_api.integrations.workspace.application.workspace import WorkspaceContext

__all__ = ["WorkspaceContext"]
