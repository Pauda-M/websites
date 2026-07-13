"""Fixed-window rate limiting keyed by client IP.

Two backends share one interface: Redis (atomic INCR + EXPIRE, correct across
replicas) and in-process memory (single-node deploys, tests, and the fallback
when Redis is unreachable — the limiter fails open rather than taking the API
down with it). Health and metrics endpoints are exempt so orchestrators and
scrapers are never throttled.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pb_api.core.logging import get_logger

logger = get_logger(__name__)

EXEMPT_PREFIXES = ("/api/v1/health", "/metrics", "/docs", "/openapi.json", "/redoc")


class RateLimitResult:
    __slots__ = ("allowed", "retry_after")

    def __init__(self, allowed: bool, retry_after: int) -> None:
        self.allowed = allowed
        self.retry_after = retry_after


class RateLimiterBackend(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult: ...


class MemoryRateLimiter:
    """Per-process fixed window. Correct only for a single instance.

    Stale windows are swept periodically so the key set stays bounded rather
    than growing once per distinct client for the process lifetime. The clock
    is injectable so tests can pin it and avoid window-boundary flakiness.
    """

    _SWEEP_EVERY = 1024

    def __init__(self, *, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._windows: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()
        self._time_fn = time_fn
        self._hits_since_sweep = 0

    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(self._time_fn())
        window_start = now - (now % window_seconds)
        async with self._lock:
            start, count = self._windows.get(key, (window_start, 0))
            if start != window_start:
                start, count = window_start, 0
            count += 1
            self._windows[key] = (start, count)

            self._hits_since_sweep += 1
            if self._hits_since_sweep >= self._SWEEP_EVERY:
                self._hits_since_sweep = 0
                stale = [k for k, (s, _) in self._windows.items() if s < window_start]
                for k in stale:
                    del self._windows[k]
        if count > limit:
            return RateLimitResult(False, window_seconds - (now - window_start))
        return RateLimitResult(True, 0)


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        redis_key = f"ratelimit:{key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds, nx=True)
            pipe.ttl(redis_key)
            count, _, ttl = await pipe.execute()
        if int(count) > limit:
            return RateLimitResult(False, max(int(ttl), 1))
        return RateLimitResult(True, 0)


def client_identifier(request: Request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Leftmost entry is the originating client as recorded by our edge proxy.
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        backend: RateLimiterBackend,
        limit_per_minute: int,
        trust_proxy_headers: bool,
        enabled: bool,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._backend = backend
        self._limit = limit_per_minute
        self._trust_proxy_headers = trust_proxy_headers
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._enabled or request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        key = client_identifier(request, trust_proxy_headers=self._trust_proxy_headers)
        try:
            result = await self._backend.hit(key, self._limit, 60)
        except (RedisError, OSError) as exc:
            logger.warning("rate_limiter_unavailable", error=str(exc))
            return await call_next(request)

        if not result.allowed:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(result.retry_after)},
            )
        return await call_next(request)
