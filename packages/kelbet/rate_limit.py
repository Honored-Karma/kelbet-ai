"""Fixed-window rate limiter (memory for tests, Redis for production)."""

from __future__ import annotations

import time
from typing import Protocol


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Return True if allowed, False if rate limited."""


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, int]] = {}

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = int(time.time())
        bucket = now // max(1, window_seconds)
        compound = f"{key}:{bucket}"
        count, stored_bucket = self._windows.get(compound, (0, bucket))
        if stored_bucket != bucket:
            count = 0
        count += 1
        self._windows[compound] = (count, bucket)
        # prune old buckets opportunistically
        if len(self._windows) > 2048:
            stale = [k for k in self._windows if not k.endswith(f":{bucket}")]
            for item in stale[:1024]:
                self._windows.pop(item, None)
        return count <= limit


class RedisRateLimiter:
    def __init__(self, redis: object) -> None:
        self._redis = redis

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = int(time.time())
        bucket = now // max(1, window_seconds)
        redis_key = f"kelbet:rl:{key}:{bucket}"
        count = await self._redis.incr(redis_key)  # type: ignore[attr-defined]
        if count == 1:
            await self._redis.expire(redis_key, window_seconds + 1)  # type: ignore[attr-defined]
        return int(count) <= limit
