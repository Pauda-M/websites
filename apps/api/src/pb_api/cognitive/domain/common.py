"""Shared domain primitives for the Cognitive Core."""

from __future__ import annotations

import enum
import hashlib
import math
import re
import uuid
from datetime import UTC, datetime

DEFAULT_EMBEDDING_DIM = 64


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> datetime:
    """Coerce a datetime to UTC-aware.

    Datetimes round-tripped through SQLite come back naive; treat them as UTC so
    comparisons and arithmetic against ``utcnow()`` are always valid.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MemoryType(enum.StrEnum):
    """The six canonical memory types (Genesis glossary §5)."""

    WORKING = "working"
    CONVERSATION = "conversation"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    LONG_TERM = "long_term"


class AuthorityLevel(enum.IntEnum):
    """Governed-autonomy levels A0-A5 (Genesis glossary §8).

    Integer-valued so ``min()`` composes an effective authority and comparisons
    are natural. Names mirror the specification exactly.
    """

    OBSERVE = 0
    SUGGEST = 1
    ACT_WITH_APPROVAL = 2
    ACT_BOUNDED = 3
    ACT_BROAD = 4
    GOVERN = 5


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 on mismatch/empty.

    Deterministic and dependency-free — the default similarity used until a
    ``VectorStore`` adapter (pgvector/Qdrant) is wired in.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def hash_embedding(text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """Deterministic signed feature-hashing embedding, L2-normalised.

    A real, dependency-free embedding technique (the hashing trick) used as the
    default ``Embeddings`` adapter so similarity, dedup, and ranking work
    end-to-end before a learned embedding model (bge/pgvector) is wired in
    (`docs/genesis/004_Company_Brain.md`). Same text always yields the same
    vector.
    """
    vec = [0.0] * dim
    for token in (part for part in re.split(r"\W+", text.lower()) if part):
        digest = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
        index = digest % dim
        sign = 1.0 if (digest >> 8) % 2 == 0 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(value * value for value in vec))
    if norm == 0.0:
        return vec
    return [value / norm for value in vec]


def estimate_tokens(text: str, chars_per_token: float) -> int:
    """Deterministic token estimate (no tokenizer dependency).

    Errs on the side of over-counting so token budgets are respected.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / chars_per_token))
