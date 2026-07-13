"""Resolves a connection to the Graph resource identifiers its requests address.

Application permissions cannot use the ``/me`` shortcut, so every mailbox/drive
path must name a concrete user or drive. :class:`GraphResourceResolver` abstracts
"which mailbox/drive/user does this connection act as" so providers stay free of
directory look-ups. :class:`StaticGraphResolver` satisfies it from an in-memory
mapping, letting the whole adapter run without a database.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pb_api.integrations.workspace.graph.errors import GraphError


@dataclass(frozen=True)
class ResourceBinding:
    """The Graph resource identifiers a single connection operates on.

    ``mailbox`` and ``default_user`` are user identifiers (object id or UPN);
    ``drive_id`` is the id of the connection's primary drive (may be empty when the
    connection does not use file storage). ``default_user`` falls back to
    ``mailbox`` when left blank.
    """

    mailbox: str
    drive_id: str = ""
    default_user: str = ""

    def user(self) -> str:
        return self.default_user or self.mailbox


@runtime_checkable
class GraphResourceResolver(Protocol):
    """Maps a ``(tenant, connection)`` to its Graph mailbox/drive/user."""

    async def mailbox(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str: ...

    async def drive(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str: ...

    async def default_user(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str: ...


class StaticGraphResolver:
    """A :class:`GraphResourceResolver` backed by a fixed in-memory mapping.

    Bindings are keyed by ``connection_id``; a ``default`` binding is used for any
    connection not present in the mapping. Constructing with only a ``default`` is
    enough for single-connection deployments and tests.
    """

    def __init__(
        self,
        bindings: Mapping[uuid.UUID, ResourceBinding] | None = None,
        *,
        default: ResourceBinding | None = None,
    ) -> None:
        self._bindings: dict[uuid.UUID, ResourceBinding] = dict(bindings or {})
        self._default = default

    def _resolve(self, connection_id: uuid.UUID) -> ResourceBinding:
        binding = self._bindings.get(connection_id, self._default)
        if binding is None:
            raise GraphError(
                f"no Graph resource binding configured for connection {connection_id}",
                status_code=400,
                code="ResourceBindingMissing",
            )
        return binding

    async def mailbox(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        return self._resolve(connection_id).mailbox

    async def drive(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        binding = self._resolve(connection_id)
        if not binding.drive_id:
            raise GraphError(
                f"no drive configured for connection {connection_id}",
                status_code=400,
                code="DriveBindingMissing",
            )
        return binding.drive_id

    async def default_user(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
        return self._resolve(connection_id).user()
