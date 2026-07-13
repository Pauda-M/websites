"""The Microsoft Graph HTTP client — the only place in the workspace that speaks Graph.

Wraps an injected :class:`httpx.AsyncClient` with the cross-cutting concerns every
Graph call needs: bearer-token injection (via the :class:`TokenProvider` port),
client-side rate limiting, and retry with exponential backoff that honours the
``Retry-After`` header on ``429``/``503``. It also implements Graph's two read
idioms — ``@odata.nextLink`` cursor pagination and ``@odata.deltaLink`` delta sync
— as generic helpers so the capability providers only supply an item mapper.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar
from urllib.parse import parse_qs, urlparse

import httpx

from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.common import ensure_aware
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.graph.errors import GraphAuthError, GraphError
from pb_api.integrations.workspace.graph.rate_limit import AsyncRateLimiter
from pb_api.integrations.workspace.ports.credentials import TokenProvider

JSONObject = dict[str, Any]
T = TypeVar("T")

_RETRY_STATUS = frozenset({429, 503})
_FRACTIONAL_SECONDS = re.compile(r"(\.\d{6})\d+")


class GraphClient:
    """An authenticated, rate-limited, retrying HTTP client for Microsoft Graph."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        token_provider: TokenProvider,
        rate_limiter: AsyncRateLimiter,
        settings: WorkspaceSettings,
    ) -> None:
        self._http = http_client
        self._token_provider = token_provider
        self._rate_limiter = rate_limiter
        self._settings = settings

    # -- Verb helpers ---------------------------------------------------

    async def get(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        return await self._request(
            "GET",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            params=params,
            headers=headers,
            follow_redirects=follow_redirects,
        )

    async def post(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "POST",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=json,
            params=params,
            headers=headers,
        )

    async def patch(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "PATCH",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=json,
            params=params,
            headers=headers,
        )

    async def delete(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "DELETE",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            params=params,
            headers=headers,
        )

    async def put_content(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        content: bytes,
        content_type: str,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Upload a raw byte body (used for small ``driveItem`` uploads)."""
        return await self._request(
            "PUT",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            content=content,
            content_type=content_type,
            headers=headers,
        )

    async def get_content(
        self,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        params: Mapping[str, Any] | None = None,
    ) -> bytes:
        """GET raw bytes, following the pre-authenticated download redirect Graph issues."""
        response = await self._request(
            "GET",
            path_or_url,
            tenant_id=tenant_id,
            connection_id=connection_id,
            params=params,
            follow_redirects=True,
        )
        return response.content

    # -- Pagination & delta --------------------------------------------

    async def paginate(
        self,
        path: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        map_item: Callable[[JSONObject], T],
        params: Mapping[str, Any] | None = None,
        cursor: str | None = None,
    ) -> Page[T]:
        """Fetch one page of a Graph collection and its ``@odata.nextLink`` cursor."""
        if cursor:
            response = await self.get(cursor, tenant_id=tenant_id, connection_id=connection_id)
        else:
            response = await self.get(
                path, tenant_id=tenant_id, connection_id=connection_id, params=params
            )
        payload = _as_object(response)
        items = [map_item(item) for item in _values(payload)]
        next_cursor = payload.get("@odata.nextLink")
        return Page(items=items, next_cursor=next_cursor if isinstance(next_cursor, str) else None)

    async def delta(
        self,
        path: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        map_item: Callable[[JSONObject], T],
        params: Mapping[str, Any] | None = None,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[T]:
        """Fetch one page of a Graph delta sweep.

        Resumption precedence mirrors Graph: an in-sweep ``cursor`` (nextLink) wins,
        else a stored ``delta_token`` (deltaLink), else a fresh ``{path}/delta``.
        Items carrying ``@removed`` are tombstones — their ids go to ``removed_ids``.
        """
        if cursor:
            response = await self.get(cursor, tenant_id=tenant_id, connection_id=connection_id)
        elif delta_token:
            merged: dict[str, Any] = dict(params or {})
            merged["$deltatoken"] = delta_token
            response = await self.get(
                f"{path}/delta",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params=merged,
            )
        else:
            response = await self.get(
                f"{path}/delta",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params=params,
            )
        payload = _as_object(response)
        items: list[T] = []
        removed: list[str] = []
        for item in _values(payload):
            if "@removed" in item:
                removed_id = item.get("id")
                if isinstance(removed_id, str):
                    removed.append(removed_id)
                continue
            items.append(map_item(item))
        next_link = payload.get("@odata.nextLink")
        next_cursor = next_link if isinstance(next_link, str) else None
        new_delta_token: str | None = None
        if next_cursor is None:
            delta_link = payload.get("@odata.deltaLink")
            if isinstance(delta_link, str):
                new_delta_token = _delta_token_from_link(delta_link)
        return DeltaPage(
            items=items,
            next_cursor=next_cursor,
            delta_token=new_delta_token,
            removed_ids=tuple(removed),
        )

    # -- Internals ------------------------------------------------------

    def _build_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return f"{self._settings.graph_base_url.rstrip('/')}/{path_or_url.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        url = self._build_url(path_or_url)
        attempt = 0
        while True:
            token = await self._token_provider.get_access_token(tenant_id, connection_id)
            await self._rate_limiter.acquire()
            request_headers: dict[str, str] = {"Authorization": f"Bearer {token.token}"}
            if content_type is not None:
                request_headers["Content-Type"] = content_type
            if headers:
                request_headers.update(headers)
            response = await self._http.request(
                method,
                url,
                params=params,
                json=json,
                content=content,
                headers=request_headers,
                follow_redirects=follow_redirects,
            )
            if response.status_code == 401:
                raise self._build_error(response, auth=True)
            if response.status_code in _RETRY_STATUS and attempt < self._settings.max_retries:
                await asyncio.sleep(self._retry_delay(response, attempt))
                attempt += 1
                continue
            if response.status_code >= 400:
                raise self._build_error(response)
            return response

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        delay = self._settings.retry_base_delay_seconds * (2**attempt)
        if retry_after is not None:
            # A non-numeric Retry-After (an HTTP-date) leaves the backoff delay.
            with contextlib.suppress(ValueError):
                delay = float(retry_after)
        return float(min(delay, self._settings.retry_max_delay_seconds))

    def _build_error(self, response: httpx.Response, *, auth: bool = False) -> GraphError:
        code: str | None = None
        message = f"Microsoft Graph returned HTTP {response.status_code}"
        body = _try_json(response)
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            raw_code = error.get("code")
            raw_message = error.get("message")
            code = str(raw_code) if raw_code is not None else None
            if raw_message is not None:
                message = str(raw_message)
        error_type = GraphAuthError if auth else GraphError
        return error_type(message, status_code=response.status_code, code=code)


# -- Module-level parsing helpers ---------------------------------------


def _as_object(response: httpx.Response) -> JSONObject:
    data = _try_json(response)
    return data if isinstance(data, dict) else {}


def _try_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _values(payload: JSONObject) -> list[JSONObject]:
    value = payload.get("value")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _delta_token_from_link(delta_link: str) -> str | None:
    tokens = parse_qs(urlparse(delta_link).query).get("$deltatoken")
    return tokens[0] if tokens else None


def parse_graph_datetime(value: object) -> datetime | None:
    """Parse a Graph ISO-8601 timestamp to a UTC-aware ``datetime`` (or ``None``).

    Handles the trailing ``Z`` shorthand and Graph's 7-digit fractional seconds,
    both of which bare :meth:`datetime.fromisoformat` rejects on some versions.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        text = f"{text[:-1]}+00:00"
    text = _FRACTIONAL_SECONDS.sub(r"\1", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return ensure_aware(parsed)


def to_graph_utc_iso(value: datetime) -> str:
    """Render a ``datetime`` as UTC ISO-8601 with the ``Z`` suffix Graph expects."""
    return ensure_aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")
