"""Platform introspection endpoints.

Exposes the module manifest so internal admin/monitoring surfaces (and humans
reading the OpenAPI spec) can see which product modules exist, which are
reserved for the future, and the compliance controls outreach modules require.
"""

from __future__ import annotations

from fastapi import APIRouter

from pb_api.platform.modules import ModuleStatus, all_modules
from pb_api.schemas.platform import ModuleManifest, ModuleRead

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/modules", response_model=ModuleManifest, summary="Platform module manifest")
async def list_modules() -> ModuleManifest:
    modules = all_modules()
    reads = [
        ModuleRead(
            slug=module.slug,
            name=module.name,
            category=module.category,
            status=module.status,
            api_namespace=module.api_namespace,
            description=module.description,
            compliance_controls=list(module.compliance_controls),
        )
        for module in modules
    ]
    return ModuleManifest(
        total=len(reads),
        available=sum(1 for module in modules if module.status is ModuleStatus.AVAILABLE),
        planned=sum(1 for module in modules if module.status is ModuleStatus.PLANNED),
        modules=reads,
    )
