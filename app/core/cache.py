from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from redis.asyncio import Redis


def _round4(x: float) -> float:
    return round(float(x), 4)


def cache_key(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    raw = f"{_round4(origin_lat)},{_round4(origin_lng)},{_round4(dest_lat)},{_round4(dest_lng)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"traffic:route:{digest}"


@dataclass(frozen=True)
class CacheResult:
    value: dict | None
    hit: bool


class RedisCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> CacheResult:
        data = await self._redis.get(key)
        if not data:
            return CacheResult(value=None, hit=False)
        return CacheResult(value=json.loads(data), hit=True)

    async def set(self, key: str, value: dict) -> None:
        await self._redis.set(key, json.dumps(value), ex=self._ttl)

