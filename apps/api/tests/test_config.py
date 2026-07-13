from __future__ import annotations

import pytest

from tests.conftest import build_test_settings


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        build_test_settings(
            environment="production",
            secret_key="dev-only-secret-key-change-me-0000000000000000",
        )


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="at least"):
        build_test_settings(environment="production", secret_key="tiny")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="Wildcard"):
        build_test_settings(
            environment="production",
            secret_key="a-genuinely-random-signing-string-0123456789abcdef",
            database_url="postgresql+asyncpg://pb:pb@db:5432/pb",
            cors_origins=["*"],
        )


def test_production_requires_postgres() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        build_test_settings(
            environment="production",
            secret_key="a-genuinely-random-signing-string-0123456789abcdef",
            database_url="sqlite+aiosqlite:///prod.db",
        )


def test_valid_production_settings_accepted() -> None:
    settings = build_test_settings(
        environment="production",
        secret_key="a-genuinely-random-signing-string-0123456789abcdef",
        database_url="postgresql+asyncpg://pb:pb@db:5432/pb",
        cors_origins=["https://pbsolutions.example"],
    )
    assert settings.is_production
    assert settings.render_logs_as_json


def test_development_defaults_are_permissive() -> None:
    settings = build_test_settings()
    assert not settings.is_production
    assert not settings.render_logs_as_json
