"""OAuth token acquisition for Microsoft Graph — implements the ``TokenProvider`` port.

Two flows are supported, chosen per stored :class:`OAuthGrant`:

* **Delegated** (a ``refresh_token`` is present): the ``refresh_token`` grant is
  used and the rotated refresh token Microsoft returns is persisted back through
  :class:`CredentialStore.rotate_refresh_token` — refresh tokens are single-use in
  Entra ID, so failing to rotate would break the next refresh.
* **Application** (no ``refresh_token``): the ``client_credentials`` grant is used
  with the ``.default`` scope (the app's admin-consented application permissions).

Tokens are cached in-memory per ``(tenant_id, connection_id)`` and re-fetched only
once :meth:`AccessToken.is_expired` reports expiry (which already applies a safety
skew). All refreshes for a given process are serialized by a lock so a burst of
callers triggers a single token request.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import httpx

from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.graph.errors import GraphAuthError
from pb_api.integrations.workspace.ports.credentials import (
    AccessToken,
    CredentialStore,
    OAuthGrant,
)

_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"


class GraphTokenProvider:
    """Acquires and caches Microsoft Graph access tokens for a connection."""

    def __init__(
        self,
        credential_store: CredentialStore,
        http_client: httpx.AsyncClient,
        settings: WorkspaceSettings,
    ) -> None:
        self._store = credential_store
        self._http = http_client
        self._settings = settings
        self._cache: dict[tuple[uuid.UUID, uuid.UUID], AccessToken] = {}
        self._lock = asyncio.Lock()

    async def get_access_token(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> AccessToken:
        key = (tenant_id, connection_id)
        cached = self._cache.get(key)
        if cached is not None and not cached.is_expired():
            return cached
        async with self._lock:
            # Re-check inside the lock: another coroutine may have refreshed while
            # we were waiting.
            cached = self._cache.get(key)
            if cached is not None and not cached.is_expired():
                return cached
            grant = await self._store.load(tenant_id, connection_id)
            if grant is None:
                raise GraphAuthError(
                    f"no OAuth grant stored for connection {connection_id}",
                    status_code=401,
                    code="MissingGrant",
                )
            token = await self._acquire(grant)
            self._cache[key] = token
            return token

    async def _acquire(self, grant: OAuthGrant) -> AccessToken:
        if grant.refresh_token:
            return await self._refresh_token_grant(grant)
        return await self._client_credentials_grant(grant)

    def _token_endpoint(self, grant: OAuthGrant) -> str:
        tenant = grant.provider_tenant_id or self._settings.graph_tenant_id or "common"
        return f"{self._settings.graph_authority.rstrip('/')}/{tenant}/oauth2/v2.0/token"

    def _scope_string(self, grant: OAuthGrant) -> str:
        scopes = grant.scopes or self._settings.graph_scope_list or [_DEFAULT_SCOPE]
        return " ".join(scopes)

    async def _client_credentials_grant(self, grant: OAuthGrant) -> AccessToken:
        form = {
            "grant_type": "client_credentials",
            "client_id": grant.client_id or self._settings.graph_client_id,
            "client_secret": grant.client_secret,
            "scope": _DEFAULT_SCOPE,
        }
        payload = await self._post_token(grant, form)
        return AccessToken(
            token=str(payload["access_token"]),
            expires_at=utcnow() + timedelta(seconds=_expires_in(payload)),
        )

    async def _refresh_token_grant(self, grant: OAuthGrant) -> AccessToken:
        # ``offline_access`` is requested so Entra ID returns a fresh refresh token
        # to rotate; without it the delegated session would eventually expire.
        scope = self._scope_string(grant)
        if "offline_access" not in scope.split():
            scope = f"{scope} offline_access".strip()
        form = {
            "grant_type": "refresh_token",
            "client_id": grant.client_id or self._settings.graph_client_id,
            "client_secret": grant.client_secret,
            "refresh_token": grant.refresh_token or "",
            "scope": scope,
        }
        payload = await self._post_token(grant, form)
        rotated = payload.get("refresh_token")
        rotated_str = str(rotated) if isinstance(rotated, str) and rotated else None
        if rotated_str is not None and rotated_str != grant.refresh_token:
            await self._store.rotate_refresh_token(
                grant.tenant_id, grant.connection_id, rotated_str
            )
        return AccessToken(
            token=str(payload["access_token"]),
            expires_at=utcnow() + timedelta(seconds=_expires_in(payload)),
            refresh_token=rotated_str,
        )

    async def _post_token(self, grant: OAuthGrant, form: dict[str, str]) -> dict[str, Any]:
        response = await self._http.post(self._token_endpoint(grant), data=form)
        body = _safe_json(response)
        if response.status_code >= 400 or "access_token" not in body:
            description = body.get("error_description") or body.get("error")
            message = (
                str(description)
                if description is not None
                else f"token endpoint returned HTTP {response.status_code}"
            )
            raise GraphAuthError(
                message,
                status_code=response.status_code,
                code=str(body.get("error")) if body.get("error") is not None else None,
            )
        return body


def _expires_in(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("expires_in", 3600))
    except (TypeError, ValueError):
        return 3600


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
