"""Redis client factory.

Redis is optional at boot: when ``redis_url`` is unset the API runs with
in-process fallbacks (rate limiting) and readiness skips the Redis check.
This keeps single-node deploys and the test suite honest without stubbing.
"""

from __future__ import annotations

from redis.asyncio import Redis

from pb_api.core.config import Settings


def create_redis(settings: Settings) -> Redis | None:
    if not settings.redis_url:
        return None
    return Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
