from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TrafficRecord


class TrafficRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_record(
        self,
        *,
        queried_at: datetime,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        label: str | None,
        duration_seconds: int | None,
        static_duration_seconds: int | None,
        delay_seconds: int | None,
        congestion_level: str | None,
        overall_condition: str | None,
        cache_hit: bool,
        raw_response: dict[str, Any] | None,
    ) -> None:
        rec = TrafficRecord(
            queried_at=queried_at,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            label=label,
            duration_seconds=duration_seconds,
            static_duration_seconds=static_duration_seconds,
            delay_seconds=delay_seconds,
            congestion_level=congestion_level,
            overall_condition=overall_condition,
            cache_hit=cache_hit,
            raw_response=raw_response,
        )
        self._session.add(rec)
        await self._session.commit()

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
    ) -> list[TrafficRecord]:
        stmt = (
            select(TrafficRecord)
            .where(TrafficRecord.origin_lat == origin_lat)
            .where(TrafficRecord.origin_lng == origin_lng)
            .where(TrafficRecord.dest_lat == dest_lat)
            .where(TrafficRecord.dest_lng == dest_lng)
            .where(TrafficRecord.queried_at >= from_dt)
            .where(TrafficRecord.queried_at <= to_dt)
            .order_by(TrafficRecord.queried_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)

