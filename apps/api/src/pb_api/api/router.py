from __future__ import annotations

from fastapi import APIRouter

from pb_api.api.routes import auth, health, platform, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(platform.router)
