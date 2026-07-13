"""Workspace application layer — services, workers, and the composition root.

Services depend only on the provider *ports* and repositories, never on a vendor
SDK or another bounded context's internals. The composition root
(:class:`WorkspaceContext`) wires a chosen provider adapter, the repositories, the
Cognitive Core, and the CRM bridge into the services and the HTTP surface.
"""

from pb_api.integrations.workspace.application.worker import WorkspaceSyncWorker
from pb_api.integrations.workspace.application.workspace import WorkspaceContext

__all__ = ["WorkspaceContext", "WorkspaceSyncWorker"]
