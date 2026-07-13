"""Microsoft Graph adapter — the primary implementation of the workspace ports.

This package is the *only* place in the workspace integration that speaks HTTP to a
vendor. :class:`GraphWorkspaceProvider` implements the ``WorkspaceProvider``
aggregate port; :class:`GraphClient` centralizes auth, rate limiting, retries, and
Graph's pagination/delta idioms; :class:`GraphTokenProvider` implements the
``TokenProvider`` port (client-credentials and delegated refresh-token flows); and
:class:`GraphResourceResolver` maps a connection to the mailbox/drive/user its
requests address.
"""

from __future__ import annotations

from pb_api.integrations.workspace.graph.auth import GraphTokenProvider
from pb_api.integrations.workspace.graph.client import GraphClient
from pb_api.integrations.workspace.graph.errors import GraphAuthError, GraphError
from pb_api.integrations.workspace.graph.provider import GraphWorkspaceProvider
from pb_api.integrations.workspace.graph.rate_limit import AsyncRateLimiter
from pb_api.integrations.workspace.graph.resolver import (
    GraphResourceResolver,
    ResourceBinding,
    StaticGraphResolver,
)

__all__ = [
    "AsyncRateLimiter",
    "GraphAuthError",
    "GraphClient",
    "GraphError",
    "GraphResourceResolver",
    "GraphTokenProvider",
    "GraphWorkspaceProvider",
    "ResourceBinding",
    "StaticGraphResolver",
]
