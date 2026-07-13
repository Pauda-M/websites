from __future__ import annotations

import fakeredis.aioredis

from pb_api.middleware.rate_limit import MemoryRateLimiter, RedisRateLimiter


async def test_memory_limiter_allows_within_limit() -> None:
    limiter = MemoryRateLimiter()
    for _ in range(5):
        result = await limiter.hit("client-a", limit=5, window_seconds=60)
        assert result.allowed


async def test_memory_limiter_blocks_over_limit() -> None:
    limiter = MemoryRateLimiter()
    for _ in range(5):
        await limiter.hit("client-b", limit=5, window_seconds=60)
    result = await limiter.hit("client-b", limit=5, window_seconds=60)
    assert not result.allowed
    assert result.retry_after >= 0


async def test_memory_limiter_isolates_keys() -> None:
    limiter = MemoryRateLimiter()
    for _ in range(5):
        await limiter.hit("client-c", limit=5, window_seconds=60)
    result = await limiter.hit("client-d", limit=5, window_seconds=60)
    assert result.allowed


async def test_redis_limiter_blocks_over_limit() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(redis)
    for _ in range(3):
        result = await limiter.hit("client-e", limit=3, window_seconds=60)
        assert result.allowed
    blocked = await limiter.hit("client-e", limit=3, window_seconds=60)
    assert not blocked.allowed
    assert blocked.retry_after >= 1
    await redis.aclose()


async def test_redis_limiter_sets_expiry() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(redis)
    await limiter.hit("client-f", limit=3, window_seconds=60)
    ttl = await redis.ttl("ratelimit:client-f")
    assert 0 < ttl <= 60
    await redis.aclose()
