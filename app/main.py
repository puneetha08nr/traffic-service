from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes.health import router as health_router
from app.api.routes.traffic import router as traffic_router
from app.config import get_settings
from app.core.exceptions import GoogleRoutesAPIError, InvalidCoordinatesError, QuotaExceededError
from app.dependencies import close_resources, init_resources
from app.utils.logger import configure_logging, get_logger, log_extra


logger = get_logger(__name__)
quota_usage_ratio = Gauge(
    "quota_usage_ratio", "used/cap ratio (0..1) updated per call"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_resources(app)
    try:
        yield
    finally:
        await close_resources(app)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Traffic Service",
        version="1.0.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    instrumentator = Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "http_request",
                extra=log_extra(
                    method=request.method,
                    path=request.url.path,
                    status_code=getattr(locals().get("response", None), "status_code", None),
                    duration_ms=duration_ms,
                ),
            )

    @app.exception_handler(InvalidCoordinatesError)
    async def invalid_coordinates_handler(_: Request, exc: InvalidCoordinatesError):
        return ORJSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded_handler(_: Request, exc: QuotaExceededError):
        quota_usage_ratio.set(min(1.0, exc.used / max(1, exc.cap)))
        return ORJSONResponse(
            status_code=429,
            content={"detail": str(exc), "used": exc.used, "cap": exc.cap},
        )

    @app.exception_handler(GoogleRoutesAPIError)
    async def google_error_handler(_: Request, exc: GoogleRoutesAPIError):
        return ORJSONResponse(status_code=502, content={"detail": str(exc)})

    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    app.include_router(traffic_router, prefix="/api/v1", tags=["traffic"])

    return app


app = create_app()

