"""Document service — SharePoint/OneDrive access and knowledge ingestion.

Reads documents through the ``StorageProvider`` port, chunks their text, and
ingests each chunk into the unified knowledge index (reusing the Cognitive Core's
portable embedding). Ingested documents become ``DocumentIndexed`` events. Binary
formats whose text cannot be extracted are indexed by their metadata rather than
skipped, so nothing is silently lost.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.domain.files import DriveItem, SharePointSite
from pb_api.integrations.workspace.ports.providers import StorageProvider


def _chunks(text: str, size: int) -> builtins.list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _decode(content: bytes) -> str:
    """Best-effort text extraction; returns '' for undecodable binary formats."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return ""


class DocumentService:
    def __init__(
        self,
        *,
        provider: StorageProvider,
        search: SearchService,
        projector: WorkspaceEventProjector,
        settings: WorkspaceSettings,
    ) -> None:
        self._provider = provider
        self._search = search
        self._projector = projector
        self._settings = settings

    async def list_sites(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> builtins.list[SharePointSite]:
        return await self._provider.list_sites(tenant_id, connection_id)

    async def list_items(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, drive_id: str
    ) -> builtins.list[DriveItem]:
        page = await self._provider.list_items(
            tenant_id, connection_id, drive_id=drive_id, page_size=self._settings.sync_page_size
        )
        return list(page.items)

    async def ingest_document(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, item: DriveItem
    ) -> int:
        """Ingest one document into the knowledge index; returns chunks indexed."""
        content = await self._provider.download(
            tenant_id, connection_id, drive_id=item.drive_id, item_provider_id=item.provider_id
        )
        text = _decode(content)
        parts = _chunks(text, self._settings.document_chunk_chars) or [item.name]
        for chunk_index, chunk in enumerate(parts):
            await self._search.index_text(
                tenant_id,
                kind="document",
                source_provider_id=f"{item.provider_id}#chunk{chunk_index}",
                title=item.name,
                body=chunk,
                web_url=item.web_url,
                connection_id=connection_id,
                ref={"drive_id": item.drive_id, "chunk_index": chunk_index},
            )
        await self._projector.project(
            tenant_id,
            event_type=WorkspaceEventType.DOCUMENT_INDEXED,
            summary=f"Indexed document: {item.name}",
            payload={"name": item.name, "chunks": len(parts)},
            importance=0.4,
        )
        return len(parts)

    async def ingest_drive(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, *, drive_id: str
    ) -> int:
        """Ingest every file in a drive; returns the number of documents ingested."""
        cursor: str | None = None
        ingested = 0
        while True:
            page = await self._provider.list_items(
                tenant_id,
                connection_id,
                drive_id=drive_id,
                cursor=cursor,
                page_size=self._settings.sync_page_size,
            )
            for item in page.items:
                if not item.is_folder:
                    await self.ingest_document(tenant_id, connection_id, item=item)
                    ingested += 1
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return ingested
