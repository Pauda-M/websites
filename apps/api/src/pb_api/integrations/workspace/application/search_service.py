"""Unified search — one semantic search across every workspace surface.

Mail, meetings, documents, contacts, tasks, knowledge, and events are all projected
into a single index (`ws_index_entry`). Search reuses the Cognitive Core's
deterministic, portable embedding (feature-hashed ``hash_embedding``) and cosine
similarity — the same representation the rest of Genesis uses, so it survives
vendor and model changes (manifesto: Memory). No external vector service is
required; pgvector is the production scale-up behind the same interface.
"""

from __future__ import annotations

import builtins
import uuid

from pb_api.cognitive.domain.common import cosine_similarity, hash_embedding
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.search import IndexEntry, SearchHit
from pb_api.integrations.workspace.infrastructure.repositories import IndexEntryRepository


class SearchService:
    def __init__(self, index: IndexEntryRepository, settings: WorkspaceSettings) -> None:
        self._index = index
        self._settings = settings

    def _embed(self, text: str) -> list[float]:
        return hash_embedding(text, dim=self._settings.embedding_dim)

    async def index_entry(self, entry: IndexEntry) -> IndexEntry:
        """Index (or re-index) an item, computing its embedding if absent."""
        if not entry.embedding:
            entry.embedding = self._embed(f"{entry.title}\n{entry.snippet}\n{entry.body}")
        return await self._index.upsert(entry)

    async def index_text(
        self,
        tenant_id: uuid.UUID,
        *,
        kind: str,
        source_provider_id: str,
        title: str,
        body: str,
        snippet: str = "",
        web_url: str | None = None,
        connection_id: uuid.UUID | None = None,
        ref: dict[str, object] | None = None,
    ) -> IndexEntry:
        entry = IndexEntry(
            tenant_id=tenant_id,
            kind=kind,
            source_provider_id=source_provider_id,
            connection_id=connection_id,
            title=title,
            snippet=snippet or body[:280],
            body=body,
            web_url=web_url,
            ref=ref or {},
        )
        return await self.index_entry(entry)

    async def search(
        self,
        tenant_id: uuid.UUID,
        *,
        query: str,
        kinds: builtins.list[str] | None = None,
        limit: int = 20,
    ) -> builtins.list[SearchHit]:
        """Semantic search: rank indexed entries by cosine similarity to the query."""
        query_vec = self._embed(query)
        entries = await self._index.fetch_all(tenant_id, kinds=kinds)
        scored = [
            SearchHit(entry=entry, score=cosine_similarity(query_vec, entry.embedding))
            for entry in entries
            if entry.embedding
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:limit]
