from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.core.exceptions import QuotaExceededError


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _first_day_next_month(dt: datetime) -> datetime:
    year = dt.year + (1 if dt.month == 12 else 0)
    month = 1 if dt.month == 12 else dt.month + 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class QuotaUsage:
    used: int
    cap: int
    remaining: int
    reset_date: datetime


class CostGuard:
    def __init__(self, redis: Redis, cap: int) -> None:
        self._redis = redis
        self._cap = cap

    def _redis_key(self, now: datetime) -> str:
        return f"traffic:api_calls:{_month_key(now)}"

    async def check_or_raise(self) -> int:
        now = datetime.now(timezone.utc)
        key = self._redis_key(now)
        raw = await self._redis.get(key)
        used = int(raw) if raw else 0
        if used >= self._cap:
            raise QuotaExceededError(
                f"Monthly Google Routes quota cap reached ({used}/{self._cap}).",
                used=used,
                cap=self._cap,
            )
        return used

    async def increment(self) -> int:
        now = datetime.now(timezone.utc)
        key = self._redis_key(now)
        used = await self._redis.incr(key)
        # Keep key around slightly longer than a month boundary (optional safety)
        ttl_seconds = int((_first_day_next_month(now) - now).total_seconds()) + 86400
        await self._redis.expire(key, ttl_seconds)
        return int(used)

    async def current_usage(self) -> QuotaUsage:
        now = datetime.now(timezone.utc)
        key = self._redis_key(now)
        raw = await self._redis.get(key)
        used = int(raw) if raw else 0
        remaining = max(0, self._cap - used)
        return QuotaUsage(
            used=used,
            cap=self._cap,
            remaining=remaining,
            reset_date=_first_day_next_month(now),
        )

