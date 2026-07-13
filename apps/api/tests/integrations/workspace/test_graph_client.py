"""Microsoft Graph adapter tests against a mocked HTTP transport.

No live tenant: an ``httpx.MockTransport`` intercepts requests so we can assert the
adapter mints tokens correctly, attaches the bearer, retries on 429 honoring
``Retry-After``, follows ``@odata.nextLink`` pagination, and extracts the delta
token from ``@odata.deltaLink``.
"""

from __future__ import annotations

import json
import uuid

import httpx

from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.graph import GraphClient, GraphTokenProvider
from pb_api.integrations.workspace.graph.mail import GraphMailProvider
from pb_api.integrations.workspace.graph.rate_limit import AsyncRateLimiter
from pb_api.integrations.workspace.graph.resolver import ResourceBinding, StaticGraphResolver
from pb_api.integrations.workspace.ports.credentials import OAuthGrant

TENANT = uuid.uuid4()
CONNECTION = uuid.uuid4()


class _FakeCredentialStore:
    """A minimal in-memory ``CredentialStore`` for client-credentials tests."""

    def __init__(self) -> None:
        self.rotated: list[str] = []

    async def save(self, grant: OAuthGrant) -> None:  # pragma: no cover - unused here
        return None

    async def load(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> OAuthGrant | None:
        return OAuthGrant(
            tenant_id=tenant_id,
            connection_id=connection_id,
            provider_tenant_id="contoso",
            client_id="app-123",
            client_secret="secret",
            refresh_token=None,
            scopes=["https://graph.microsoft.com/.default"],
        )

    async def rotate_refresh_token(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, refresh_token: str
    ) -> None:  # pragma: no cover - client-credentials has no refresh token
        self.rotated.append(refresh_token)


def _message(provider_id: str) -> dict[str, object]:
    return {
        "id": provider_id,
        "subject": "Hi",
        "from": {"emailAddress": {"address": "a@b.com", "name": "A"}},
        "sender": {"emailAddress": {"address": "a@b.com", "name": "A"}},
        "receivedDateTime": "2026-01-01T00:00:00Z",
        "bodyPreview": "hello",
        "body": {"content": "hello", "contentType": "text"},
        "toRecipients": [],
        "ccRecipients": [],
        "importance": "normal",
        "isRead": False,
        "categories": [],
        "hasAttachments": False,
    }


def _build(handler: httpx.MockTransport) -> tuple[httpx.AsyncClient, GraphMailProvider]:
    settings = WorkspaceSettings(retry_base_delay_seconds=0.0)
    http = httpx.AsyncClient(transport=handler)
    token = GraphTokenProvider(_FakeCredentialStore(), http, settings)
    client = GraphClient(http, token, AsyncRateLimiter(1000.0), settings)
    resolver = StaticGraphResolver(default=ResourceBinding(mailbox="user@contoso.test"))
    return http, GraphMailProvider(client, resolver)


async def test_acquires_client_credentials_token_and_attaches_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok-abc", "expires_in": 3600})
        return httpx.Response(200, json={"value": [_message("m1")]})

    http, mail = _build(httpx.MockTransport(handler))
    async with http:
        page = await mail.list_messages(TENANT, CONNECTION)
    assert len(page.items) == 1
    token_req = next(r for r in seen if r.url.path.endswith("/token"))
    assert b"grant_type=client_credentials" in token_req.content
    msg_req = next(r for r in seen if "messages" in r.url.path)
    assert msg_req.headers["Authorization"] == "Bearer tok-abc"


async def test_retries_on_429_honoring_retry_after() -> None:
    calls = {"messages": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        calls["messages"] += 1
        if calls["messages"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {}})
        return httpx.Response(200, json={"value": [_message("m1")]})

    http, mail = _build(httpx.MockTransport(handler))
    async with http:
        page = await mail.list_messages(TENANT, CONNECTION)
    assert len(page.items) == 1
    assert calls["messages"] == 2  # one 429, one success


async def test_pagination_exposes_next_link_as_cursor() -> None:
    next_link = "https://graph.microsoft.com/v1.0/users/user@contoso.test/messages?$skiptoken=ABC"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if "skiptoken" in str(request.url):
            return httpx.Response(200, json={"value": [_message("m2")]})
        return httpx.Response(200, json={"value": [_message("m1")], "@odata.nextLink": next_link})

    http, mail = _build(httpx.MockTransport(handler))
    async with http:
        first = await mail.list_messages(TENANT, CONNECTION)
        assert first.next_cursor == next_link
        second = await mail.list_messages(TENANT, CONNECTION, cursor=first.next_cursor)
    assert [m.provider_id for m in second.items] == ["m2"]


async def test_delta_extracts_delta_token() -> None:
    delta_link = (
        "https://graph.microsoft.com/v1.0/users/user@contoso.test/messages/delta?$deltatoken=XYZ"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"value": [_message("m1")], "@odata.deltaLink": delta_link})

    http, mail = _build(httpx.MockTransport(handler))
    async with http:
        page = await mail.delta_messages(TENANT, CONNECTION)
    assert page.delta_token == "XYZ"
    assert page.next_cursor is None


def test_message_json_is_valid() -> None:
    # Guard: the fixture message serializes (used by the handlers above).
    assert json.loads(json.dumps(_message("m1")))["id"] == "m1"
