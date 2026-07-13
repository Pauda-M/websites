"""Liveness route for the workspace integration (no dependencies, no DB)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["workspace"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok", "integration": "workspace"}
