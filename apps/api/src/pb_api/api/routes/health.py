"""Liveness and readiness probes.

Liveness never touches dependencies — it answers "is the process serving".
Readiness checks PostgreSQL and (when configured) Redis, returning 503 with
per-dependency detail so orchestrators stop routing traffic to a broken
instance and operators can see which dependency failed.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pb_api
from pb_api.core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)

CheckStatus = Literal["ok", "error", "skipped"]


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]


@router.get("/live", response_model=LivenessResponse)
async def liveness(request: Request) -> LivenessResponse:
    settings = request.app.state.settings
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        version=pb_api.__version__,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    checks: dict[str, CheckStatus] = {}

    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # readiness must report failures, not crash on them
        logger.warning("readiness_database_failed", error=str(exc))
        checks["database"] = "error"

    redis: Redis | None = request.app.state.redis
    if redis is None:
        checks["redis"] = "skipped"
    else:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.warning("readiness_redis_failed", error=str(exc))
            checks["redis"] = "error"

    degraded = any(value == "error" for value in checks.values())
    if degraded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="degraded" if degraded else "ok", checks=checks)
