"""Pagination and delta-synchronization value objects.

Provider-agnostic containers the ports return. ``Page`` models cursor pagination
(Graph's ``@odata.nextLink``); ``DeltaPage`` models incremental delta sync
(Graph's ``@odata.deltaLink``) where the token persisted after one sweep is
replayed on the next to fetch only changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """One page of results plus an opaque cursor to the next page (if any)."""

    items: Sequence[T]
    next_cursor: str | None = None

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None


@dataclass(frozen=True, slots=True)
class DeltaPage(Generic[T]):
    """One page of a delta sweep.

    ``next_cursor`` walks the pages of the current sweep; ``delta_token`` is
    present only on the final page and is what the caller persists to resume from
    changes next time. ``removed_ids`` carries tombstones the provider reported.
    """

    items: Sequence[T]
    next_cursor: str | None = None
    delta_token: str | None = None
    removed_ids: Sequence[str] = field(default_factory=tuple)

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None

    @property
    def is_final(self) -> bool:
        return self.next_cursor is None and self.delta_token is not None
