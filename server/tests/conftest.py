"""Fixtures partagées par toute la suite de tests serveur.

Base de données : SQLite (aiosqlite) dans un fichier temporaire propre à chaque test, ou
Postgres si la variable d'environnement `DR_TEST_DATABASE_URL` est définie
(ex. `postgresql+asyncpg://refuge:refuge@localhost:5432/refuge_test`). Sur Postgres, le
schéma est supprimé puis recréé à chaque test : n'utilisez jamais une base de production.

Redis : `fakeredis.aioredis.FakeRedis(decode_responses=True)` (en mémoire, aucun serveur).

Chaîne de fixtures :

    database_url ─► engine ─┐
          └──────► settings ┼─► app ─► client ─► create_account / auth_headers / create_character
                     redis ─┘

Pour un test WebSocket via `starlette.testclient.TestClient` (qui exécute l'application
dans sa propre boucle d'événements), ne réutilisez pas `engine` dans l'application : demandez
la fixture `engine` (elle prépare le schéma), puis `create_app(settings, redis=...)` sans
`engine`, pour que le lifespan crée son propre moteur sur `settings.database_url`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.api.characters import DEFAULT_ZONE_ID
from app.config import Settings
from app.db import models  # noqa: F401  (enregistre les tables dans Base.metadata)
from app.db.base import Base
from app.db.models import Character, Zone
from app.db.session import create_sessionmaker
from app.main import create_app

TEST_DATABASE_URL_ENV = "DR_TEST_DATABASE_URL"
DEFAULT_PASSWORD = "mot-de-passe-solide"
# Mêmes valeurs que la migration initiale (migrations/versions/0001_initial.py).
DEFAULT_ZONE_SPAWN = (64.0, 64.0)


async def kill_character(engine: AsyncEngine, character_id: str) -> None:
    """Marque un personnage comme mort directement en base (la mort en jeu arrive en phase 2)."""
    async with engine.begin() as conn:
        await conn.execute(
            update(Character).where(Character.id == uuid.UUID(character_id)).values(is_dead=True)
        )


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """URL de la base de test : `DR_TEST_DATABASE_URL` ou un fichier SQLite temporaire."""
    return os.environ.get(TEST_DATABASE_URL_ENV) or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


def create_test_engine(url: str) -> AsyncEngine:
    """Moteur de test ; sur SQLite, active les clés étrangères (désactivées par défaut)."""
    engine = create_async_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Moteur sur un schéma vierge (`Base.metadata.create_all`) contenant la zone `valcendre`."""
    engine = create_test_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with create_sessionmaker(engine)() as session:
        session.add(
            Zone(
                id=DEFAULT_ZONE_ID,
                name="Valcendre",
                map_file="maps/valcendre.tmj",
                max_players=32,
                is_pvp=False,
                spawn_x=DEFAULT_ZONE_SPAWN[0],
                spawn_y=DEFAULT_ZONE_SPAWN[1],
            )
        )
        await session.commit()
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def redis() -> AsyncIterator[FakeRedis]:
    """Redis en mémoire (fakeredis), vidé à chaque test."""
    client = FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Réglages de test, indépendants de l'environnement et de tout fichier `.env`."""
    return Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        redis_url="redis://redis-non-utilise-en-test:6379/0",
        jwt_secret="secret-de-test-suffisamment-long-0123456789",
        zone_ticket_ttl_seconds=30,
        max_characters_per_account=1,
    )


@pytest.fixture
async def app(settings: Settings, engine: AsyncEngine, redis: FakeRedis) -> AsyncIterator[FastAPI]:
    """Application démarrée (lifespan exécuté : `app.state.*` rempli, boucles de zone lancées)."""
    application = create_app(settings, engine=engine, redis=redis)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Client HTTP asynchrone branché directement sur l'application ASGI (aucun réseau)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@dataclass(frozen=True)
class AuthenticatedAccount:
    """Compte créé et connecté par la fixture `create_account`."""

    id: uuid.UUID
    username: str
    password: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


CreateAccount = Callable[..., Awaitable[AuthenticatedAccount]]
CreateCharacter = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture
def create_account(client: httpx.AsyncClient) -> CreateAccount:
    """Fabrique : `await create_account(username=None, password=DEFAULT_PASSWORD)`.

    Inscrit puis connecte un compte via l'API REST ; pseudo aléatoire par défaut.
    """

    async def factory(username: str | None = None, password: str = DEFAULT_PASSWORD) -> AuthenticatedAccount:
        name = username or f"joueur_{uuid.uuid4().hex[:12]}"
        credentials = {"username": name, "password": password}
        registered = await client.post("/api/auth/register", json=credentials)
        assert registered.status_code == 201, registered.text
        logged_in = await client.post("/api/auth/login", json=credentials)
        assert logged_in.status_code == 200, logged_in.text
        return AuthenticatedAccount(
            id=uuid.UUID(registered.json()["id"]),
            username=name,
            password=password,
            token=logged_in.json()["access_token"],
        )

    return factory


@pytest.fixture
async def account(create_account: CreateAccount) -> AuthenticatedAccount:
    """Un compte prêt à l'emploi."""
    return await create_account()


@pytest.fixture
def auth_headers(account: AuthenticatedAccount) -> dict[str, str]:
    """En-têtes `Authorization: Bearer …` du compte de la fixture `account`."""
    return account.headers


@pytest.fixture
def create_character(client: httpx.AsyncClient) -> CreateCharacter:
    """Fabrique : `await create_character(account, name="Mara")` → corps JSON `CharacterOut`."""

    async def factory(owner: AuthenticatedAccount, name: str = "Mara") -> dict[str, Any]:
        response = await client.post("/api/characters", json={"name": name}, headers=owner.headers)
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    return factory
