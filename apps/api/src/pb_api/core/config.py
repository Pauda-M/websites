"""Application configuration.

All configuration is sourced from the environment (12-factor). Every service
setting uses the ``PB_API_`` prefix; a handful of cross-service values
(``PB_ENVIRONMENT``, ``DATABASE_URL``, ``REDIS_URL``) are also accepted so the
same variables can be shared across the compose stack.

Validation is strict: the service refuses to boot in production with
placeholder secrets, wildcard CORS, or a non-PostgreSQL database.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]

_PLACEHOLDER_SECRET_MARKERS = ("dev-only", "change-me", "changeme", "secret-key", "example")
_MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PB_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "pb-api"
    environment: Environment = Field(
        default="development",
        # Service-specific override wins; the shared cross-stack var is the fallback.
        validation_alias=AliasChoices("PB_API_ENVIRONMENT", "PB_ENVIRONMENT"),
    )
    debug: bool = False

    # --- Database / cache -------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://pb:pb@localhost:5432/pb_platform",
        validation_alias=AliasChoices("PB_API_DATABASE_URL", "DATABASE_URL"),
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PB_API_REDIS_URL", "REDIS_URL"),
    )

    # --- Security ----------------------------------------------------------
    secret_key: SecretStr = SecretStr("dev-only-secret-key-change-me-0000000000000000")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 14  # 14 days
    password_min_length: int = 10

    # --- HTTP behaviour ----------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000"]
    trust_proxy_headers: bool = False
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool | None = None  # None -> JSON everywhere except development/test
    metrics_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def render_logs_as_json(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.environment not in ("development", "test")

    @model_validator(mode="after")
    def _validate_production_hardening(self) -> Self:
        if self.environment != "production":
            return self

        secret = self.secret_key.get_secret_value()
        lowered = secret.lower()
        if len(secret) < _MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                "PB_API_SECRET_KEY must be at least "
                f"{_MIN_PRODUCTION_SECRET_LENGTH} characters in production"
            )
        if any(marker in lowered for marker in _PLACEHOLDER_SECRET_MARKERS):
            raise ValueError("PB_API_SECRET_KEY looks like a placeholder; set a real secret")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if not self.database_url.startswith("postgresql"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL")
        return self


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (tests build their own instances)."""
    return Settings()
