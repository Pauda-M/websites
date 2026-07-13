"""Workspace ports — the interfaces business logic depends on (never a vendor SDK).

Provider capabilities (`providers`), OAuth credential/token handling
(`credentials`), and the narrow CRM-sync bridge (`crm_sync`). Adapters implement
these; nothing here imports an adapter.
"""
