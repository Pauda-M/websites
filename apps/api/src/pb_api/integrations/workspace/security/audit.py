"""Audit logging.

Security-relevant actions — credential access, permission checks, outbound actions,
approval decisions — are recorded as immutable :class:`AuditRecord`s through an
:class:`AuditSink` port. The always-available :class:`StructlogAuditSink` emits a
structured, tamper-evident log line; a database-backed sink (see infrastructure)
persists records for compliance queries. Auditing never raises into the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from pb_api.core.logging import get_logger
from pb_api.integrations.workspace.domain.common import new_id, utcnow


class AuditRecord(BaseModel):
    """One immutable audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=new_id)
    tenant_id: uuid.UUID
    action: str  # e.g. "credential.load", "mail.send", "approval.decided"
    actor: str = "workspace"
    resource: str = ""
    outcome: str = "ok"  # "ok" | "denied" | "error"
    detail: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


@runtime_checkable
class AuditSink(Protocol):
    async def record(self, entry: AuditRecord) -> None: ...


class StructlogAuditSink:
    """Emits each audit record as a structured log line (always available)."""

    def __init__(self) -> None:
        self._log = get_logger("pb_api.workspace.audit")

    async def record(self, entry: AuditRecord) -> None:
        self._log.info(
            "audit",
            audit_id=str(entry.id),
            tenant_id=str(entry.tenant_id),
            action=entry.action,
            actor=entry.actor,
            resource=entry.resource,
            outcome=entry.outcome,
            **{f"detail_{k}": v for k, v in entry.detail.items()},
        )


class AuditLog:
    """Convenience facade over a sink; auditing failures never break the caller."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink
        self._log = get_logger("pb_api.workspace.audit")

    async def emit(
        self,
        tenant_id: uuid.UUID,
        action: str,
        *,
        actor: str = "workspace",
        resource: str = "",
        outcome: str = "ok",
        detail: dict[str, object] | None = None,
    ) -> None:
        entry = AuditRecord(
            tenant_id=tenant_id,
            action=action,
            actor=actor,
            resource=resource,
            outcome=outcome,
            detail=detail or {},
        )
        try:
            await self._sink.record(entry)
        except Exception:
            self._log.warning("audit_sink_failed", action=action, tenant_id=str(tenant_id))
