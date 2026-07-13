# ADR-0012: Enterprise Digital Workspace Integration

## Status

Accepted — 2026-07-13

## Context

Genesis Epic 009 requires the **Enterprise Digital Workspace Integration**: Genesis must operate
as an active digital employee *inside* a customer's Microsoft 365 — reading and replying from a
shared mailbox, scheduling on a calendar, knowing the directory and contacts, posting to Teams,
ingesting SharePoint/OneDrive as knowledge, and tracking tasks and presence. It is the first
Genesis module that reaches out to a live third-party SaaS on the customer's behalf.

Several forces from the manifesto and prior ADRs shaped how this landed:

- **No vendor lock-in.** The manifesto forbids depending entirely on one vendor; every provider
  must be abstracted (`004_Company_Brain.md`, `012_Security.md`). A workspace integration is
  precisely where a naive design would hard-wire a vendor SDK through the whole codebase.
- **Everything is an event; everything produces memory.** The Cognitive Core (ADR-0010) already
  owns an append-only event store and a memory engine; the Program Manager (ADR-0011) already owns
  the CRM. Bounded contexts must not reach into each other's internals (ADR-0008). The workspace
  needs all three but must re-implement none.
- **Governed autonomy.** Reaching into a real mailbox means the ability to send real email.
  Autonomy must be bounded and auditable from first boot (ADR-0009): every outward action needs an
  approval decision and an immutable event, and nothing may exceed its bound silently.
- **Always assume production, never hardcode secrets.** OAuth credentials — client secrets and
  refresh tokens — must be encrypted at rest and rotatable.
- **The platform must stay fully functional with no external services.** The suite runs on SQLite
  with no network; the integration cannot require a live Microsoft 365 tenant to boot or test.

## Decision

**Placement.** The integration is a bounded context at
`apps/api/src/pb_api/integrations/workspace/`, addressable at
`/api/v1/integrations/workspace`, strictly layered domain → ports → security → adapters
(`graph/`, `local/`) → db → infrastructure → application → api. `WorkspaceContext`
(`application/workspace.py`) is the single composition root, mirroring the Cognitive Core and
Program Manager so the codebase reads uniformly.

**Ports-and-adapters, with Microsoft Graph as the primary adapter.** Business logic depends only
on the provider ports in `ports/providers.py` — the aggregate `WorkspaceProvider` plus nine
capability ports (mail, calendar, contacts, directory, storage, meetings, presence, notifications,
tasks). **No code under `application/` imports Microsoft Graph.** The Graph adapter (`graph/`) is
the only code that speaks Graph, centralising OAuth, retry/backoff honouring `Retry-After`,
client-side rate limiting, `@odata.nextLink` pagination, and `@odata.deltaLink` delta sync in one
`GraphClient`. Selecting a provider is configuration (`PB_WS_PROVIDER`), not code.

**The in-memory adapter is a first-class alternate backend, not a mock.** `local/`
(`InMemoryWorkspaceProvider` over `InMemoryStore`) fully implements every port with real cursor
pagination and delta-token semantics. It is the default provider (so the platform runs with no
credentials), the development and air-gapped backend, and the test backend the whole suite runs
against — no production behaviour is stubbed.

**Reuse the Cognitive Core and the CRM through narrow seams.** The workspace reuses the Cognitive
Core's immutable `CognitiveEvent` envelope and its append-only `EventProcessor` via a single
`WorkspaceEventProjector.project` write path that also writes episodic memory — it builds no
second event store. It reaches the Program Manager's CRM only through the narrow `CrmSyncPort`
(`identify_customer` / `ensure_customer` / `record_interaction`), wired at the composition
boundary by `ProgramManagerCrmBridge`; it never imports Program-Manager internals.

**Fernet credential encryption with rotation.** `CredentialCipher` (`security/crypto.py`) wraps a
`MultiFernet`: the primary key encrypts, retired keys still decrypt, so a key rotates without a
flag-day re-encryption. `EncryptedCredentialStore` encrypts client secrets and refresh tokens
before they touch `ws_credential` (which stores only ciphertext) and decrypts only in memory to
mint a token; delegated refresh tokens are rotated on every refresh. Every credential access is
audited. No secret is hardcoded — configuration comes from `PB_WS_*`.

**Resilient synchronization: delta + webhooks + retry/DLQ.** `SyncService` runs per-resource delta
sync resuming from a persisted `delta_token`, records each run as a `SyncJob`, retries with
exponential backoff, and captures exhausted work in a dead-letter queue rather than dropping it.
`WorkspaceSyncWorker.tick` drives periodic sync and webhook renewal outside the request path;
change-notification subscriptions are created and renewed before expiry.

**An approval engine gates every outbound action.** `ApprovalEngine` deterministically evaluates
each `OutboundAction` (mail, meeting response, Teams post, notification) against enabled policies,
taking the maximum under `(priority, specificity, restrictiveness)`, downgrading an
auto-approval that exceeds the actor's authority, and defaulting to human approval with no match.
The default seed drafts replies and requires approval for everything else — bounded from first
boot.

**Runtime dependencies.** The Graph adapter adds `httpx` (async HTTP) and `cryptography` (Fernet)
as runtime dependencies. Both are mature, widely-used, and isolated behind the adapter and the
security module respectively.

## Alternatives Considered

- **Use the Microsoft Graph SDK directly in the services.** Rejected as vendor lock-in: it would
  thread a Microsoft type through every service and make a second provider a rewrite. A thin
  `httpx`-based adapter behind ports keeps business logic vendor-free and a new provider a matter
  of one package plus a factory branch.
- **Store OAuth secrets in plaintext (env or DB columns).** Rejected: it violates "always assume
  production, never hardcode/expose secrets." Fernet encryption at rest with rotation, and secrets
  supplied per-connection rather than in config, is the honest baseline.
- **Stand up a second event store (and/or memory) for workspace activity.** Rejected as
  duplication and a second source of truth. Reusing the Cognitive Core's `EventProcessor` and
  episodic memory through one projector keeps the entire company history in one append-only,
  tenant-scoped store — the manifesto's Memory principle.
- **Import the Program Manager's `CrmService` directly to "update CRM on every email."** Rejected
  as a bounded-context violation. The narrow `CrmSyncPort` exposes only what the workspace needs,
  and a no-op implementation lets the workspace run without the CRM.
- **Mock outbound sends / a live-tenant-only test strategy.** Rejected. A fully-functional
  in-memory adapter is a real backend the suite exercises end-to-end, and the Graph adapter is
  tested against an `httpx.MockTransport` at the HTTP boundary — no production behaviour is faked.

## Consequences

- The platform gains a complete, tested workspace integration: ten provider ports, a Microsoft
  Graph adapter and an in-memory adapter, 11 tenant-scoped `ws_` tables (Alembic `0004`), an
  HTTP surface under `/api/v1/integrations/workspace`, and workspace metrics
  (`ws_sync_runs_total`, `ws_sync_items_total`, `ws_sync_duration_seconds`, `ws_dead_letter_*`,
  `ws_approvals_total`, `ws_provider_rate_limited_total`, `ws_webhook_subscriptions_active`,
  `ws_worker_runs_total`) on the existing `/metrics` registry.
- Every workspace activity is an immutable event that updates memory, every email is linked to the
  CRM through the port, and every outbound action is approval-gated and audited — governed
  autonomy is concrete.
- Adding another provider (e.g. Google Workspace) is a new adapter package, a `Provider` enum
  value, and a factory branch — no business-logic change.
- The suite still runs on SQLite with no external services (in-memory adapter); production runs
  PostgreSQL and Microsoft Graph unchanged, via portable column types and configuration.
- Two runtime dependencies (`httpx`, `cryptography`) are added, isolated behind the adapter and
  security module.
- A real deployment must provision an Entra ID app with least-privilege permissions, a persistent
  `PB_WS_CREDENTIAL_ENCRYPTION_KEY`, and a scheduler to drive `WorkspaceSyncWorker.tick` per
  tenant.

## Future Considerations

- A **Google Workspace adapter** (the `GOOGLE_WORKSPACE` enum value is already reserved),
  implemented purely as new port implementations.
- **pgvector** for the unified search index (`ws_index_entry`), replacing in-process cosine
  similarity behind the same `SearchService` interface, as the production scale-up.
- **Cross-tenant worker scheduling** — a production scheduler that fans `WorkspaceSyncWorker.tick`
  across tenants on an interval, with backpressure informed by the dead-letter and rate-limit
  metrics.
- **Inbound webhook processing** — turning delivered Graph change notifications into immediate
  ingestion, complementing the current delta-poll model.
- Row-level tenant isolation once the multi-tenancy delta (`000_Glossary.md` §13) lands, hardening
  the application-level tenant scoping the module already enforces.
