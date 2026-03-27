from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_guard import CostGuard
from app.dependencies import DbSessionDep, RedisDep, settings_dep
from app.models.request import TrafficQueryRequest
from app.models.response import QuotaUsageResponse, TrafficRecordResponse, TrafficResponse
from app.services.traffic_service import TrafficService


router = APIRouter(prefix="/traffic")


@router.post("/query", response_model=TrafficResponse)
async def query_traffic(
    body: TrafficQueryRequest,
    redis=RedisDep,
    db: AsyncSession = DbSessionDep,
    settings=Depends(settings_dep),
):
    svc = TrafficService.from_dependencies(redis=redis, db=db, settings=settings)
    return await svc.query(body)


@router.get("/history", response_model=list[TrafficRecordResponse])
async def traffic_history(
    origin_lat: float = Query(...),
    origin_lng: float = Query(...),
    dest_lat: float = Query(...),
    dest_lng: float = Query(...),
    from_dt: datetime = Query(...),
    to_dt: datetime = Query(...),
    limit: int = Query(100, ge=1, le=5000),
    db: AsyncSession = DbSessionDep,
    settings=Depends(settings_dep),
):
    svc = TrafficService.from_dependencies(redis=None, db=db, settings=settings)
    return await svc.history(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=limit,
    )


@router.get("/quota", response_model=QuotaUsageResponse)
async def quota(redis=RedisDep, settings=Depends(settings_dep)):
    guard = CostGuard(redis=redis, cap=settings.google_routes_monthly_quota_cap)
    return await guard.current_usage()

