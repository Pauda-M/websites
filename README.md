# PB Platform

The operating system of **PB Solutions** — a production monorepo that hosts the
consulting website today and is architected to grow into the full product
suite: CRM, client portal, AI services, blog, ticketing, knowledge base,
proposal generator, invoicing, and internal admin.

## Stack

| Layer      | Technology                                                           |
| ---------- | -------------------------------------------------------------------- |
| Frontend   | Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui      |
| Backend    | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2                  |
| Data       | PostgreSQL 17, Redis 7                                               |
| Edge       | Traefik v3 (TLS termination, routing, security headers)              |
| Auth       | JWT (access + refresh), Argon2id password hashing, role-based access |
| Quality    | Ruff, Black, MyPy (strict), ESLint, Prettier                         |
| Testing    | Pytest, Vitest, Playwright                                           |
| Validation | Local `make` gates (lint → types → tests → build → compose config)   |

## Repository layout

```
apps/          Deployable applications
  api/         FastAPI service — auth, RBAC, health, metrics (own Dockerfile)
  web/         Next.js site — landing + live status page (own Dockerfile)
packages/      Shared JS/TS libraries
  api-client/  Typed client for the API (consumed by apps/web)
  tsconfig/    Shared TypeScript configurations
shared/        Cross-language contracts
  openapi/     OpenAPI spec exported from the API (make openapi)
infra/         Infrastructure configuration
  traefik/     Edge proxy dynamic config (static config is CLI flags in compose)
docs/          Architecture, guides, and Architecture Decision Records (adr/)
scripts/       Operational scripts (OpenAPI export, ...)
tests/
  e2e/         Playwright suite that boots the real API + web app
compound-calculator/  Legacy standalone page (pre-platform, unmanaged)
```

Product modules (CRM, Client Portal, AI Services, Billing, Ticketing, Knowledge
Base, Proposal Engine, Marketing Website, Outbound Sales Engine) have reserved,
loosely-coupled API namespaces declared in the platform module registry
(`apps/api/src/pb_api/platform/modules.py`) and served at
`GET /api/v1/platform/modules`.

Root-level `docker-compose.yml` runs the full stack; `docker-compose.prod.yml`
layers production hardening on top. The `Makefile` is the canonical entry
point for every workflow — run them locally before every commit.

## Quick start

Prerequisites: Node 22+, pnpm 10+, Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
# 1. Install everything
make setup

# 2. Run the API. It needs PostgreSQL — start one with `make up-db`,
#    or point it at SQLite for a quick, dependency-free look:
PB_API_DATABASE_URL=sqlite+aiosqlite:///dev.db make migrate dev-api  # http://localhost:8000 (/docs)

# 3. Run the web app
make dev-web        # http://localhost:3000

# — or run the whole stack in containers —
cp .env.example .env
make up             # https://localhost (web), https://api.localhost (API)
```

## Quality gates

```bash
make lint           # ruff + black --check + eslint
make typecheck      # mypy (strict) + tsc across all workspaces
make test           # pytest + vitest
make test-e2e       # playwright against the real, booted stack
make format         # auto-fix formatting everywhere
```

All of these must pass locally before a commit lands — this project runs no CI
service, so the `make` gates are the enforcement point.

## Governance

[`AI_DEPLOY_AUTHORIZATION.md`](AI_DEPLOY_AUTHORIZATION.md) is the governing
authority for this repository — engineering standards, security requirements,
the validation loop, and compliance rules. Where any implementation conflicts
with it, the governance document takes precedence.

## Genesis — Autonomous Digital Workforce

The long-term product built on this foundation is **Genesis**: a platform for
deploying **AI Employees** that collaborate through a shared **Company Brain**
under governed autonomy. Its complete architecture specification — the canonical
source of truth every future implementation must follow — lives in
[docs/genesis/](docs/genesis/):

- [000_Glossary.md](docs/genesis/000_Glossary.md) — the binding spine: terminology and locked decisions
- [001_Vision.md](docs/genesis/001_Vision.md) · [002_System_Architecture.md](docs/genesis/002_System_Architecture.md) · [003_Cognitive_Architecture.md](docs/genesis/003_Cognitive_Architecture.md) · [004_Company_Brain.md](docs/genesis/004_Company_Brain.md)
- [005_Event_Model.md](docs/genesis/005_Event_Model.md) · [006_Agent_Runtime.md](docs/genesis/006_Agent_Runtime.md) · [007_AI_Employees.md](docs/genesis/007_AI_Employees.md) · [008_Memory_Engine.md](docs/genesis/008_Memory_Engine.md)
- [009_Knowledge_Graph.md](docs/genesis/009_Knowledge_Graph.md) · [010_Workflow_Engine.md](docs/genesis/010_Workflow_Engine.md) · [011_ML_Platform.md](docs/genesis/011_ML_Platform.md) · [012_Security.md](docs/genesis/012_Security.md)
- [013_APIs.md](docs/genesis/013_APIs.md) · [014_Data_Model.md](docs/genesis/014_Data_Model.md) · [015_Roadmap.md](docs/genesis/015_Roadmap.md)
- [016_Cognitive_Core.md](docs/genesis/016_Cognitive_Core.md) — Cognitive Core implementation reference (Phase 7)

Genesis is event-driven and modular by construction: it depends on ports (never
vendors), reserves loosely-coupled module namespaces (see the module registry
above), and keeps autonomy governed (explicit authority levels, human-in-the-loop,
and the outreach-compliance controls). Phase 1 here is its foundation; the
roadmap in `015_Roadmap.md` sequences the build. The **Cognitive Core** (Phase 7)
is implemented under `apps/api/src/pb_api/cognitive` and served at
`/api/v1/cognitive` — see `016_Cognitive_Core.md` and
[ADR-0010](docs/adr/0010-cognitive-core.md).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, boundaries, and how the platform grows
- [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) — day-to-day workflows, adding endpoints/pages/migrations
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — every environment variable and the production-hardening rules
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — running the stack in production
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — day-2 operations: deploys, backups, scaling, migrations
- [docs/SECURITY.md](docs/SECURITY.md) — security model, posture, and hardening roadmap
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — symptom → cause → fix for common issues
- [docs/adr/](docs/adr/) — Architecture Decision Records

## Security posture (phase 1)

- Argon2id password hashing, JWT access (15 min) + refresh (14 d) tokens with type separation and `jti`
- RBAC roles (`admin` / `staff` / `client`) enforced by dependency injection
- Strict security headers, locked-down CORS, IP rate limiting (Redis-backed)
- Settings validation refuses production boot with placeholder secrets,
  wildcard CORS, or a non-PostgreSQL database
- TLS at the edge via Traefik; HSTS in production
