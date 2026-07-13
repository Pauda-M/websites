# ADR-0002: Backend stack

## Status

Accepted — 2026-07-13

## Context

The API (`apps/api`) owns all business logic and persistence for PB Platform. It
must be strongly typed, async-first (it fronts PostgreSQL and Redis and will
grow I/O-bound product modules), testable without a running HTTP server, and
able to construct isolated instances for tests. Governance requires production
readiness, dependency injection where appropriate, and no global mutable state
leaking between tests.

## Decision

We build the service on a focused, async-first Python stack:

- **FastAPI** for the HTTP layer — first-class async, dependency injection, and
  automatic OpenAPI generation (which feeds `shared/openapi/` and
  `@pb/api-client`).
- **SQLAlchemy 2.0 (async)** with the **asyncpg** driver for persistence, and
  **Alembic** for migrations (see `apps/api/alembic/`).
- **Pydantic v2** + **pydantic-settings** for request/response schemas and
  configuration.
- **uv** for dependency management and the virtualenv (`apps/api/pyproject.toml`,
  `uv.lock`), with **hatchling** as the build backend.

The service uses an **app-factory pattern**: `create_app(settings)` in
`apps/api/src/pb_api/main.py` builds a fully configured `FastAPI` instance from
an injected `Settings` object, and a module-level `app = create_app()` is what
uvicorn and Docker serve. Per-instance state — the SQLAlchemy engine, session
factory, Redis client, and the Prometheus `CollectorRegistry` — lives on
`app.state` (created in the lifespan context manager), never at import time.
Tests build as many isolated apps as they need without global leakage.

The codebase is layered `routes → services → models`
(`api/routes/` → `services/` → `db/models/`). Route handlers stay thin: they
translate HTTP to service calls and domain exceptions to `HTTPException`.
Services own the business rules and are unit-testable without HTTP. Everything
is `async def` end to end, and CPU-bound work (Argon2id hashing) is pushed off
the event loop with `starlette.concurrency.run_in_threadpool` (see
`services/users.py`). Quality is enforced by Ruff, Black, and MyPy in strict
mode (`pyproject.toml`).

## Alternatives Considered

- **Django (+ DRF).** Batteries-included ORM, admin, and auth would accelerate
  early CRUD, but its historically sync-first core and heavier conventions fit
  an async, service-oriented, contract-first design less cleanly, and the admin
  is not needed. Rejected in favour of a lighter async core we control.
- **Flask.** Minimal and familiar, but async support and typed request modelling
  are bolt-ons rather than first-class, and it lacks FastAPI's automatic OpenAPI
  generation that the contract-first workflow depends on. Rejected.
- **Node/NestJS.** Would unify the language with the frontend, but it forfeits
  Python's data/AI ecosystem — which the planned AI Services module needs — and
  splits nothing usefully. Rejected: language unification is not worth losing
  the Python ecosystem for the service tier.

## Consequences

- The whole request path is async; blocking calls are a bug, and CPU-bound work
  must be explicitly offloaded (as hashing already is).
- The app-factory + `app.state` design makes the test suite fast and hermetic:
  each test can inject its own `Settings` (e.g. SQLite, a fake Redis) and get a
  clean app with its own metrics registry.
- Two toolchains (uv/Python and pnpm/Node) live in one repo; contributors need
  uv installed for backend work.
- Portable model column types (`Uuid`, non-native enums) let the suite run on
  SQLite while production runs PostgreSQL, and CI exercises both.
- MyPy strict and Ruff's security lint (`S`) raise the floor for new code but
  require discipline (justified `type: ignore`/`Any`).

## Future Considerations

- A background worker service (arq/Celery over Redis) sharing the same image for
  jobs that outlive a request, noted as a growth path in `docs/ARCHITECTURE.md`.
- A shared Python `libs/` tree once a second Python service needs common code.
- Read replicas / connection-pool tuning (`database_pool_size`,
  `database_max_overflow` are already settings) when load demands it.
