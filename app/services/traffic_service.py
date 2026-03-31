from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache, cache_key
from app.core.cost_guard import CostGuard
from app.core.metrics import (
    google_routes_api_calls_total,
    traffic_api_latency_seconds,
    traffic_api_requests_total,
    quota_usage_ratio,
)
from app.core.exceptions import InvalidCoordinatesError
from app.core.google_routes import GoogleRoutesClient
from app.db.repository import TrafficRepository
from app.models.request import TrafficQueryRequest
from app.models.response import TrafficRecordResponse, TrafficResponse
from app.utils.logger import get_logger, log_extra


logger = get_logger(__name__)


def _validate_lat_lng(lat: float, lng: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise InvalidCoordinatesError(f"Invalid latitude {lat}. Must be between -90 and 90.")
    if not (-180.0 <= lng <= 180.0):
        raise InvalidCoordinatesError(f"Invalid longitude {lng}. Must be between -180 and 180.")


class TrafficService:
    def __init__(
        self,
        *,
        redis: Redis | None,
        db: AsyncSession,
        httpx_client: httpx.AsyncClient,
        google_api_key: str,
        cache_ttl_seconds: int,
        quota_cap: int,
    ) -> None:
        self._redis = redis
        self._db = db
        self._httpx = httpx_client
        self._google = GoogleRoutesClient(httpx_client=httpx_client, api_key=google_api_key)
        self._cache = RedisCache(redis, ttl_seconds=cache_ttl_seconds) if redis else None
        self._guard = CostGuard(redis=redis, cap=quota_cap) if redis else None
        self._repo = TrafficRepository(db)

    @classmethod
    def from_dependencies(cls, *, redis: Redis | None, db: AsyncSession, settings: Any) -> "TrafficService":
        # settings is app.config.Settings
        httpx_client = settings.__dict__.get("_httpx_client")
        if httpx_client is None:
            # When called via FastAPI, httpx comes from app.state; in this scaffold we keep
            # it simple and create a new client if not injected (tests inject it).
            httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
            )
        return cls(
            redis=redis,
            db=db,
            httpx_client=httpx_client,
            google_api_key=settings.google_routes_api_key,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            quota_cap=settings.google_routes_monthly_quota_cap,
        )

    async def query(self, req: TrafficQueryRequest) -> TrafficResponse:
        start = time.perf_counter()
        _validate_lat_lng(req.origin.latitude, req.origin.longitude)
        _validate_lat_lng(req.destination.latitude, req.destination.longitude)

        key = cache_key(
            req.origin.latitude,
            req.origin.longitude,
            req.destination.latitude,
            req.destination.longitude,
        )

        if self._cache:
            cached = await self._cache.get(key)
            if cached.hit and cached.value:
                cached_value = dict(cached.value)
                cached_value["cache_hit"] = True
                traffic_api_requests_total.labels(
                    cache_hit="true",
                    congestion_level=str(cached_value.get("congestion_level") or "UNKNOWN"),
                ).inc()
                return TrafficResponse.model_validate(cached_value)

        used_before = 0
        if self._guard:
            used_before = await self._guard.check_or_raise()
            quota_usage_ratio.set(min(1.0, used_before / max(1, self._guard._cap)))  # noqa: SLF001

        google_routes_api_calls_total.inc()
        result = await self._google.compute_route(
            req.origin.latitude,
            req.origin.longitude,
            req.destination.latitude,
            req.destination.longitude,
        )

        if self._guard:
            used_after = await self._guard.increment()
            quota_usage_ratio.set(min(1.0, used_after / max(1, self._guard._cap)))  # noqa: SLF001
            logger.info(
                "quota_increment",
                extra=log_extra(used=used_after, cap=self._guard._cap, remaining=max(0, self._guard._cap - used_after)),  # noqa: SLF001
            )

        response = TrafficResponse(
            origin=req.origin,
            destination=req.destination,
            duration_seconds=result.duration_seconds,
            static_duration_seconds=result.static_duration_seconds,
            delay_seconds=result.delay_seconds,
            congestion_level=result.congestion_level,
            overall_condition=result.overall_condition,
            cache_hit=False,
            queried_at=result.queried_at,
            label=req.label,
        )

        await self._repo.insert_record(
            queried_at=response.queried_at,
            origin_lat=req.origin.latitude,
            origin_lng=req.origin.longitude,
            dest_lat=req.destination.latitude,
            dest_lng=req.destination.longitude,
            label=req.label,
            duration_seconds=response.duration_seconds,
            static_duration_seconds=response.static_duration_seconds,
            delay_seconds=response.delay_seconds,
            congestion_level=response.congestion_level,
            overall_condition=response.overall_condition,
            cache_hit=response.cache_hit,
            raw_response=result.raw_response,
        )

        if self._cache:
            await self._cache.set(key, response.model_dump(mode="json"))

        duration = time.perf_counter() - start
        traffic_api_latency_seconds.observe(duration)
        traffic_api_requests_total.labels(cache_hit="false", congestion_level=response.congestion_level).inc()

        logger.info(
            "traffic_query_complete",
            extra=log_extra(
                duration_ms=int(duration * 1000),
                cache_hit=False,
                congestion_level=response.congestion_level,
            ),
        )
        return response

    async def history(
        self,
        *,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        from_dt: datetime,
        to_dt: datetime,
        limit: int,
    ) -> list[TrafficRecordResponse]:
        _validate_lat_lng(origin_lat, origin_lng)
        _validate_lat_lng(dest_lat, dest_lng)
        rows = await self._repo.history(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            from_dt=from_dt,
            to_dt=to_dt,
            limit=limit,
        )
        return [
            TrafficRecordResponse(
                queried_at=r.queried_at,
                origin_lat=r.origin_lat,
                origin_lng=r.origin_lng,
                dest_lat=r.dest_lat,
                dest_lng=r.dest_lng,
                label=r.label,
                duration_seconds=r.duration_seconds,
                static_duration_seconds=r.static_duration_seconds,
                delay_seconds=r.delay_seconds,
                congestion_level=r.congestion_level,
                overall_condition=r.overall_condition,
                cache_hit=r.cache_hit,
            )
            for r in rows
        ]

