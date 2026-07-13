"""Application factory.

``create_app`` builds a fully configured FastAPI instance from a Settings
object; module-level ``app`` is what uvicorn/Docker serve. Engine, session
factory, Redis client and metrics registry live on ``app.state`` so tests can
construct isolated apps with injected settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CollectorRegistry
from starlette.responses import JSONResponse, Response

import pb_api
from pb_api.api.router import api_router
from pb_api.core.config import Settings, get_settings
from pb_api.core.logging import configure_logging, get_logger
from pb_api.core.redis import create_redis
from pb_api.db.session import create_engine, create_session_factory
from pb_api.middleware.metrics import AppMetrics, MetricsMiddleware
from pb_api.middleware.rate_limit import (
    MemoryRateLimiter,
    RateLimiterBackend,
    RateLimitMiddleware,
    RedisRateLimiter,
)
from pb_api.middleware.request_context import RequestContextMiddleware
from pb_api.middleware.secure_headers import SecureHeadersMiddleware

API_V1_PREFIX = "/api/v1"

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = create_redis(settings)
        logger.info(
            "startup",
            environment=settings.environment,
            version=pb_api.__version__,
            redis_configured=app.state.redis is not None,
        )
        try:
            yield
        finally:
            if app.state.redis is not None:
                await app.state.redis.aclose()
            limiter_redis = getattr(app.state, "rate_limit_redis", None)
            if limiter_redis is not None:
                await limiter_redis.aclose()
            await engine.dispose()
            logger.info("shutdown")

    app = FastAPI(
        title="PB Platform API",
        version=pb_api.__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )
    app.state.settings = settings

    metrics = AppMetrics(CollectorRegistry())
    app.state.metrics = metrics

    rate_limit_backend: RateLimiterBackend
    redis_for_limiter = create_redis(settings)
    app.state.rate_limit_redis = redis_for_limiter
    if redis_for_limiter is not None:
        rate_limit_backend = RedisRateLimiter(redis_for_limiter)
    else:
        rate_limit_backend = MemoryRateLimiter()
    app.state.rate_limit_backend = rate_limit_backend

    # Starlette middleware run in reverse order of registration: the last
    # add_middleware call is the outermost layer. Effective request path:
    # RequestContext -> Metrics -> CORS -> SecureHeaders -> RateLimit -> app
    app.add_middleware(
        RateLimitMiddleware,
        backend=rate_limit_backend,
        limit_per_minute=settings.rate_limit_per_minute,
        trust_proxy_headers=settings.trust_proxy_headers,
        enabled=settings.rate_limit_enabled,
    )
    app.add_middleware(SecureHeadersMiddleware, enable_hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(MetricsMiddleware, metrics=metrics, mount_prefix=API_V1_PREFIX)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=API_V1_PREFIX)

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint(request: Request) -> Response:
            app_metrics: AppMetrics = request.app.state.metrics
            return app_metrics.render()

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    return app


app = create_app()
