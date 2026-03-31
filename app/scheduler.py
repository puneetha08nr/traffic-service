from __future__ import annotations

from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.request import LatLng, TrafficQueryRequest
from app.models.response import TrafficResponse
from app.services.traffic_service import TrafficService
from app.utils.logger import get_logger, log_extra

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

MG_ROAD_REQUEST = TrafficQueryRequest(
    origin=LatLng(latitude=12.9752, longitude=77.6094),
    destination=LatLng(latitude=12.9719, longitude=77.6176),
    label="mg_road_metro_to_trinity",
)

_scheduler: AsyncIOScheduler | None = None


async def _do_poll(app: FastAPI) -> TrafficResponse:
    """Core poll logic — instantiates TrafficService from app state and queries MG Road."""
    from app.config import get_settings

    settings = get_settings()
    async with app.state.db_sessionmaker() as db:
        svc = TrafficService(
            redis=app.state.redis,
            db=db,
            httpx_client=app.state.httpx,
            google_api_key=settings.google_routes_api_key,
            cache_ttl_seconds=settings.cache_ttl_seconds,
            quota_cap=settings.google_routes_monthly_quota_cap,
        )
        return await svc.query(MG_ROAD_REQUEST)


async def poll_mg_road(app: FastAPI) -> None:
    """Scheduled job: poll MG Road traffic and persist to DB. Swallows all exceptions."""
    try:
        result = await _do_poll(app)
        logger.info(
            "scheduler_poll_complete",
            extra=log_extra(
                queried_at=result.queried_at.isoformat(),
                congestion_level=result.congestion_level,
                delay_seconds=result.delay_seconds,
                cache_hit=result.cache_hit,
            ),
        )
    except Exception as exc:
        logger.error(
            "scheduler_poll_error",
            extra=log_extra(error=str(exc)),
            exc_info=True,
        )


def start_scheduler(app: FastAPI, interval_minutes: int) -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        poll_mg_road,
        trigger="interval",
        minutes=interval_minutes,
        args=[app],
        id="mg_road_poll",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "scheduler_started",
        extra=log_extra(interval_minutes=interval_minutes),
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
