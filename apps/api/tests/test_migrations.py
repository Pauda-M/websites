"""The Alembic migration chain must build a working schema from scratch."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, str]:
    db_path = tmp_path / "migration-test.db"
    url = f"sqlite:///{db_path}"
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    # env.py honours -x db_url=... ; hand it the async sqlite URL it migrates.
    config.cmd_opts = Namespace(x=[f"db_url={url.replace('sqlite://', 'sqlite+aiosqlite://')}"])
    return config, url


def test_upgrade_head_builds_schema(alembic_config: tuple[Config, str]) -> None:
    config, url = alembic_config

    command.upgrade(config, "head")

    engine = create_engine(url)
    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    columns = {col["name"] for col in inspector.get_columns("users")}
    assert {
        "id",
        "email",
        "hashed_password",
        "full_name",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    } <= columns
    indexes = inspector.get_indexes("users")
    assert any(idx["unique"] and idx["column_names"] == ["email"] for idx in indexes)
    engine.dispose()


def test_downgrade_base_removes_schema(alembic_config: tuple[Config, str]) -> None:
    config, url = alembic_config

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    inspector = inspect(engine)
    assert "users" not in inspector.get_table_names()
    engine.dispose()
