"""InitData replay protection."""

from __future__ import annotations

from typing import Protocol

from kelbet.domain.exceptions import ReplayInitDataError


class ReplayStore(Protocol):
    async def claim(self, *, key: str, ttl_seconds: int) -> bool:
        """Return True if key was newly claimed; False if already present."""


class MemoryReplayStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def claim(self, *, key: str, ttl_seconds: int) -> bool:
        _ = ttl_seconds
        if key in self._keys:
            return False
        self._keys.add(key)
        return True

    def clear(self) -> None:
        self._keys.clear()


class RedisReplayStore:
    def __init__(self, redis: object) -> None:
        # duck-typed redis.asyncio.Redis to keep mypy free of redis stubs quirks
        self._redis = redis

    async def claim(self, *, key: str, ttl_seconds: int) -> bool:
        # SET key 1 NX EX ttl → True if set
        result = await self._redis.set(key, "1", nx=True, ex=ttl_seconds)  # type: ignore[attr-defined]
        return bool(result)


async def assert_not_replayed(
    store: ReplayStore,
    *,
    init_data_hash: str,
    ttl_seconds: int,
) -> None:
    claimed = await store.claim(key=f"tg_init:{init_data_hash}", ttl_seconds=ttl_seconds)
    if not claimed:
        raise ReplayInitDataError("initData replay detected")
