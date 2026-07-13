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


async def test_memory_limiter_resets_on_new_window() -> None:
    clock = {"now": 100.0}
    limiter = MemoryRateLimiter(time_fn=lambda: clock["now"])
    for _ in range(3):
        assert (await limiter.hit("client-g", limit=3, window_seconds=60)).allowed
    assert not (await limiter.hit("client-g", limit=3, window_seconds=60)).allowed

    # Advance into the next fixed window: the counter resets.
    clock["now"] = 100.0 + 60
    assert (await limiter.hit("client-g", limit=3, window_seconds=60)).allowed


async def test_memory_limiter_evicts_stale_windows() -> None:
    clock = {"now": 0.0}
    limiter = MemoryRateLimiter(time_fn=lambda: clock["now"])
    # Populate distinct keys in the first window.
    for i in range(MemoryRateLimiter._SWEEP_EVERY - 1):
        await limiter.hit(f"old-{i}", limit=1000, window_seconds=60)
    assert len(limiter._windows) == MemoryRateLimiter._SWEEP_EVERY - 1

    # Move to a later window and trip the sweep threshold with a fresh key.
    clock["now"] = 120.0
    await limiter.hit("fresh", limit=1000, window_seconds=60)
    # Stale keys from the first window are gone; only the fresh one remains.
    assert limiter._windows == {"fresh": (120, 1)}


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
