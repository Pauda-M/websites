"""Program Manager observability metrics.

Business-level Prometheus metrics for the Program Manager, registered on the
*application's* CollectorRegistry (the same one that backs ``/metrics``) so they
are per-app and never collide across the many app instances a test suite builds.
The metrics complement — they do not replace — the domain event log, which
remains the authoritative audit trail.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram


class ProgramManagerMetrics:
    """Counters and a histogram describing Program Manager lifecycle activity."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.runs_total = Counter(
            "pm_runs_total",
            "Program Manager lifecycle runs by goal and outcome",
            labelnames=("goal", "outcome"),
            registry=registry,
        )
        self.approvals_requested_total = Counter(
            "pm_approvals_requested_total",
            "Actions that paused a run awaiting human approval",
            registry=registry,
        )
        self.run_duration_seconds = Histogram(
            "pm_run_duration_seconds",
            "Wall-clock duration of a Program Manager lifecycle run",
            registry=registry,
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
