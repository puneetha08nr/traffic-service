from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.google_routes import GoogleRoutesClient
from app.dependencies import DbSessionDep, HttpxDep, RedisDep, settings_dep


router = APIRouter()


@router.get("/health")
async def health(
    redis: Redis = RedisDep,
    db: AsyncSession = DbSessionDep,
    httpx_client=HttpxDep,
    settings=Depends(settings_dep),
):
    # Redis
    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    # DB
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Google API reachability (best-effort: DNS + TLS handshake to host)
    google_ok = True
    try:
        client = GoogleRoutesClient(httpx_client=httpx_client, api_key=settings.google_routes_api_key)
        await client.ping()
    except Exception:
        google_ok = False

    status = "ok" if (redis_ok and db_ok and google_ok) else "degraded"
    return {
        "status": status,
        "redis": redis_ok,
        "db": db_ok,
        "google_routes_api": google_ok,
    }

