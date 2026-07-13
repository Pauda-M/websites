"""Workspace integration configuration.

Sourced from ``PB_WS_*`` environment variables (12-factor). Secrets are read from
the environment / secret store, never hardcoded (manifesto: Security). When no
Microsoft Graph credentials are configured, the integration runs on the
in-memory provider so the platform is fully functional out of the box.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from pb_api.integrations.workspace.domain.common import Provider


class WorkspaceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PB_WS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Provider selection --------------------------------------------
    # The active provider. Defaults to the in-memory adapter so the platform runs
    # with no external credentials; set to ``microsoft_graph`` in production.
    provider: Provider = Provider.IN_MEMORY

    # --- Microsoft Graph -----------------------------------------------
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    # The client secret / certificate is read from the secret store, not here.
    graph_authority: str = "https://login.microsoftonline.com"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    graph_scopes: str = "https://graph.microsoft.com/.default"

    # --- Credential encryption -----------------------------------------
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt stored credentials at
    # rest. Empty => an ephemeral key is generated per process (dev only); a
    # persistent key MUST be provided in production.
    credential_encryption_key: str = ""

    # --- Sync & resilience ---------------------------------------------
    sync_page_size: int = 50
    max_retries: int = 5
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 30.0
    rate_limit_per_second: float = 15.0
    webhook_renew_before_seconds: int = 3600
    http_timeout_seconds: float = 30.0

    # --- Knowledge ingestion -------------------------------------------
    document_chunk_chars: int = 4000
    embedding_dim: int = 64

    @property
    def graph_configured(self) -> bool:
        return bool(self.graph_tenant_id and self.graph_client_id)

    @property
    def graph_scope_list(self) -> list[str]:
        return [scope for scope in self.graph_scopes.split() if scope]


@lru_cache
def get_workspace_settings() -> WorkspaceSettings:
    return WorkspaceSettings()
