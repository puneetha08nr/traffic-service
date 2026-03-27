from __future__ import annotations

from typing import AsyncGenerator

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings


async def init_resources(app) -> None:
    settings = get_settings()

    app.state.httpx = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
    )
    app.state.redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

    engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
    app.state.db_engine = engine
    app.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


async def close_resources(app) -> None:
    httpx_client: httpx.AsyncClient = app.state.httpx
    await httpx_client.aclose()

    redis: Redis = app.state.redis
    await redis.aclose()

    engine: AsyncEngine = app.state.db_engine
    await engine.dispose()


def settings_dep() -> Settings:
    return get_settings()


def redis_dep(request: Request) -> Redis:
    return request.app.state.redis


def httpx_dep(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx


async def db_session_dep(request: Request) -> AsyncGenerator[AsyncSession, None]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield session


SettingsDep = Depends(settings_dep)
RedisDep = Depends(redis_dep)
HttpxDep = Depends(httpx_dep)
DbSessionDep = Depends(db_session_dep)

