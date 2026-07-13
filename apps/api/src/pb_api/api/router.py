from __future__ import annotations

from fastapi import APIRouter

from pb_api.agents.program_manager.api import program_manager_router
from pb_api.api.routes import auth, health, platform, users
from pb_api.cognitive.api import cognitive_router
from pb_api.integrations.workspace.api import workspace_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(platform.router)
api_router.include_router(cognitive_router)
api_router.include_router(program_manager_router)
api_router.include_router(workspace_router)
