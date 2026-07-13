# PB Platform — Developer Guide

Everything you need for day-to-day work. All commands run from the repository
root unless stated otherwise; the `Makefile` targets are the canonical
interface, run locally before every commit.

## 1. Prerequisites

| Tool   | Version | Notes                                       |
| ------ | ------- | ------------------------------------------- |
| Node   | 22+     | `.nvmrc` provided                           |
| pnpm   | 10+     | pinned via `packageManager` in package.json |
| Python | 3.11+   | managed per-project by uv                   |
| uv     | latest  | https://docs.astral.sh/uv/                  |
| Docker | 24+     | for the full stack + Compose validation     |

## 2. First-time setup

```bash
make setup          # uv sync (apps/api) + pnpm install (workspace)
cp .env.example .env   # only needed for docker compose
```

## 3. Running things

| Command        | What it does                                            |
| -------------- | ------------------------------------------------------- |
| `make dev-api` | uvicorn with reload on :8000 (Swagger UI at `/docs`)    |
| `make dev-web` | Next.js dev server on :3000                             |
| `make up`      | Full containerised stack behind Traefik (see below)     |
| `make migrate` | `alembic upgrade head` against your configured database |

Without any configuration the API falls back to
`postgresql+asyncpg://pb:pb@localhost:5432/pb_platform`. For a quick
database-free run: `PB_API_DATABASE_URL=sqlite+aiosqlite:///dev.db make migrate dev-api`.

With `make up`: web at https://localhost, API at https://api.localhost
(Traefik serves its default certificate locally — browsers will warn; that is
expected outside production).

### Provisioning an admin user

```bash
cd apps/api && uv run python -m pb_api.cli create-admin \
  --email admin@example.com --full-name "Ada Admin"
# omit --password to have a strong one generated and printed once
```

## 4. Quality gates (run before every commit)

```bash
make format      # ruff --fix + black + prettier (writes changes)
make lint        # ruff + black --check + eslint
make typecheck   # mypy (strict) + tsc for every TS workspace
make test        # pytest (apps/api) + vitest (web, api-client)
make test-e2e    # playwright: boots real api + web and drives a browser
```

These are the required gates and they run locally — this project has no CI
service; validation is done on the developer's machine before every commit.
For a full-stack smoke test, `make up` then check the health endpoints
(`docs/OPERATIONS.md`). A red gate is a broken build — fix it before you push.

Sandboxed environments with a preinstalled Chromium can point Playwright at
it: `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium make test-e2e`.

## 5. Backend workflows (`apps/api`)

### Layout

Routes (`api/routes/`) translate HTTP ↔ domain. Services (`services/`) own
business rules. Models (`db/models/`) own persistence. Schemas (`schemas/`)
are the wire format. Cross-cutting concerns live in `core/` and `middleware/`.

### Adding an endpoint

1. Define request/response models in `schemas/`.
2. Put the business logic in a service function (raise domain exceptions).
3. Add the route in `api/routes/`, mapping domain exceptions to `HTTPException`.
4. Register new routers in `api/router.py`.
5. Write tests (`tests/`) through the HTTP layer with the `client` fixture.
6. `make openapi` to refresh `shared/openapi/openapi.json`; extend
   `packages/api-client` if the endpoint is consumed from TS.

### Adding a model + migration

1. Create the model under `db/models/` and import it in `db/models/__init__.py`
   (that import is what makes autogenerate and `create_all` see it).
2. Generate a migration (needs a running PostgreSQL, e.g. `make up-db`):
   ```bash
   cd apps/api && uv run alembic revision --autogenerate -m "add invoices table"
   ```
   Review the generated file — autogenerate is a draft, not a decision. Keep
   column types portable (see `0001_create_users_table.py`).
3. `uv run alembic upgrade head`, then run the test suite: migration tests
   assert the chain builds and tears down cleanly.

### Configuration

All settings are `PB_API_*` env vars parsed by `core/config.py` (see
`.env.example` for the full list). Add new settings there — never read
`os.environ` elsewhere. Anything secret must have no committed real value.

### Auth in practice

- `CurrentUser` dependency → any authenticated user.
- `require_roles(UserRole.ADMIN)` in `dependencies=[...]` → RBAC guard.
- Access tokens expire in 15 min; clients refresh via `POST /api/v1/auth/refresh`.

### AI Employees (`agents/`)

AI Employees live under `pb_api/agents/`; the **Program Manager**
(`agents/program_manager/`) is the reference implementation. Each employee
composes the Cognitive Core (`CognitiveCore`) for memory, goals, policy,
reflection, and events, and adds its own Domain / Application / Infrastructure /
API layers — it never re-implements the core.

To drive the Program Manager against a dependency-free SQLite database:

```bash
cd apps/api
PB_API_DATABASE_URL=sqlite+aiosqlite:///dev.db uv run alembic upgrade head
PB_API_DATABASE_URL=sqlite+aiosqlite:///dev.db uv run uvicorn pb_api.main:app
# then, against http://localhost:8000/api/v1/agents/program-manager :
#   POST /bootstrap {"tenant_id": "..."}          register + seed policies
#   POST /runs      {"tenant_id","input_text",...} run one cognitive lifecycle pass
#   GET  /runs/{id}/tasks                          inspect per-step execution + approvals
#   POST /tasks/{id}/approve                        approve a paused action
```

Extending it: add domain models under `domain/`, a repository under
`infrastructure/` (mirror `cognitive/repositories/goals.py`), a service under
`application/`, and routes under `api/routes/`. New tables must be tenant-scoped
and covered by an Alembic migration. The authority a new action needs is declared
in `application/authority.py`'s `ACTION_CATALOG`; the deterministic plan a goal
expands into lives in `application/task_planner.py`. Keep outward-transport
effects behind a port — record the prepared artifact and emit an event rather than
assuming a vendor. Tests go under `tests/agents/program_manager/` and run against
real SQLite with no mocks.

## 6. Frontend workflows (`apps/web`)

- Server components by default; add `"use client"` only where interaction
  demands it.
- Environment access goes through `src/lib/env.ts` — never sprinkle
  `process.env` through components.
- API calls use `@pb/api-client` (`packages/api-client`); extend the client
  (and its tests) rather than hand-rolling `fetch` calls.
- UI primitives live in `src/components/ui/` (shadcn/ui conventions,
  Tailwind v4 CSS variables in `globals.css`; dark mode via the `.dark`
  class).
- Unit tests are Vitest + Testing Library, colocated as `*.test.tsx`.

## 7. Shared packages (`packages/`)

`@pb/api-client` is the typed contract client (kept in lockstep with
`shared/openapi/openapi.json`). `@pb/tsconfig` holds the shared compiler
bases. New shared TS code follows the same shape: `src/`, strict tsconfig
extending `@pb/tsconfig/base.json`, vitest tests, eslint flat config, and an
entry in `pnpm-workspace.yaml` (already wildcarded for `packages/*`).

## 8. End-to-end tests (`tests/e2e`)

The Playwright config boots the real API (uvicorn + SQLite + migrations) and
the real production web build (`next start`), then drives Chromium. No mocks:
if the contract between web and api breaks, these tests break. Keep them
black-box — talk to the apps only over HTTP.

```bash
make test-e2e                 # full run (builds web first)
cd tests/e2e && pnpm run e2e:only   # skip the web rebuild while iterating
```

## 9. Conventions

- **Commits**: imperative mood, scoped subject (`api: add invoice model`),
  body explains _why_ when it isn't obvious. Commit only with green gates.
- **Formatting is law**: Black + Ruff for Python, Prettier for everything
  else. No style debates in review.
- **Types are law**: MyPy strict and `tsc --noEmit` must pass; `Any` and
  `type: ignore` need a justifying comment.
- **No secrets in git**, ever, including tests and fixtures.
- **Every new service** ships with: Dockerfile, health endpoints, metrics,
  structured logs, tests, and an entry in the compose stack.
