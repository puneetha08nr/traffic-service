from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.core.cost_guard import CostGuard
from app.core.exceptions import QuotaExceededError


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.exp: dict[str, int] = {}

    async def get(self, key: str):
        v = self.store.get(key)
        return str(v) if v is not None else None

    async def incr(self, key: str):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int):
        self.exp[key] = ttl


@pytest.mark.anyio
async def test_cost_guard_enforces_cap():
    r = FakeRedis()
    guard = CostGuard(redis=r, cap=2)  # type: ignore[arg-type]

    await guard.check_or_raise()
    await guard.increment()
    await guard.check_or_raise()
    await guard.increment()

    with pytest.raises(QuotaExceededError):
        await guard.check_or_raise()


@pytest.mark.anyio
async def test_current_usage_shape():
    r = FakeRedis()
    guard = CostGuard(redis=r, cap=10)  # type: ignore[arg-type]
    usage = await guard.current_usage()
    assert usage.used == 0
    assert usage.cap == 10
    assert usage.remaining == 10
    assert usage.reset_date.tzinfo is not None

