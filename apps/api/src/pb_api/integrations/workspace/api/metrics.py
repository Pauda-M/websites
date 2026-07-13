"""Workspace observability metrics.

Business-level Prometheus metrics registered on the application's CollectorRegistry
(the same one backing ``/metrics``), so they are per-app and never collide across
the many app instances a test suite builds. They complement — never replace — the
immutable event log and the audit log.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class WorkspaceMetrics:
    """Counters, gauges, and histograms describing workspace activity."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.sync_runs_total = Counter(
            "ws_sync_runs_total",
            "Workspace synchronization runs by resource and outcome",
            labelnames=("resource", "outcome"),
            registry=registry,
        )
        self.sync_items_total = Counter(
            "ws_sync_items_total",
            "Items processed by synchronization, by resource",
            labelnames=("resource",),
            registry=registry,
        )
        self.sync_duration_seconds = Histogram(
            "ws_sync_duration_seconds",
            "Wall-clock duration of a synchronization run, by resource",
            labelnames=("resource",),
            registry=registry,
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )
        self.retries_total = Counter(
            "ws_sync_retries_total",
            "Synchronization attempts that were retried, by resource",
            labelnames=("resource",),
            registry=registry,
        )
        self.dead_letter_total = Counter(
            "ws_dead_letter_total",
            "Units of work sent to the dead-letter queue",
            registry=registry,
        )
        self.approvals_total = Counter(
            "ws_approvals_total",
            "Approval-engine decisions by decision type",
            labelnames=("decision",),
            registry=registry,
        )
        self.rate_limited_total = Counter(
            "ws_provider_rate_limited_total",
            "Provider requests that hit a rate limit (HTTP 429)",
            registry=registry,
        )
        self.webhook_subscriptions_active = Gauge(
            "ws_webhook_subscriptions_active",
            "Currently-active provider webhook subscriptions",
            registry=registry,
        )
        self.dead_letter_queue_size = Gauge(
            "ws_dead_letter_queue_size",
            "Current size of the dead-letter queue",
            registry=registry,
        )
        self.worker_runs_total = Counter(
            "ws_worker_runs_total",
            "Background worker ticks, by outcome",
            labelnames=("outcome",),
            registry=registry,
        )
