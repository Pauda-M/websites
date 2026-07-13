"""Database-backed audit sink — persists audit records for compliance queries.

Complements the always-on structured-log sink: this one writes each
:class:`AuditRecord` to ``ws_audit_log`` so security-relevant history is queryable.
Auditing must never break the operation it records, so failures are surfaced by the
``AuditLog`` facade, not raised here.
"""

from __future__ import annotations

from pb_api.integrations.workspace.infrastructure.repositories import AuditRepository
from pb_api.integrations.workspace.security.audit import AuditRecord


class DbAuditSink:
    """An ``AuditSink`` that appends records to the audit-log table."""

    def __init__(self, repository: AuditRepository) -> None:
        self._repo = repository

    async def record(self, entry: AuditRecord) -> None:
        await self._repo.add(entry)
