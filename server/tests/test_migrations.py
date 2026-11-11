"""Migrations Alembic : `upgrade head` sur une base vierge doit produire exactement `Base.metadata`.

Fonctionne sur SQLite (par défaut) et sur Postgres (`DR_TEST_DATABASE_URL`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.characters import DEFAULT_ZONE_ID
from app.db.base import Base
from app.db.models import Zone
from tests.conftest import create_test_engine

SERVER_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    # env.py réutilise cette connexion au lieu d'ouvrir la base de `Settings`.
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


def _reset_schema(connection: Connection) -> None:
    Base.metadata.drop_all(connection)
    connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def _upgrade(connection: Connection) -> None:
    command.upgrade(_alembic_config(connection), "head")


def _downgrade(connection: Connection) -> None:
    command.downgrade(_alembic_config(connection), "base")


def _diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, Base.metadata))


def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


@pytest.fixture
async def blank_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Moteur sur une base sans aucune table (nettoyée avant et après le test)."""
    engine = create_test_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(_reset_schema)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(_reset_schema)
        await engine.dispose()


async def test_upgrade_head_matches_models(blank_engine: AsyncEngine) -> None:
    async with blank_engine.begin() as conn:
        await conn.run_sync(_upgrade)
    async with blank_engine.connect() as conn:
        assert await conn.run_sync(_diff) == []
        zone = (await conn.execute(select(Zone.__table__).where(Zone.id == DEFAULT_ZONE_ID))).one()
    assert zone._mapping == {
        "id": DEFAULT_ZONE_ID,
        "name": "Valcendre",
        "map_file": "maps/valcendre.tmj",
        "max_players": 32,
        "is_pvp": False,
        "spawn_x": 64.0,
        "spawn_y": 64.0,
    }


async def test_downgrade_base_removes_tables(blank_engine: AsyncEngine) -> None:
    async with blank_engine.begin() as conn:
        await conn.run_sync(_upgrade)
        await conn.run_sync(_downgrade)
    async with blank_engine.connect() as conn:
        assert await conn.run_sync(_table_names) <= {"alembic_version"}
