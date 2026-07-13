"""Cognitive Core configuration.

Sourced from ``PB_COG_*`` environment variables (12-factor), independent of the
API settings so token budgets and consolidation cadences can be tuned per
deployment without touching the core service settings.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class CognitiveSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PB_COG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Working memory -------------------------------------------------
    # Default token budget for an assembled Working Set / LLM context.
    default_token_budget: int = 8000
    # Characters-per-token heuristic used by the deterministic token estimator.
    chars_per_token: float = 4.0
    # Working-memory entries expire this many seconds after last touch.
    working_memory_ttl_seconds: int = 3600

    # --- Ranking / retrieval -------------------------------------------
    # Half-life (seconds) for recency decay in the heuristic ranker (7 days).
    recency_half_life_seconds: float = 7 * 24 * 3600
    # Default number of memories a recall returns.
    default_recall_limit: int = 20

    # --- Consolidation --------------------------------------------------
    # Importance threshold at/above which an episodic memory is promoted.
    promotion_importance_threshold: float = 0.7
    # Strength at/below which a memory is archived by consolidation.
    archive_strength_threshold: float = 0.05
    # Cosine similarity at/above which two memories are treated as duplicates.
    duplicate_similarity_threshold: float = 0.95


@lru_cache
def get_cognitive_settings() -> CognitiveSettings:
    return CognitiveSettings()
