# PB Platform — Architecture

This document describes the system as built in Phase 1 (foundation) and the
rules that keep it healthy as it grows into the full PB Solutions product
suite (CRM, client portal, AI services, ticketing, knowledge base, proposals,
invoicing, internal admin).

## 1. High-level topology

```
                        ┌──────────────────────────────┐
        HTTPS           │   Traefik (edge)             │
  users ──────────────▶ │   TLS, routing, sec headers  │
                        └──────┬────────────────┬──────┘
                               │                │
                    Host(`DOMAIN`)      Host(`api.DOMAIN`)
                               │                │
                        ┌──────▼─────┐   ┌──────▼─────┐
                        │  web       │──▶│  api       │
                        │  Next.js   │   │  FastAPI   │
                        └────────────┘   └──┬──────┬──┘
                                            │      │
                                     ┌──────▼──┐ ┌─▼──────┐
                                     │Postgres │ │ Redis  │
                                     └─────────┘ └────────┘
```

- **Traefik** is the only ingress. It terminates TLS, redirects HTTP→HTTPS,
  applies edge middleware (security headers, compression), and routes by
  hostname. Databases are on an internal network with no published ports in
  production.
- **web** renders the public site and server-side pages. It talks to the API
  over the internal network (`PB_WEB_API_INTERNAL_URL`) using the shared
  `@pb/api-client` package; browsers use `NEXT_PUBLIC_API_URL` through Traefik.
- **api** owns all business logic and persistence. It is stateless — sessions
  are JWTs, shared state lives in PostgreSQL/Redis — so it scales
  horizontally.
- **migrations** run as a one-shot container (`alembic upgrade head`) that the
  API waits on; app containers never mutate schema at import time.

## 2. Monorepo layout and boundaries

| Path         | Role                                 | May depend on           |
| ------------ | ------------------------------------ | ----------------------- |
| `apps/api`   | Deployable FastAPI service           | nothing in `apps/`      |
| `apps/web`   | Deployable Next.js app               | `packages/*`            |
| `packages/*` | Shared JS/TS libraries               | other `packages/*`      |
| `shared/`    | Cross-language contracts (OpenAPI)   | — (generated artifacts) |
| `infra/`     | Infrastructure config (Traefik, ...) | —                       |
| `scripts/`   | Operational scripts                  | apps (read-only)        |
| `tests/e2e`  | Black-box tests of the running stack | public interfaces only  |

Rules that keep the monorepo healthy:

1. **Apps never import from other apps.** Cross-app communication happens over
   HTTP contracts (the OpenAPI spec in `shared/openapi/`), never through code.
2. **Each app is independently deployable** — its own Dockerfile, its own
   dependency lockfile scope, its own health endpoints and metrics.
3. **Shared code is promoted deliberately**: copy once is fine; the second
   consumer moves it into `packages/` (TS) or a future `libs/` (Python).
4. **Contracts are generated, not hand-maintained**: `make openapi` exports
   the spec from the live FastAPI app; `@pb/api-client` mirrors it and is
   covered by unit tests.

## 3. Backend design (`apps/api`)

```
src/pb_api/
├── main.py          # create_app() factory; module-level `app` for uvicorn
├── cli.py           # operational CLI (create-admin)
├── core/            # cross-cutting: config, logging, security, redis
├── db/              # SQLAlchemy base, session wiring, models
├── middleware/      # request context, secure headers, metrics, rate limit
├── api/             # HTTP layer: deps (DI), router, routes/
├── schemas/         # Pydantic request/response models
└── services/        # domain logic (no HTTP concerns)
```

Layering: `routes → services → models`. Route handlers stay thin — they
translate HTTP to service calls and domain errors to HTTP errors. Services
contain the rules and are testable without HTTP.

Key mechanics:

- **App factory + state.** `create_app(settings)` builds an isolated app;
  engine, session factory, Redis client, and the Prometheus registry live on
  `app.state`. Tests construct as many apps as they need without global
  leakage.
- **Configuration** (`core/config.py`) is a Pydantic Settings class sourcing
  `PB_API_*` environment variables. Production boot fails fast on placeholder
  secrets, wildcard CORS, or a non-PostgreSQL database URL.
- **Auth**: Argon2id (pwdlib) password hashes; HS256 JWTs with distinct
  `access`/`refresh` types, issuer validation, and `jti` claims so a
  revocation store can be added without changing token format. Self-service
  registration only ever creates `client` users; `admin`/`staff` are
  provisioned via `python -m pb_api.cli create-admin`.
- **RBAC**: `require_roles(UserRole.ADMIN, ...)` dependency; the access token
  carries the role claim, the database record is authoritative.
- **Rate limiting**: fixed-window per client IP, Redis-backed (correct across
  replicas) with an in-memory fallback; fails open if Redis is down. Health
  and metrics endpoints are exempt.
- **Observability**: structlog JSON logs (console renderer in development)
  with request IDs propagated from/to `X-Request-ID`; Prometheus metrics at
  `/metrics` (`http_requests_total`, `http_request_duration_seconds`,
  in-flight gauge) labelled by route template, never raw URL.
- **Health**: `/api/v1/health/live` (process up) vs `/api/v1/health/ready`
  (PostgreSQL + Redis checked, 503 with per-dependency detail when degraded).

### Database & migrations

SQLAlchemy 2.0 async (asyncpg driver). All schema changes go through Alembic;
`alembic/env.py` resolves the URL from settings (or `-x db_url=...`).
The declarative base pins a naming convention so autogenerated constraint
names are deterministic. Models use portable column types (`Uuid`,
non-native enums) so the suite can run on SQLite while production runs
PostgreSQL; CI runs the tests against both and exercises
upgrade → downgrade → upgrade on real PostgreSQL.

## 4. Frontend design (`apps/web`)

Next.js 15 App Router with server components by default. Tailwind v4 +
shadcn/ui primitives (`components/ui/`) hand-vendored so the design system is
owned by the repo. `src/lib/env.ts` centralises environment access —
`PB_WEB_API_INTERNAL_URL` for server-side calls, `NEXT_PUBLIC_API_URL` for the
browser. The `/status` page demonstrates the canonical data path: server
component → `@pb/api-client` → API, with explicit unreachable/degraded states
(the page never 500s because a dependency is down). `output: "standalone"`
keeps the Docker image minimal.

## 5. Security model

- TLS terminates at Traefik (ACME in production); internal traffic stays on
  the compose networks. HSTS is emitted in production only.
- The API sets `default-src 'none'` CSP, nosniff, frame-deny, no-referrer,
  and `Cache-Control: no-store` on every response.
- CORS is an explicit origin allowlist from settings; wildcard is rejected in
  production.
- `trust_proxy_headers` gates whether `X-Forwarded-For` is honoured for rate
  limiting — enabled only when the API sits behind our proxy.
- Secrets enter exclusively via environment (12-factor); `.env` files are
  git-ignored, `.env.example` documents every variable, and production
  deployments are expected to inject secrets from an external store.

## 6. Observability

Every request produces one structured access-log line (method, path, status,
duration, request ID, client) and Prometheus series. A future Prometheus +
Grafana (or hosted equivalent) scrapes `/metrics`; logs are JSON-per-line and
collector-ready. Readiness gives orchestrators the signal to pull an instance
out of rotation while liveness stays green.

## 7. Module registry and growth path (beyond Phase 1)

The product modules the platform is designed to host are declared in a single
authoritative registry — `apps/api/src/pb_api/platform/modules.py` — and served
at `GET /api/v1/platform/modules`. Each entry reserves a stable API namespace,
records lifecycle status (`available` / `planned`), and — for modules that
contact customers or prospects — the compliance controls a future
implementation must ship with. Reserving namespaces in a tested registry
(rather than leaving empty stub packages) keeps the codebase free of
placeholder logic while committing to a stable layout. See
[ADR-0008](adr/0008-modular-namespace-reservation.md) and
[ADR-0009](adr/0009-outreach-compliance-guardrails.md).

Reserved product namespaces: `marketing` (Marketing Website), `crm`, `portal`
(Client Portal), `ai` (AI Services), `billing` (Billing & Invoicing),
`ticketing`, `kb` (Knowledge Base), `proposals` (Proposal Engine), `outbound`
(Outbound Sales Engine — compliance-gated).

| Future capability        | Where it lands                                                               |
| ------------------------ | ---------------------------------------------------------------------------- |
| CRM / Ticketing / KB     | New routers + services + models in `apps/api`; UI in `apps/web` or a new app |
| Client portal            | `apps/portal` (own deployable), reusing `@pb/api-client` + `packages/ui`     |
| AI services              | `apps/ai` FastAPI service behind Traefik; contracts in `shared/`             |
| Background jobs          | Worker service consuming Redis (arq/celery), same image as api               |
| Token revocation         | Redis/PG-backed session store keyed by the `jti` already in tokens           |
| Fine-grained permissions | Permission tables layered under the existing role dependency                 |
| Multi-tenancy            | Tenant column + scoping in services (single choke-point for queries)         |

The invariants to preserve: apps stay independently deployable, contracts stay
generated, services own business rules, and every new surface ships with
health endpoints, metrics, and tests from day one.

Architectural decisions are recorded as ADRs in [`adr/`](adr/).
