"""Memory ranking — deterministic heuristic implementation.

Implements the ``MemoryRanker`` interface (`docs/genesis/008_Memory_Engine.md`).
This is intentionally NOT machine learning: it is a transparent, deterministic
scoring function that a future ``MemoryRankNet`` replaces behind the same
interface (`docs/genesis/011_ML_Platform.md`). Every score comes with a
human-readable reason so ranking decisions are explainable.
"""

from __future__ import annotations

from pb_api.cognitive.config import CognitiveSettings, get_cognitive_settings
from pb_api.cognitive.domain.common import cosine_similarity, ensure_aware, utcnow
from pb_api.cognitive.domain.memory import MemoryItem
from pb_api.cognitive.domain.ranking import (
    RankedMemory,
    RankingContext,
    RankingResult,
)

# Weights sum to 1.0; tuned so similarity and importance dominate while recency
# and strength break ties. A learned ranker will subsume these.
_W_SIMILARITY = 0.4
_W_IMPORTANCE = 0.25
_W_STRENGTH = 0.15
_W_RECENCY = 0.1
_W_CONTEXT = 0.1


class HeuristicMemoryRanker:
    """Deterministic ranker combining similarity, importance, strength,
    recency, and contextual match."""

    name = "heuristic-v1"

    def __init__(self, settings: CognitiveSettings | None = None) -> None:
        self._settings = settings or get_cognitive_settings()

    def _recency_score(self, item: MemoryItem) -> float:
        age_seconds = max(0.0, (utcnow() - ensure_aware(item.last_accessed_at)).total_seconds())
        half_life = self._settings.recency_half_life_seconds
        # Exponential decay: 1.0 now, 0.5 at one half-life.
        return 0.5 ** (age_seconds / half_life) if half_life > 0 else 0.0

    def _context_score(self, item: MemoryItem, context: RankingContext) -> float:
        related = set(item.related_entity_ids)
        wanted = {
            context.customer_id,
            context.project_id,
            context.conversation_id,
        }
        wanted.discard(None)
        if not wanted:
            return 0.0
        hits = len(related & wanted)
        return min(1.0, hits / len(wanted))

    def _score(self, item: MemoryItem, context: RankingContext) -> tuple[float, str]:
        if context.query_embedding and item.embedding:
            similarity = max(0.0, cosine_similarity(context.query_embedding, item.embedding))
        else:
            similarity = 0.0
        recency = self._recency_score(item)
        ctx = self._context_score(item, context)
        score = (
            _W_SIMILARITY * similarity
            + _W_IMPORTANCE * item.importance
            + _W_STRENGTH * item.strength
            + _W_RECENCY * recency
            + _W_CONTEXT * ctx
        )
        reason = (
            f"sim={similarity:.2f} imp={item.importance:.2f} "
            f"str={item.strength:.2f} rec={recency:.2f} ctx={ctx:.2f}"
        )
        return round(score, 6), reason

    def rank(self, memories: list[MemoryItem], context: RankingContext) -> RankingResult:
        scored = [
            RankedMemory(memory=item, score=(pair := self._score(item, context))[0], reason=pair[1])
            for item in memories
        ]
        scored.sort(key=lambda ranked: ranked.score, reverse=True)
        return RankingResult(ranker=self.name, ranked=scored)
