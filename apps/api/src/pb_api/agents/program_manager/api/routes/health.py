"""Health route for the Program Manager module."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["program-manager"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "employee": "program_manager"}
