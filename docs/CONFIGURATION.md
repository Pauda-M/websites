# PB Platform — Configuration Reference

Every runtime knob in the platform is an environment variable. This document is
the complete reference. It complements the narrative in `docs/DEPLOYMENT.md` and
`docs/DEVELOPER_GUIDE.md`; those explain _when_ to set things, this explains
_what every variable is_.

Three sources define the surface:

- **API service** — the Pydantic `Settings` class in
  `apps/api/src/pb_api/core/config.py`. Every field maps to an environment
  variable with the **`PB_API_`** prefix. A field is read only through this
  class; nothing else in the API reads `os.environ`.
- **Web app** — `apps/web/src/lib/env.ts` plus the `web` service in
  `docker-compose.yml`.
- **Infrastructure / Compose** — `.env.example` and the compose files, consumed
  by Traefik, PostgreSQL, Redis, and the migrations/api services.

## Precedence and formats

- **A real environment variable always wins over a value in a `.env` file.** The
  API's `Settings` reads process env first and falls back to `.env`
  (`env_file=".env"`); the compose stack sets variables explicitly on each
  service. `.env` is git-ignored; `.env.example` is the documented template.
- **`PB_API_*` beats the shared cross-stack name.** Three settings accept either
  name via `AliasChoices`, with the service-specific name winning:
  `PB_API_ENVIRONMENT` over `PB_ENVIRONMENT`, `PB_API_DATABASE_URL` over
  `DATABASE_URL`, `PB_API_REDIS_URL` over `REDIS_URL`.
- **`PB_API_CORS_ORIGINS` is a JSON array**, e.g.
  `["https://pbsolutions.example"]`.
- **`NEXT_PUBLIC_*` is inlined at build time.** Because Next.js bakes
  `NEXT_PUBLIC_*` into the browser bundle during `next build`, `NEXT_PUBLIC_API_URL`
  is passed as a Docker **build arg** (not just a runtime env var). Changing it
  requires rebuilding the web image — see `docs/TROUBLESHOOTING.md`.

## API service settings (`PB_API_*`)

Defaults below are the code defaults from `core/config.py`. "Required in prod"
means the value must be set to a real value for a production deploy (some are
enforced by the boot-time validation described further down).

| Variable                                | Default                                                 | Purpose                                                                        | Required in prod            |
| --------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------ | --------------------------- |
| `PB_API_APP_NAME`                       | `pb-api`                                                | Service name; also the JWT issuer (`iss`) claim and liveness `service` field.  | No                          |
| `PB_API_ENVIRONMENT` / `PB_ENVIRONMENT` | `development`                                           | Runtime mode (`development`/`staging`/`production`/`test`); gates hardening.   | Yes (`production`)          |
| `PB_API_DEBUG`                          | `false`                                                 | SQLAlchemy engine `echo`; verbose diagnostics.                                 | No (keep `false`)           |
| `PB_API_DATABASE_URL` / `DATABASE_URL`  | `postgresql+asyncpg://pb:pb@localhost:5432/pb_platform` | Async SQLAlchemy database URL.                                                 | Yes (must be PostgreSQL)    |
| `PB_API_DATABASE_POOL_SIZE`             | `10`                                                    | Connection pool size (PostgreSQL only; ignored for SQLite).                    | No                          |
| `PB_API_DATABASE_MAX_OVERFLOW`          | `20`                                                    | Max overflow connections beyond the pool (PostgreSQL only).                    | No                          |
| `PB_API_REDIS_URL` / `REDIS_URL`        | _unset_ (`None`)                                        | Redis URL; enables the Redis rate-limiter and the readiness Redis check.       | Recommended                 |
| `PB_API_SECRET_KEY`                     | `dev-only-secret-key-change-me-…` (placeholder)         | JWT signing secret (`SecretStr`).                                              | Yes (≥32 chars, real)       |
| `PB_API_JWT_ALGORITHM`                  | `HS256`                                                 | JWT signing algorithm.                                                         | No                          |
| `PB_API_ACCESS_TOKEN_EXPIRE_MINUTES`    | `15`                                                    | Access-token lifetime (minutes).                                               | No                          |
| `PB_API_REFRESH_TOKEN_EXPIRE_MINUTES`   | `20160` (14 days)                                       | Refresh-token lifetime (minutes).                                              | No                          |
| `PB_API_PASSWORD_MIN_LENGTH`            | `10`                                                    | Minimum password length enforced at registration/provisioning.                 | No                          |
| `PB_API_CORS_ORIGINS`                   | `["http://localhost:3000"]`                             | JSON array of allowed browser origins. Wildcard `*` rejected in production.    | Yes (real allowlist)        |
| `PB_API_TRUST_PROXY_HEADERS`            | `false`                                                 | Honour `X-Forwarded-For` for rate-limit client identity (enable behind proxy). | Yes (`true` behind Traefik) |
| `PB_API_RATE_LIMIT_ENABLED`             | `true`                                                  | Master switch for the rate-limit middleware.                                   | No                          |
| `PB_API_RATE_LIMIT_PER_MINUTE`          | `120`                                                   | Fixed-window request budget per client IP per minute.                          | No                          |
| `PB_API_LOG_LEVEL`                      | `INFO`                                                  | Root log level (applied to the structlog/stdlib pipeline).                     | No                          |
| `PB_API_LOG_JSON`                       | _unset_ (`None`)                                        | Force JSON (`true`) or console (`false`) logs; unset → JSON except dev/test.   | No                          |
| `PB_API_METRICS_ENABLED`                | `true`                                                  | Register the `/metrics` endpoint.                                              | No                          |

In the compose stack, `PB_API_DATABASE_URL` is composed from the `POSTGRES_*`
variables, `PB_API_REDIS_URL` is set to `redis://redis:6379/0`, and
`PB_API_TRUST_PROXY_HEADERS` is set to `true` (the API sits behind Traefik).

## Web app settings

| Variable                  | Component | Default (code / compose)                          | Purpose                                                                          | Required in prod |
| ------------------------- | --------- | ------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------- |
| `PB_WEB_API_INTERNAL_URL` | web       | `http://localhost:8000` / `http://api:8000`       | Server-side base URL the web app uses to reach the API over the private network. | Yes              |
| `NEXT_PUBLIC_API_URL`     | web       | `http://localhost:8000` / `https://api.localhost` | Browser-facing API base URL. **Build-time inlined** (Docker build arg).          | Yes              |

The two are read only through `apps/web/src/lib/env.ts` (`env.API_INTERNAL_URL`
and `env.NEXT_PUBLIC_API_URL`); components never touch `process.env` directly.
Server-side calls (e.g. the `/status` page) use the internal URL; browser calls
use the public URL through Traefik. The two never cross, so internal hostnames
never reach the client.

## Infrastructure / Compose variables

From `.env.example`, consumed by the compose files. Variables marked "required"
use the `${VAR:?...}` form in compose and will abort `docker compose` if unset.

| Variable               | Component       | Default (`.env.example`)          | Purpose                                                        | Required in prod |
| ---------------------- | --------------- | --------------------------------- | -------------------------------------------------------------- | ---------------- |
| `PB_ENVIRONMENT`       | all             | `development`                     | Shared environment mode; the prod overlay forces `production`. | Yes              |
| `COMPOSE_PROJECT_NAME` | compose         | `pb-platform`                     | Compose project name.                                          | No               |
| `PB_DOMAIN`            | traefik         | `localhost`                       | Base domain; web on the apex, API on `api.${PB_DOMAIN}`.       | Yes              |
| `PB_ACME_EMAIL`        | traefik (prod)  | `admin@example.com`               | Let's Encrypt registration/expiry email (required by overlay). | Yes              |
| `POSTGRES_USER`        | postgres, api   | `pb`                              | Database user (required by compose).                           | Yes              |
| `POSTGRES_PASSWORD`    | postgres, api   | `change-me-in-production`         | Database password (required by compose).                       | Yes              |
| `POSTGRES_DB`          | postgres, api   | `pb_platform`                     | Database name (required by compose).                           | Yes              |
| `POSTGRES_PORT`        | postgres        | `5432`                            | Host-published port (loopback only; removed by prod overlay).  | No               |
| `REDIS_PORT`           | redis           | `6379`                            | Host-published port (loopback only; removed by prod overlay).  | No               |
| `PB_API_SECRET_KEY`    | api, migrations | `dev-only-secret-key-change-me-…` | JWT signing secret (required by compose; validated in prod).   | Yes              |

The compose stack also passes `PB_API_ACCESS_TOKEN_EXPIRE_MINUTES`,
`PB_API_REFRESH_TOKEN_EXPIRE_MINUTES`, `PB_API_LOG_LEVEL`,
`PB_API_RATE_LIMIT_PER_MINUTE`, and `PB_API_CORS_ORIGINS` through with the
defaults shown in `.env.example`.

## Production-hardening rules (why the API refuses to boot)

When `environment == "production"`, a Pydantic validator in `core/config.py`
(`_validate_production_hardening`) aborts startup if any of these hold:

1. `PB_API_SECRET_KEY` is **shorter than 32 characters**.
2. `PB_API_SECRET_KEY` contains a **placeholder marker** — any of `dev-only`,
   `change-me`, `changeme`, `secret-key`, `example` (case-insensitive).
3. The CORS origins list **contains `*`** (wildcard).
4. `PB_API_DATABASE_URL` **does not start with `postgresql`**.

The failure is loud and immediate (a `ValueError` at construction), so a
misconfigured production deploy fails at start rather than quietly at runtime.
See `docs/TROUBLESHOOTING.md` for the exact symptoms.

## Notes on specific behaviours

- **Redis is optional.** With `PB_API_REDIS_URL` unset, the API falls back to an
  in-process rate limiter and readiness reports `redis: skipped`
  (`core/redis.py`). Configure Redis in any multi-replica deployment so the rate
  limiter is correct across replicas.
- **Docs/`docs/` in production.** With `environment == production`, the API
  disables `/docs`, `/redoc`, and `/openapi.json` (`main.py`).
- **Token lifetimes.** The compose default for
  `PB_API_REFRESH_TOKEN_EXPIRE_MINUTES` is `20160` minutes = 14 days, matching
  the code default.
