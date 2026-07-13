# Microsoft Graph Integration Guide

Operations and developer guide for the **Microsoft Graph adapter** of the Workspace Integration
(Epic 009). It covers configuration, registering the Azure AD (Microsoft Entra ID) application,
how token acquisition and credential encryption work, how to rotate the Fernet key, how delta
sync and webhooks operate, and how to run a synchronization. For the architecture, see
`018_Workspace_Integration.md`; for the decision record, [ADR-0012](../adr/0012-workspace-integration.md).

The integration is **provider-agnostic**. Graph is the primary adapter; with no Graph
credentials configured the platform runs on the fully-functional in-memory adapter, so nothing
below is required to boot Genesis — only to connect a real Microsoft 365 tenant.

## Configuration (`PB_WS_*`)

All configuration is sourced from environment variables with the `PB_WS_` prefix
(`integrations/workspace/config.py`, `WorkspaceSettings`). Secrets are read from the environment
/ secret store, never hardcoded.

| Env var | Setting | Default | Notes |
| --- | --- | --- | --- |
| `PB_WS_PROVIDER` | `provider` | `in_memory` | Set to `microsoft_graph` to activate the Graph adapter. |
| `PB_WS_GRAPH_TENANT_ID` | `graph_tenant_id` | `""` | The Entra ID (directory) tenant id. |
| `PB_WS_GRAPH_CLIENT_ID` | `graph_client_id` | `""` | The registered application (client) id. |
| `PB_WS_GRAPH_AUTHORITY` | `graph_authority` | `https://login.microsoftonline.com` | OAuth authority host. |
| `PB_WS_GRAPH_BASE_URL` | `graph_base_url` | `https://graph.microsoft.com/v1.0` | Graph API base. |
| `PB_WS_GRAPH_SCOPES` | `graph_scopes` | `https://graph.microsoft.com/.default` | Space-separated scope list (`graph_scope_list`). |
| `PB_WS_CREDENTIAL_ENCRYPTION_KEY` | `credential_encryption_key` | `""` | Fernet key (urlsafe base64, 32 bytes) for credential encryption at rest. **Required in production.** |
| `PB_WS_SYNC_PAGE_SIZE` | `sync_page_size` | `50` | Page size for listing/delta reads. |
| `PB_WS_MAX_RETRIES` | `max_retries` | `5` | Retry attempts for sync and Graph `429`/`503`. |
| `PB_WS_RETRY_BASE_DELAY_SECONDS` | `retry_base_delay_seconds` | `0.5` | Base backoff delay. |
| `PB_WS_RETRY_MAX_DELAY_SECONDS` | `retry_max_delay_seconds` | `30.0` | Backoff cap. |
| `PB_WS_RATE_LIMIT_PER_SECOND` | `rate_limit_per_second` | `15.0` | Client-side token-bucket rate. |
| `PB_WS_WEBHOOK_RENEW_BEFORE_SECONDS` | `webhook_renew_before_seconds` | `3600` | Renew subscriptions within this window of expiry. |
| `PB_WS_HTTP_TIMEOUT_SECONDS` | `http_timeout_seconds` | `30.0` | HTTP client timeout. |
| `PB_WS_DOCUMENT_CHUNK_CHARS` | `document_chunk_chars` | `4000` | Document ingestion chunk size. |
| `PB_WS_EMBEDDING_DIM` | `embedding_dim` | `64` | Search embedding dimension. |

`graph_configured` is `True` only when both `graph_tenant_id` and `graph_client_id` are set; the
API dependency (`api/deps.py`) selects the Graph adapter only when `provider == microsoft_graph`
**and** `graph_configured`, otherwise it falls back to the in-memory adapter.

> **The client secret and refresh token are NOT `PB_WS_*` config.** They are supplied
> per-connection when you register a connection (`POST /connections`) and stored **encrypted**
> in `ws_credential`. `graph_client_id` in config is only a fallback used when a stored grant
> omits its own `client_id`.

## Registering the Azure AD application

1. In the Entra ID portal, **App registrations → New registration**. Note the **Application
   (client) ID** → `PB_WS_GRAPH_CLIENT_ID` and the **Directory (tenant) ID** →
   `PB_WS_GRAPH_TENANT_ID`.
2. Add a **client secret** (or certificate) under **Certificates & secrets**. This secret is
   passed to `POST /connections` as `client_secret` and stored encrypted — it never goes in
   config or logs.
3. Grant **least-privilege** Microsoft Graph permissions matching only the capabilities the
   adapter exercises, then grant admin consent:

| Permission | Enables |
| --- | --- |
| `Mail.ReadWrite` | Read the mailbox, thread conversations, download attachments, create drafts. |
| `Calendars.ReadWrite` | Read events, compute availability, create invites, respond. |
| `Contacts.Read` | Read contacts. |
| `User.Read.All` | Read the directory (users, groups, healthcheck). |
| `Files.Read.All` | Read SharePoint/OneDrive sites and drive items, ingest documents. |
| `Tasks.ReadWrite` | Read/create/complete To Do tasks. |
| `Presence.Read.All` | Read user presence. |

   Sending mail (`send`) additionally requires `Mail.Send`; uploading drive content
   (`StorageProvider.upload`) requires `Files.ReadWrite.All`. Grant those only if you enable
   those actions. Nothing is granted that the code does not use.

4. Choose the flow:
   - **Application permissions (client-credentials)** — for a service that acts on a shared
     mailbox/tenant with admin consent. Register the connection with a `client_secret` and **no**
     `refresh_token`; the adapter uses the `client_credentials` grant with the `.default` scope.
   - **Delegated permissions (refresh-token)** — for acting as a specific user. Register the
     connection with a `refresh_token`; the adapter uses the `refresh_token` grant and rotates
     the token on each refresh.

## Registering a connection

```bash
curl -X POST http://localhost:8000/api/v1/integrations/workspace/connections \
  -H 'content-type: application/json' \
  -d '{
        "tenant_id": "<genesis-tenant-uuid>",
        "display_name": "Support Mailbox",
        "mailbox": "support@contoso.com",
        "provider_tenant_id": "<entra-tenant-id>",
        "client_id": "<app-client-id>",
        "client_secret": "<app-client-secret>",
        "refresh_token": null,
        "scopes": ["https://graph.microsoft.com/.default"]
      }'
```

`bootstrap_connection` (`application/workspace.py`) creates the `ws_connection`, stores the
grant encrypted via `EncryptedCredentialStore.save`, seeds the default approval policies, and
emits `pb.workspace.connection.established`. The `mailbox` resolves the Graph resource path
(`/users/{mailbox}/...`) via the DB-backed resolver.

## How token acquisition + credential encryption work

`GraphTokenProvider` (`graph/auth.py`) implements the `TokenProvider` port:

- On each request `GraphClient` calls `get_access_token(tenant_id, connection_id)`. A per-key
  in-memory cache returns the current token until `AccessToken.is_expired` (with a safety skew)
  reports expiry; a lock serializes refreshes so a burst of callers triggers one token request.
- The grant is loaded through `EncryptedCredentialStore.load`, which **decrypts** the client
  secret and refresh token in memory only.
- **Delegated:** the `refresh_token` grant requests `offline_access`; Entra ID returns a fresh
  refresh token (single-use), which is persisted back through
  `CredentialStore.rotate_refresh_token` (re-encrypted). Failing to rotate would break the next
  refresh.
- **Application:** the `client_credentials` grant with the `.default` scope is used.

Secrets at rest: `EncryptedCredentialStore` (`application/credential_store.py`) encrypts the
client secret and refresh token with the Fernet `CredentialCipher` before they touch
`ws_credential`, which stores **only ciphertext** (`client_secret_encrypted`,
`refresh_token_encrypted`). Every credential access is audited (`credential.save`,
`credential.load`, `credential.rotate_refresh_token`); no plaintext secret is ever logged or
returned.

## Generating and rotating the Fernet key

Generate a key with the module helper (`security/crypto.py`):

```python
from pb_api.integrations.workspace.security.crypto import generate_key
print(generate_key())   # a urlsafe-base64 Fernet key; set as PB_WS_CREDENTIAL_ENCRYPTION_KEY
```

(Equivalently: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.)

`CredentialCipher` wraps a `MultiFernet`, which makes rotation first-class: the **primary** key
encrypts, and any number of **retired** keys can still decrypt, so a key rotates without a
flag-day re-encryption.

```python
from pb_api.integrations.workspace.security.crypto import CredentialCipher

# New primary key, old key retained so existing ciphertext still decrypts.
cipher = CredentialCipher.from_key_material(new_primary_key, retired=[old_key])
```

Rotation procedure:

1. Generate a new key and make it the **primary**; move the old key to **retired** so stored
   credentials still decrypt.
2. Optionally re-encrypt existing tokens under the new primary with `CredentialCipher.rotate`
   (re-writes each token via `MultiFernet.rotate`).
3. Once every stored credential is re-encrypted under the new primary, drop the retired key.

If no key is configured, `from_key_material` generates an **ephemeral** key per process — fine
for development, but credentials will not decrypt after a restart. Production **must** supply a
persistent `PB_WS_CREDENTIAL_ENCRYPTION_KEY`. A malformed key fails fast (`_normalize_key`
validates it), and a token that cannot be decrypted raises a clear `ValueError` rather than
returning garbage.

## How delta sync and webhooks work operationally

- **Delta sync** — each `(connection, resource)` keeps a `ws_sync_state.delta_token`. A sweep
  resumes in Graph's precedence order: an in-sweep `@odata.nextLink` cursor wins, else the stored
  `deltatoken`, else a fresh `{path}/delta`. `@removed` items are tombstones routed to
  `removed_ids`; the final page's `@odata.deltaLink` yields the new token, which is persisted so
  the next run fetches only changes.
- **Retry + dead-letter** — `SyncService.sync_resource` records a `ws_sync_job`, retries the
  resource with exponential backoff up to `max_retries`, and on final failure captures a
  `ws_dead_letter` and emits `pb.workspace.sync.failed`. Nothing is silently lost.
- **Webhooks** — `GraphWorkspaceProvider.create_subscription` registers a Graph
  change-notification subscription (with a `clientState` secret echoed back to authenticate
  notifications and a ~3-day default expiry). `WorkspaceContext.renew_due_webhooks` — invoked
  each worker tick — renews subscriptions within `webhook_renew_before_seconds` of expiry via
  `renew_subscription`. Store subscriptions in `ws_webhook_subscription`; the health snapshot
  reports the active count.

## Running a sync

**On demand (HTTP):** sync every resource for a connection —

```bash
curl -X POST http://localhost:8000/api/v1/integrations/workspace/sync/run \
  -H 'content-type: application/json' \
  -d '{"tenant_id": "<tenant>", "connection_id": "<connection>"}'

# inspect recent jobs
curl "http://localhost:8000/api/v1/integrations/workspace/sync/status?tenant_id=<tenant>"
```

`POST /sync/run` calls `sync.sync_all` (mail, calendar, contacts, directory users, tasks) and
increments `ws_sync_runs_total` / `ws_sync_items_total`. Mail can be delta-synced on its own via
`POST /mail/sync`.

**Background (worker):** a production scheduler invokes one tick per tenant on an interval —

```python
from pb_api.integrations.workspace.application.worker import WorkspaceSyncWorker

worker = WorkspaceSyncWorker(session_factory, provider_for=build_provider)  # optional factory
summary = await worker.tick(tenant_id)
# {"connections": N, "jobs": M, "failures": K, "webhooks_renewed": R}
```

Each tick opens its own session, builds a `WorkspaceContext`, runs `sync.sync_all` for every
connection, and renews due webhooks — all under retry + dead-lettering. Pass a `provider_for`
factory (e.g. `build_graph_provider`) so the worker uses the same Graph adapter as the request
path.

## Health & troubleshooting

- `GET /connections/health?tenant_id=...` returns provider reachability (a Graph healthcheck
  against `/users/{mailbox}` with a fallback to `/organization`), the dead-letter count, and the
  active-webhook count.
- Watch `ws_provider_rate_limited_total` for throttling; lower `PB_WS_RATE_LIMIT_PER_SECOND` if
  Graph returns sustained `429`s (the client already honours `Retry-After`).
- Growth in `ws_dead_letter_queue_size` / `ws_dead_letter_total` indicates a resource is failing
  past its retries — inspect the `ws_dead_letter` rows' `error`.
- A `GraphAuthError` (`401`, or a missing grant) means the connection has no stored/valid
  credential — re-register the connection or check the app's permissions and admin consent.

## Cross-references

- `018_Workspace_Integration.md` — architecture and full API surface.
- `PROVIDER_ABSTRACTION_GUIDE.md` — the port contracts a new adapter implements.
- `APPROVAL_WORKFLOW_GUIDE.md` — how outbound Graph actions are gated.
- [ADR-0012](../adr/0012-workspace-integration.md) — the decision record.
