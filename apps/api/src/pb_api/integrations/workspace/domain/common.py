"""Shared workspace domain primitives and enumerations.

Provider-agnostic: nothing here knows about Microsoft Graph. Time and identity
helpers are reused from the Cognitive Core so workspace data shares the platform's
identity/time semantics.
"""

from __future__ import annotations

import enum

from pb_api.cognitive.domain.common import (
    ensure_aware,
    new_id,
    utcnow,
)

__all__ = [
    "ApprovalDecisionType",
    "AttachmentDisposition",
    "MessagePriority",
    "Provider",
    "SyncResource",
    "SyncStatus",
    "WorkspaceScope",
    "ensure_aware",
    "new_id",
    "utcnow",
]


class Provider(enum.StrEnum):
    """A workspace provider (vendor). Adapters register under one of these."""

    MICROSOFT_GRAPH = "microsoft_graph"
    IN_MEMORY = "in_memory"
    GOOGLE_WORKSPACE = "google_workspace"  # reserved for a future adapter


class MessagePriority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AttachmentDisposition(enum.StrEnum):
    INLINE = "inline"
    ATTACHMENT = "attachment"


class SyncResource(enum.StrEnum):
    """A resource kind that supports incremental / delta synchronization."""

    MAIL = "mail"
    CALENDAR = "calendar"
    CONTACTS = "contacts"
    DIRECTORY_USERS = "directory_users"
    DIRECTORY_GROUPS = "directory_groups"
    FILES = "files"
    TASKS = "tasks"


class SyncStatus(enum.StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApprovalDecisionType(enum.StrEnum):
    """The four possible rulings of the approval engine."""

    APPROVE_AUTOMATICALLY = "approve_automatically"
    CREATE_DRAFT = "create_draft"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    REJECT = "reject"


class WorkspaceScope(enum.StrEnum):
    """Least-privilege scope classes an operation may require."""

    READ = "read"
    WRITE = "write"
    SEND = "send"
    ADMIN = "admin"
