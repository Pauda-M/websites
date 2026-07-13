"""Prometheus metrics.

Each app instance owns its own ``CollectorRegistry`` (created in
``create_app``) so test suites can build many apps without duplicate-metric
errors. Path labels use the matched route template — never the raw URL — to
keep label cardinality bounded.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


class AppMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self.requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            labelnames=("method", "path", "status"),
            registry=registry,
        )
        self.request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            labelnames=("method", "path"),
            registry=registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
        self.requests_in_flight = Gauge(
            "http_requests_in_flight",
            "In-flight HTTP requests",
            registry=registry,
        )

    def render(self) -> Response:
        return Response(generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)


def _route_template(request: Request, mount_prefix: str) -> str:
    """Return the matched route template, e.g. ``/api/v1/users/{user_id}``.

    Routers included with a prefix (FastAPI mounts them lazily) report paths
    relative to the mount, so the known prefix is re-attached when the raw
    request path lives under it.
    """
    route = request.scope.get("route")
    if not isinstance(route, Route):
        return "unmatched"
    template: str = route.path
    raw_path: str = request.scope.get("path", "")
    if mount_prefix and raw_path.startswith(mount_prefix) and not template.startswith(mount_prefix):
        template = mount_prefix + template
    return template


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, metrics: AppMetrics, mount_prefix: str = "") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._metrics = metrics
        self._mount_prefix = mount_prefix

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        self._metrics.requests_in_flight.inc()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            self._metrics.requests_in_flight.dec()
            path = _route_template(request, self._mount_prefix)
            method = request.method
            self._metrics.requests_total.labels(method=method, path=path, status=status).inc()
            self._metrics.request_duration.labels(method=method, path=path).observe(
                time.perf_counter() - start
            )
