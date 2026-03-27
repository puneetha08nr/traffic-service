from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.request import LatLng, TrafficQueryRequest
from app.services.traffic_service import TrafficService


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    async def get(self, k: str):
        return self.kv.get(k)

    async def set(self, k: str, v: str, ex: int):
        self.kv[k] = v

    async def incr(self, k: str):
        self.kv[k] = str(int(self.kv.get(k, "0")) + 1)
        return int(self.kv[k])

    async def expire(self, k: str, ttl: int):
        return None


class FakeDB:
    def __init__(self) -> None:
        self.inserted = 0

    def add(self, _):
        self.inserted += 1

    async def commit(self):
        return None

    async def execute(self, *_args, **_kwargs):
        raise NotImplementedError


class FakeHttpx:
    async def post(self, *_args, **_kwargs):
        class R:
            status_code = 200

            def json(self):
                return {
                    "routes": [
                        {
                            "duration": "400s",
                            "staticDuration": "100s",
                            "travelAdvisory": {"trafficOnRoute": "TRAFFIC"},
                        }
                    ]
                }

            text = "ok"

        return R()

    async def head(self, *_args, **_kwargs):
        class R:
            status_code = 200

        return R()


class Settings:
    google_routes_api_key = "k"
    cache_ttl_seconds = 300
    google_routes_monthly_quota_cap = 100


@pytest.mark.anyio
async def test_query_cache_miss_goes_to_google_and_persists():
    redis = FakeRedis()
    db = FakeDB()
    settings = Settings()
    settings._httpx_client = FakeHttpx()

    svc = TrafficService.from_dependencies(redis=redis, db=db, settings=settings)  # type: ignore[arg-type]
    req = TrafficQueryRequest(
        origin=LatLng(latitude=1.0, longitude=2.0),
        destination=LatLng(latitude=3.0, longitude=4.0),
        label="x",
    )
    resp = await svc.query(req)
    assert resp.cache_hit is False
    assert resp.delay_seconds == 300
    assert resp.congestion_level == "SLOW"

