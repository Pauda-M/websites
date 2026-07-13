"""Working Memory service.

Isolated, short-lived, token-aware, task/conversation-scoped memory that expires
automatically, prioritises relevance, can merge multiple contexts, and is
versioned (Phase 7 spec). Backed by ``WorkingMemoryRepository``.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.domain.common import estimate_tokens, utcnow
from pb_api.cognitive.domain.memory import WorkingMemoryEntry, WorkingSet
from pb_api.cognitive.repositories.memory import WorkingMemoryRepository


class WorkingMemoryService:
    def __init__(
        self,
        repository: WorkingMemoryRepository,
        settings: CognitiveSettings | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings or get_cognitive_settings()

    async def remember(
        self,
        tenant_id: uuid.UUID,
        scope_key: str,
        content: str,
        *,
        relevance: float = 0.5,
        source: str = "observation",
        ttl_seconds: int | None = None,
    ) -> WorkingMemoryEntry:
        """Add a token-aware, auto-expiring, versioned working entry."""
        ttl = ttl_seconds if ttl_seconds is not None else self._settings.working_memory_ttl_seconds
        next_version = (await self._repo.max_version(tenant_id, scope_key)) + 1
        entry = WorkingMemoryEntry(
            tenant_id=tenant_id,
            scope_key=scope_key,
            content=content,
            token_estimate=estimate_tokens(content, self._settings.chars_per_token),
            relevance=relevance,
            version=next_version,
            source=source,
            expires_at=utcnow() + timedelta(seconds=ttl),
        )
        return await self._repo.add(entry)

    async def build_set(
        self, tenant_id: uuid.UUID, scope_key: str, *, token_budget: int | None = None
    ) -> WorkingSet:
        """Assemble a token-bounded WorkingSet, dropping least-relevant entries
        once the budget is exceeded."""
        budget = token_budget or self._settings.default_token_budget
        entries = await self._repo.list_active(tenant_id, scope_key)
        selected: list[WorkingMemoryEntry] = []
        total = 0
        truncated = False
        for entry in entries:  # already ordered by relevance desc
            if total + entry.token_estimate > budget:
                truncated = True
                continue
            selected.append(entry)
            total += entry.token_estimate
        return WorkingSet(
            scope_key=scope_key,
            entries=selected,
            total_tokens=total,
            token_budget=budget,
            truncated=truncated,
        )

    async def merge_scopes(
        self, tenant_id: uuid.UUID, source_scopes: list[str], target_scope: str
    ) -> int:
        """Merge multiple contexts into one target scope (versioned copies)."""
        merged = 0
        for scope in source_scopes:
            for entry in await self._repo.list_active(tenant_id, scope):
                await self.remember(
                    tenant_id,
                    target_scope,
                    entry.content,
                    relevance=entry.relevance,
                    source="merge",
                )
                merged += 1
        return merged

    async def expire(self, tenant_id: uuid.UUID) -> int:
        """Purge expired entries; returns the number removed."""
        return await self._repo.purge_expired(tenant_id)

    async def clear(self, tenant_id: uuid.UUID, scope_key: str) -> int:
        return await self._repo.clear_scope(tenant_id, scope_key)
