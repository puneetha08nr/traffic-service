from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.response import TrafficResponse
from app.scheduler import _do_poll, get_scheduler

router = APIRouter(prefix="/scheduler")


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    running: bool
    interval_minutes: int | None
    next_run_time: datetime | None
    job_id: str | None


@router.get("/status", response_model=SchedulerStatusResponse)
async def scheduler_status(request: Request) -> SchedulerStatusResponse:
    settings = request.app.state  # settings stored indirectly; read from config
    from app.config import get_settings

    cfg = get_settings()
    scheduler = get_scheduler()

    if scheduler is None or not scheduler.running:
        return SchedulerStatusResponse(
            enabled=cfg.scheduler_enabled,
            running=False,
            interval_minutes=cfg.scheduler_interval_minutes,
            next_run_time=None,
            job_id=None,
        )

    job = scheduler.get_job("mg_road_poll")
    return SchedulerStatusResponse(
        enabled=cfg.scheduler_enabled,
        running=True,
        interval_minutes=cfg.scheduler_interval_minutes,
        next_run_time=job.next_run_time if job else None,
        job_id=job.id if job else None,
    )


@router.post("/trigger", response_model=TrafficResponse)
async def trigger_poll(request: Request) -> TrafficResponse:
    """Immediately runs one MG Road poll and returns the traffic response."""
    return await _do_poll(request.app)


@router.post("/pause", response_model=dict[str, Any])
async def pause_scheduler() -> dict[str, Any]:
    scheduler = get_scheduler()
    if scheduler is None or not scheduler.running:
        raise HTTPException(status_code=409, detail="Scheduler is not running.")
    job = scheduler.get_job("mg_road_poll")
    if job is None:
        raise HTTPException(status_code=404, detail="Job mg_road_poll not found.")
    job.pause()
    return {"status": "paused", "job_id": "mg_road_poll"}


@router.post("/resume", response_model=dict[str, Any])
async def resume_scheduler() -> dict[str, Any]:
    scheduler = get_scheduler()
    if scheduler is None or not scheduler.running:
        raise HTTPException(status_code=409, detail="Scheduler is not running.")
    job = scheduler.get_job("mg_road_poll")
    if job is None:
        raise HTTPException(status_code=404, detail="Job mg_road_poll not found.")
    job.resume()
    return {"status": "resumed", "job_id": "mg_road_poll"}
