"""Workspace security — credential encryption and audit logging.

`CredentialCipher` (Fernet, with key rotation) encrypts secrets at rest;
`AuditLog` records security-relevant actions as immutable audit entries.
"""

from pb_api.integrations.workspace.security.audit import (
    AuditLog,
    AuditRecord,
    AuditSink,
    StructlogAuditSink,
)
from pb_api.integrations.workspace.security.crypto import CredentialCipher, generate_key

__all__ = [
    "AuditLog",
    "AuditRecord",
    "AuditSink",
    "CredentialCipher",
    "StructlogAuditSink",
    "generate_key",
]
