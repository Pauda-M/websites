"""In-memory workspace adapter — a first-class alternate provider backend.

This package implements every port in ``ports/providers.py`` against a
process-local :class:`InMemoryStore`, exactly the way ``MemoryRateLimiter`` is a
real alternative to ``RedisRateLimiter``. It is not a mock: pagination, delta
synchronization (with tombstones), mailbox/calendar mutations, availability,
storage, tasks, presence, notifications, and webhook subscriptions all behave
faithfully. It powers development, air-gapped operation, and tests without any
network or Microsoft Graph dependency.

Compose an :class:`InMemoryWorkspaceProvider` over an :class:`InMemoryStore`,
seed the store, and reach every capability through the aggregate's properties.
"""

from pb_api.integrations.workspace.local.providers import (
    InMemoryCalendarProvider,
    InMemoryContactsProvider,
    InMemoryDirectoryProvider,
    InMemoryMailProvider,
    InMemoryMeetingProvider,
    InMemoryNotificationProvider,
    InMemoryPresenceProvider,
    InMemoryStorageProvider,
    InMemoryTaskProvider,
    InMemoryWorkspaceProvider,
)
from pb_api.integrations.workspace.local.store import (
    ConnectionData,
    InMemoryStore,
    ResourceVersion,
    new_provider_id,
)

__all__ = [
    "ConnectionData",
    "InMemoryCalendarProvider",
    "InMemoryContactsProvider",
    "InMemoryDirectoryProvider",
    "InMemoryMailProvider",
    "InMemoryMeetingProvider",
    "InMemoryNotificationProvider",
    "InMemoryPresenceProvider",
    "InMemoryStorageProvider",
    "InMemoryStore",
    "InMemoryTaskProvider",
    "InMemoryWorkspaceProvider",
    "ResourceVersion",
    "new_provider_id",
]
