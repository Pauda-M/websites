from __future__ import annotations

from pydantic import BaseModel

from pb_api.platform.modules import ModuleCategory, ModuleStatus


class ModuleRead(BaseModel):
    slug: str
    name: str
    category: ModuleCategory
    status: ModuleStatus
    api_namespace: str
    description: str
    compliance_controls: list[str]


class ModuleManifest(BaseModel):
    """The platform's module manifest: what exists, what's reserved, and the
    compliance controls outreach modules must ship with."""

    total: int
    available: int
    planned: int
    modules: list[ModuleRead]
