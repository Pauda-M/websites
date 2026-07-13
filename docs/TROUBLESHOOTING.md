# PB Platform — Troubleshooting

Symptom → cause → fix for the failures you are most likely to hit. Commands run
from the repository root. See `docs/OPERATIONS.md` for routine operations and
`docs/CONFIGURATION.md` for the full variable reference.

## Quick reference

| Symptom                                      | Likely cause                                               | Fix                                                                   |
| -------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------- |
| API container crashes on boot                | Placeholder/short secret or non-Postgres URL in production | Set a real `PB_API_SECRET_KEY` (≥32 chars) and a `postgresql` URL     |
| `/api/v1/health/ready` returns 503           | PostgreSQL or Redis unreachable                            | Read the `checks` field to see which; restart/repair that dependency  |
| `migrations` service exits non-zero          | Database not reachable, or a bad migration, or bad config  | `docker compose logs migrations`; fix DB/config or the revision       |
| `/status` shows "API unreachable"            | Wrong `PB_WEB_API_INTERNAL_URL` or api not on the network  | Point it at `http://api:8000`; confirm api is healthy                 |
| Browser calls the API at `localhost`         | `NEXT_PUBLIC_API_URL` baked into the old build             | Rebuild the web image with the correct build arg                      |
| HTTP 429 responses                           | Rate limit exceeded                                        | Back off per `Retry-After`; raise `PB_API_RATE_LIMIT_PER_MINUTE`      |
| Browser cert warning / 404 locally           | Traefik default self-signed cert; or unmatched router      | Expected locally; for 404 check `PB_DOMAIN` and service labels        |
| `variable is not set` from `docker compose`  | No `.env` file                                             | `cp .env.example .env`                                                |
| Playwright "Executable doesn't exist"        | No Chromium for Playwright                                 | `pnpm exec playwright install chromium` or set the executable env var |
| `frozen-lockfile` / `--frozen` install fails | Lockfile out of sync with manifest                         | Update and commit the lockfile (`pnpm install` / `uv sync`)           |

## API container crashes on boot (production hardening)

**Symptom.** In production the API process exits immediately instead of serving;
logs show a `ValueError` from configuration, e.g. _"PB_API_SECRET_KEY looks like
a placeholder; set a real secret"_ or _"Production requires a PostgreSQL
DATABASE_URL"_.

**Cause.** With `PB_ENVIRONMENT=production`, the settings validator in
`core/config.py` refuses to construct — and `app = create_app()` builds settings
at import — so the process never starts. This is intentional: misconfiguration
fails loudly at boot, not quietly at runtime. Triggers are a secret shorter than
32 characters, a secret containing a placeholder marker (`dev-only`, `change-me`,
`changeme`, `secret-key`, `example`), a `*` in `PB_API_CORS_ORIGINS`, or a
`PB_API_DATABASE_URL` that does not start with `postgresql`.

> Note: this manifests as a **boot-time crash / non-zero exit**, not an HTTP 500
> served to a client — the process cannot start to answer requests.

**Fix.** Set a real secret (`openssl rand -base64 48`), a real origin allowlist
(`["https://your-domain"]`, no `*`), and a PostgreSQL database URL. See
`docs/CONFIGURATION.md`. The same validation runs for the `migrations` service,
so a bad config also fails migrations.

## Readiness returns 503

**Symptom.** `GET /api/v1/health/ready` returns 503 with
`{"status": "degraded", "checks": {...}}`, and load balancers stop routing to the
instance. Liveness (`/live`) still returns 200.

**Cause.** A dependency is unreachable. The `checks` object tells you **which**:

- `"database": "error"` — PostgreSQL is down or unreachable (the `SELECT 1`
  failed).
- `"redis": "error"` — Redis is down or unreachable (the `PING` failed).
- `"redis": "skipped"` — Redis is not configured (`PB_API_REDIS_URL` unset); this
  is neutral, not a failure.

**Fix.** Inspect and repair the failing dependency:
`docker compose ps` and `docker compose logs postgres` (or `redis`). Once the
dependency is healthy, readiness returns to 200 on the next probe. The API also
logs `readiness_database_failed` / `readiness_redis_failed` with the error.

## Migrations service exits non-zero

**Symptom.** `docker compose ps` shows `migrations` as `Exited (1)` and the `api`
never starts (it depends on migrations completing successfully).

**Cause.** `alembic upgrade head` failed — commonly because PostgreSQL was not
reachable, a revision itself errored, or the production config validation
rejected the environment (the migrations service constructs the same settings).

**Fix.** Read the logs: `docker compose logs migrations`. If the database was not
ready, re-run `docker compose run --rm migrations`. If a revision is broken, fix
the migration under `apps/api/alembic/versions/`; if config was rejected, correct
the environment (see the boot-crash section above).

## Web `/status` shows "API unreachable"

**Symptom.** The status page renders the red _"API unreachable — did not respond
within 3 seconds"_ card.

**Cause.** The server-side call from the web app to the API failed, timed out, or
returned a malformed response. The page uses `env.API_INTERNAL_URL` (from
`PB_WEB_API_INTERNAL_URL`) with a 3-second timeout and renders "unreachable"
rather than 500-ing. Usual causes: `PB_WEB_API_INTERNAL_URL` pointing at the
wrong host, the web container not sharing a network with the api, or the api
being down.

**Fix.** Confirm the api is healthy (`curl` its `/health/ready`) and that
`PB_WEB_API_INTERNAL_URL` is the internal address (`http://api:8000` in the
compose stack). Note this is the **server-side** URL — distinct from the
browser-facing `NEXT_PUBLIC_API_URL`.

## Browser calls the API at `localhost` (wrong public URL)

**Symptom.** In the browser, network calls go to `http://localhost:8000` (or the
wrong host) even though `NEXT_PUBLIC_API_URL` is set correctly in the running
container's environment.

**Cause.** `NEXT_PUBLIC_*` variables are **inlined into the browser bundle at
build time** by Next.js. Setting `NEXT_PUBLIC_API_URL` only at runtime has no
effect on an already-built image — the old value is baked in. The compose `web`
service therefore passes it as a Docker **build arg**.

**Fix.** Rebuild the web image with the correct value:
`docker compose build --build-arg NEXT_PUBLIC_API_URL=https://api.your-domain web`
(or set `NEXT_PUBLIC_API_URL` in `.env` and `docker compose up -d --build web`).
The prod overlay derives it from `PB_DOMAIN`. See ADR-0004.

## HTTP 429 (rate limited)

**Symptom.** Requests get `429` with `{"detail": "Rate limit exceeded"}` and a
`Retry-After` header.

**Cause.** The caller exceeded `PB_API_RATE_LIMIT_PER_MINUTE` (default 120)
requests in the current one-minute window for its client IP.

**Fix.** Honour `Retry-After` (seconds until the window resets). If legitimate
traffic is being throttled, raise `PB_API_RATE_LIMIT_PER_MINUTE`. Behind a proxy,
ensure `PB_API_TRUST_PROXY_HEADERS=true` so the real client IP is used instead of
Traefik's (otherwise all traffic shares one bucket). Health and metrics paths are
never rate limited.

## Traefik: cert warnings or 404 locally

**Symptom.** Browsers warn about an untrusted certificate at `https://localhost`
/ `https://api.localhost`, or a route returns 404.

**Cause.** Locally Traefik serves its **default self-signed certificate** (no
ACME without a public domain) — the warning is expected outside production. A 404
usually means the request `Host` did not match any router: Traefik only exposes
containers with `traefik.enable=true` labels, and routers match
`Host(${PB_DOMAIN})` / `Host(api.${PB_DOMAIN})`.

**Fix.** Accept the local certificate warning (it is expected). For a 404, check
that `PB_DOMAIN` matches the host you are requesting and that the target service
is `Up` with its Traefik labels intact (`docker compose ps`,
`docker compose logs traefik`).

## `docker compose`: "variable is not set"

**Symptom.** `docker compose ...` aborts with an error like
_"POSTGRES_USER: set in .env"_ / _"variable is not set"_.

**Cause.** Required variables use the `${VAR:?...}` form and there is no `.env`
file (or the variable is missing from it) — e.g. `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `PB_API_SECRET_KEY`, or (prod)
`PB_DOMAIN`/`PB_ACME_EMAIL`.

**Fix.** `cp .env.example .env` and fill in real values. Validate before
deploying: `docker compose config --quiet` (or `make compose-config`).

## Playwright: "Executable doesn't exist"

**Symptom.** `make test-e2e` fails with a Playwright error that the Chromium
executable is missing.

**Cause.** Playwright needs a browser binary that is not installed in this
environment.

**Fix.** Install it: `cd tests/e2e && pnpm exec playwright install chromium`
(on a fresh machine use `--with-deps` to pull the OS libraries too). In a
sandbox that already ships a Chromium, point Playwright at it instead of
installing:
`PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chromium make test-e2e` — the e2e config
reads that variable and sets `launchOptions.executablePath` when present
(`tests/e2e/playwright.config.ts`).

## Frozen-lockfile mismatches (pnpm / uv)

**Symptom.** A clean install fails: `pnpm install --frozen-lockfile` reports the
lockfile is out of date, or `uv sync --frozen` reports the lock is stale.

**Cause.** A manifest (`package.json` / `pyproject.toml`) changed without its
lockfile (`pnpm-lock.yaml` / `apps/api/uv.lock`) being regenerated and committed.
Frozen installs (used for reproducible builds) fail on any such drift.

**Fix.** Regenerate and commit the lockfile: run `pnpm install` (writes
`pnpm-lock.yaml`) or `cd apps/api && uv sync` (writes `uv.lock`), then commit the
updated lockfile alongside the manifest change.
