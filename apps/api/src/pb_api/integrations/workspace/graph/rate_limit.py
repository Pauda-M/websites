"""A cooperative async token-bucket rate limiter.

Microsoft Graph enforces per-app throttling; this bucket paces outbound requests
to ``rate_limit_per_second`` so we stay well under the limit and only ever sleep
for exactly the deficit. Timing uses the event-loop clock
(``asyncio.get_event_loop().time()``) — never wall-clock — so it is immune to
system clock changes and testable with a fake loop.
"""

from __future__ import annotations

import asyncio


class AsyncRateLimiter:
    """Limits acquisitions to ``rate_per_second`` using a monotonic token bucket.

    A single :class:`asyncio.Lock` serializes token accounting; refill is computed
    from elapsed loop time. When the bucket is empty, :meth:`acquire` sleeps for the
    precise time needed for one token to accrue and no longer.
    """

    def __init__(self, rate_per_second: float, *, burst: float | None = None) -> None:
        self._rate = rate_per_second
        # The bucket holds at most one second of capacity by default, allowing a
        # small burst without ever exceeding the sustained rate.
        self._capacity = burst if burst is not None else max(1.0, rate_per_second)
        self._tokens = self._capacity
        self._updated_at: float | None = None
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return asyncio.get_event_loop().time()

    async def acquire(self) -> None:
        """Block until a token is available, then consume it."""
        if self._rate <= 0:
            return
        async with self._lock:
            now = self._now()
            if self._updated_at is None:
                self._updated_at = now
            elapsed = now - self._updated_at
            self._updated_at = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            if self._tokens < 1.0:
                delay = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(delay)
                # After sleeping for exactly the deficit, one token has accrued and
                # is immediately consumed.
                self._tokens = 0.0
                self._updated_at = self._now()
            else:
                self._tokens -= 1.0
