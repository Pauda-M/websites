"""Workspace domain event type constants.

Reuses the Cognitive Core's immutable ``CognitiveEvent`` envelope and its
append-only ``EventProcessor`` — the workspace never builds a second event store.
This module declares only the workspace event *type* constants, following the
canonical Genesis pattern ``pb.<context>.<aggregate>.<past-verb>``
(`docs/genesis/005_Event_Model.md`). Contexts: ``mail``, ``calendar``, ``contact``,
``directory``, ``document``, ``task``, ``presence``, ``workspace``.
"""

from __future__ import annotations


class WorkspaceEventType:
    """Canonical workspace event type constants."""

    # mail
    MAIL_RECEIVED = "pb.mail.message.received"
    MAIL_DRAFT_CREATED = "pb.mail.draft.created"
    MAIL_SENT = "pb.mail.message.sent"
    MAIL_MOVED = "pb.mail.message.moved"
    MAIL_CATEGORIZED = "pb.mail.message.categorized"

    # calendar
    MEETING_CREATED = "pb.calendar.meeting.created"
    MEETING_UPDATED = "pb.calendar.meeting.updated"
    MEETING_CANCELLED = "pb.calendar.meeting.cancelled"
    MEETING_ACCEPTED = "pb.calendar.meeting.accepted"
    MEETING_DECLINED = "pb.calendar.meeting.declined"

    # contacts / directory
    CONTACT_UPDATED = "pb.contact.contact.updated"
    DIRECTORY_USER_UPDATED = "pb.directory.user.updated"
    DIRECTORY_GROUP_UPDATED = "pb.directory.group.updated"

    # documents / knowledge
    DOCUMENT_INDEXED = "pb.document.document.indexed"

    # tasks
    TASK_CREATED = "pb.task.task.created"
    TASK_COMPLETED = "pb.task.task.completed"

    # presence
    PRESENCE_CHANGED = "pb.presence.presence.changed"

    # workspace lifecycle / sync / approval
    CONNECTION_ESTABLISHED = "pb.workspace.connection.established"
    SYNC_COMPLETED = "pb.workspace.sync.completed"
    SYNC_FAILED = "pb.workspace.sync.failed"
    APPROVAL_REQUESTED = "pb.workspace.approval.requested"
    APPROVAL_GRANTED = "pb.workspace.approval.granted"
    APPROVAL_REJECTED = "pb.workspace.approval.rejected"
    NOTIFICATION_SENT = "pb.workspace.notification.sent"
