# ADR-0006: Observability

## Status

Accepted — 2026-07-13

## Context

Governance requires every service to expose a health endpoint, a readiness
endpoint, a metrics endpoint, and structured logs. Operators need to correlate a
single request across log lines, orchestrators need a machine-readable signal to
pull a broken instance out of rotation while keeping a slow-but-alive process in,
and metrics need bounded cardinality so a future Prometheus can scrape them
cheaply.

## Decision

**Structured logging (structlog).** `core/logging.py` configures one processor
chain shared by structlog and the stdlib loggers (uvicorn, SQLAlchemy, Alembic),
so every line in a container has the same shape. Output is **one JSON object per
line** everywhere except `development`/`test`, which use a human-readable console
renderer (`render_logs_as_json` derives this from `log_json`/`environment`).
`RequestContextMiddleware` assigns each request an ID (honouring an inbound
`X-Request-ID` from the edge), binds it into structlog contextvars so every line
emitted while handling the request carries it, echoes it back on the
`X-Request-ID` response header, and emits exactly one access log line
(`method`, `path`, `status`, `duration_ms`, `client`).

**Metrics (Prometheus).** `middleware/metrics.py` records `http_requests_total`
(labels `method`, `path`, `status`), `http_request_duration_seconds`
(labels `method`, `path`, explicit buckets), and an `http_requests_in_flight`
gauge. The `path` label is the **matched route template**
(e.g. `/api/v1/users/{user_id}`), never the raw URL, keeping label cardinality
bounded. Each app instance owns its own `CollectorRegistry` (created in
`create_app`) so tests build many apps without duplicate-metric errors. Metrics
are served at `GET /metrics` (registered only when `metrics_enabled`), outside
the `/api/v1` prefix and exempt from rate limiting.

**Health.** `api/routes/health.py` splits liveness from readiness:
`GET /api/v1/health/live` never touches dependencies (it answers "is the process
serving") while `GET /api/v1/health/ready` checks PostgreSQL (`SELECT 1`) and,
when configured, Redis (`PING`), returning **503 with per-dependency detail**
(`checks: {database: ok|error, redis: ok|error|skipped}`) when any dependency is
down. This lets an orchestrator stop routing to a degraded instance while
liveness stays green.

## Alternatives Considered

- **Standard-library `logging` only.** No extra dependency, but assembling
  consistent structured JSON, request-scoped context, and one unified pipeline
  across uvicorn/SQLAlchemy by hand is exactly what structlog provides. Rejected
  for the boilerplate and inconsistency.
- **OpenTelemetry-first (traces + metrics + logs via OTel SDK).** The richest
  long-term signal, but heavier to stand up and operate than phase 1 needs, and
  metrics/logs are the immediate requirement. Rejected as premature; the route
  template labelling and JSON logs are collector-ready and OTel can be layered
  on later.
- **A single combined `/health` endpoint.** Simpler, but conflates "restart me"
  (liveness) with "don't route to me" (readiness); orchestrators need the two
  signals separated. Rejected.

## Consequences

- Every request is traceable end to end by its request ID, across all structured
  log lines and back to the caller via the response header.
- Metrics have bounded cardinality by construction (route template, not URL), so
  a future scrape stays cheap even under many distinct paths.
- Readiness gives orchestrators a precise, per-dependency signal; a degraded
  dependency yields 503 with the failing check named, without crashing the
  process.
- Redis is optional: when unconfigured, readiness reports `redis: skipped`
  rather than failing (`core/redis.py` returns `None`).
- JSON-per-line logs are collector-ready; no application change is needed to ship
  them (point the Docker log driver at a collector).

## Future Considerations

- **OpenTelemetry traces** for cross-service request flows as more services
  land, noted as a growth path in `docs/ARCHITECTURE.md`.
- A **Prometheus + Grafana** (or hosted equivalent) deployment scraping
  `/metrics` over the internal network, with dashboards and alerts.
- Log-based alerting and retention once a collector is in place.
