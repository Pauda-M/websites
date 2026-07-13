# PB Platform — Security

The security model and posture of PB Platform as built in phase 1. This
describes what is implemented and verifiable in the code today, and — clearly
marked — what is roadmap. It complements `docs/ARCHITECTURE.md` (section 5) and
the decisions in `docs/adr/`.

## Authentication

- **JWT, two types.** Access and refresh tokens are signed HS256 JWTs
  (`apps/api/src/pb_api/core/security.py`). The `type` claim separates them, and
  `decode_token(expected_type=...)` rejects a token used as the wrong type.
  Access tokens default to a 15-minute lifetime, refresh tokens to 14 days.
- **Issuer + required claims.** Tokens carry an `iss` claim (the service
  `app_name`) and a random `jti`; decoding validates the issuer and requires
  `sub`, `exp`, `iat`, and `type` to be present.
- **Argon2id password hashing.** Passwords are hashed with Argon2id via `pwdlib`
  (`PasswordHash.recommended()`). Hashing is CPU-bound, so it is offloaded from
  the event loop with `run_in_threadpool` (`services/users.py`).
- **Timing-equalised login.** Authenticating an unknown email still performs a
  dummy Argon2id verification (`dummy_verify`) so the unknown-user and
  bad-password paths take comparable time, blunting user enumeration.
- **Provisioning boundary.** Public registration only creates `client` users;
  `admin`/`staff` accounts exist only through the CLI
  (`python -m pb_api.cli create-admin`). See ADR-0003.

## Authorization (RBAC)

- Roles are `admin`, `staff`, `client` (`db/models/user.py`).
- `require_roles(...)` (`api/deps.py`) is a dependency-injection guard used in
  route `dependencies=[...]` (e.g. `GET /api/v1/users` requires `admin`).
- The current user is always **loaded from the database** and checked for
  `is_active` on every authenticated request; the role claim in the token is a
  convenience, but the database record is authoritative.

## Rate limiting

- **Fixed-window, per client IP**, default 120 requests/minute
  (`PB_API_RATE_LIMIT_PER_MINUTE`), in `middleware/rate_limit.py`.
- **Redis-backed with an in-memory fallback.** With Redis configured, the limiter
  uses an atomic `INCR` + `EXPIRE` pipeline so counting is correct across
  replicas; without Redis it uses a per-process window (correct for a single
  instance).
- **Fails open.** If the Redis backend raises (`RedisError`/`OSError`), the
  request is allowed rather than failing — a limiter outage must not take the API
  down.
- **Exempt paths.** `/api/v1/health`, `/metrics`, `/docs`, `/openapi.json`, and
  `/redoc` are never throttled, so orchestrators and scrapers are not blocked.
- **`X-Forwarded-For` is only trusted when `PB_API_TRUST_PROXY_HEADERS` is
  `true`.** Otherwise the direct socket peer is used, so a client cannot spoof
  its identity by sending the header. Behind Traefik the flag is enabled.
- Over-limit responses are **429** with a `Retry-After` header.

## Response security headers

The API sets these on every response (`middleware/secure_headers.py`, via
`setdefault` so a handler can override):

| Header                      | Value                                                                |
| --------------------------- | -------------------------------------------------------------------- |
| `X-Content-Type-Options`    | `nosniff`                                                            |
| `X-Frame-Options`           | `DENY`                                                               |
| `Referrer-Policy`           | `no-referrer`                                                        |
| `Permissions-Policy`        | `camera=(), microphone=(), geolocation=()`                           |
| `Content-Security-Policy`   | `default-src 'none'; frame-ancestors 'none'`                         |
| `Cache-Control`             | `no-store`                                                           |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` — **production only** |

The CSP is deliberately maximal because the API serves JSON, not HTML. **HSTS is
emitted only in production** (where TLS is guaranteed by Traefik), so local HTTP
development is not poisoned. At the edge, Traefik applies its own
`security-headers` middleware to the web app (`infra/traefik/dynamic/security.yml`),
including nosniff, frame-deny, a referrer policy, a permissions policy, and HSTS.

## CORS

Cross-origin access is an explicit allowlist from `PB_API_CORS_ORIGINS`
(`main.py`), with `allow_credentials=true`, a fixed method set
(`GET, POST, PUT, PATCH, DELETE, OPTIONS`), and a fixed header allowlist
(`Authorization`, `Content-Type`, `X-Request-ID`). A wildcard origin is
**rejected at boot in production** (see below).

## Secrets and production validation

- Secrets enter **only** through the environment (12-factor). `.env` files are
  git-ignored; `.env.example` holds dev-only defaults and documents every
  variable. Nothing secret is committed, including in tests and fixtures.
- In production the API **refuses to boot** (`core/config.py`) if the secret is
  under 32 characters or looks like a placeholder, if CORS contains `*`, or if
  the database URL is not PostgreSQL. See `docs/CONFIGURATION.md` for the exact
  rules.
- The signing secret (`PB_API_SECRET_KEY`) is load-bearing for all token
  security; treat it as the platform's most sensitive value.

## Transport security (edge)

- **Traefik terminates TLS** and is the only ingress (`docker-compose.yml`). The
  HTTP entrypoint redirects to HTTPS; in production certificates come from Let's
  Encrypt via the ACME resolver (`docker-compose.prod.yml`).
- The dynamic TLS options pin **minimum TLS 1.2** and a modern cipher-suite list
  (`infra/traefik/dynamic/security.yml`).
- Internal traffic (web↔api, api↔postgres/redis) stays on the compose networks;
  in production the database ports are not published on the host
  (`ports: !override []`).

## Metrics exposure

`/metrics` is **internal-only**. At the edge a higher-priority Traefik router
applies the `internal-only` `ipAllowList` middleware (loopback + RFC1918 ranges),
so public callers get 403; the endpoint is also exempt from rate limiting and is
not intended to be routed publicly. Prometheus scrapes the API container
directly over the internal network. See ADR-0005 / ADR-0006.

## Input validation and data access

- **Input validation** is via Pydantic v2 models (`schemas/`); request bodies and
  query parameters are typed and bounded (e.g. pagination `limit` is constrained
  `1..200` in `api/routes/users.py`).
- **Database access is parameterised** through SQLAlchemy 2.0 (async). Queries
  are built with the expression language (`select(...).where(User.email == ...)`)
  and bound parameters — no string-interpolated SQL — which prevents SQL
  injection by construction.
- Email is normalised (trimmed, lower-cased) and uniqueness is enforced by a
  database unique index, which is authoritative even under concurrent signups.

## Reporting a vulnerability

_Placeholder — to be completed with the official channel._

If you believe you have found a security vulnerability in PB Platform, please
report it privately to the PB Solutions security contact rather than opening a
public issue. Provide steps to reproduce, affected versions/commits, and any
proof-of-concept. A disclosure policy and dedicated contact address will be
published here.

## Hardening checklist

Implemented in phase 1:

- [x] Argon2id password hashing, off-loaded to a threadpool
- [x] Short-lived access tokens + refresh tokens with type separation, `jti`, and
      issuer validation
- [x] Role-based access control enforced by dependency injection
- [x] Per-IP rate limiting (Redis-backed, fail-open) with proxy-header trust
      gating
- [x] Strict response security headers; HSTS in production
- [x] CORS allowlist; wildcard rejected in production
- [x] Boot-time production validation (secret strength, CORS, database)
- [x] TLS at the edge (min TLS 1.2), HTTP→HTTPS redirect, ACME in production
- [x] `/metrics` restricted to internal networks
- [x] Parameterised queries and Pydantic input validation
- [x] Structured, request-correlated logging (`docs/OPERATIONS.md`)

Roadmap (known items, not yet implemented):

- [ ] **Docker socket exposure mitigation.** Traefik mounts `docker.sock`
      read-only today; front it with a scoped **socket-proxy** to reduce the
      blast radius of the mounted socket.
- [ ] **Per-account login lockout / throttling.** Rate limiting is per-IP only;
      add per-account failed-login backoff to resist credential stuffing against
      a single account from distributed IPs.
- [ ] **Token revocation / session store keyed by `jti`.** Enables
      logout-everywhere and refresh-token reuse detection; the `jti` claim is
      already present so this lands without a token-format change (ADR-0003).
