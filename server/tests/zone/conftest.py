"""Fixtures des tests de bout en bout du WebSocket de zone.

`starlette.testclient.TestClient` exécute l'application dans sa propre boucle d'événements
(autre thread). On réutilise donc les fixtures partagées `engine` (schéma + zone
`valcendre`) et `settings`, mais l'application crée son propre moteur sur
`settings.database_url` (cf. tests/conftest.py) et reçoit une instance fakeredis neuve,
utilisée uniquement dans la boucle du TestClient. Les accès directs à la base pendant un
test passent par `run_db` (exécutés dans la boucle du TestClient).

Les données de jeu (`DR_GAME_DATA_DIR`) pointent vers un dossier temporaire contenant une carte
`maps/valcendre.tmj` de test (`build_test_map`), indépendante de la vraie carte.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.characters import DEFAULT_ZONE_ID
from app.config import Settings
from app.main import create_app
from app.zone.movement import MOVEMENT_FILE, REPO_ROOT
from tests.conftest import DEFAULT_PASSWORD

# Fabrique de tickets : renvoie `(ticket, character_id)`.
IssueTicket = Callable[[], tuple[str, str]]
# Fabrique de joueurs : `new_player(username, character_name)` → fabrique de tickets.
NewPlayer = Callable[[str, str], IssueTicket]
T = TypeVar("T")
RunDb = Callable[[Callable[[AsyncSession], Awaitable[T]]], T]

TEST_MAP_SIZE = 96
# Bloc solide de la carte de test : tuiles x 70..72, y 60..68 (inclus).
TEST_WALL = (70, 72, 60, 68)
# Points d'apparition de la carte de test, en tuiles.
TEST_SPAWNS = [(66.5, 64.5), (30.5, 30.5)]


def build_test_map() -> dict[str, Any]:
    """Carte Tiled 96 × 96 : bords solides, un bloc solide, deux points d'apparition."""
    size = TEST_MAP_SIZE
    x0, x1, y0, y1 = TEST_WALL
    collision = [
        1 if tx in (0, size - 1) or ty in (0, size - 1) or (x0 <= tx <= x1 and y0 <= ty <= y1) else 0
        for ty in range(size)
        for tx in range(size)
    ]
    objects = [
        {
            "id": i + 1,
            "type": "player_spawn",
            "point": True,
            "x": x * 16,
            "y": y * 16,
            "width": 0,
            "height": 0,
        }
        for i, (x, y) in enumerate(TEST_SPAWNS)
    ]
    return {
        "type": "map",
        "orientation": "orthogonal",
        "infinite": False,
        "width": size,
        "height": size,
        "tilewidth": 16,
        "tileheight": 16,
        "tilesets": [],
        "layers": [
            {
                "id": 1,
                "name": "ground",
                "type": "tilelayer",
                "width": size,
                "height": size,
                "data": [1] * size**2,
            },
            {
                "id": 2,
                "name": "collision",
                "type": "tilelayer",
                "width": size,
                "height": size,
                "data": collision,
            },
            {"id": 3, "name": "spawns", "type": "objectgroup", "objects": objects},
        ],
    }


@pytest.fixture
def game_data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    (root / "maps").mkdir(parents=True)
    (root / "maps" / "valcendre.tmj").write_text(json.dumps(build_test_map()), encoding="utf-8")
    (root / MOVEMENT_FILE).parent.mkdir(parents=True)
    shutil.copy(REPO_ROOT / MOVEMENT_FILE, root / MOVEMENT_FILE)
    # Contenu de jeu du dépôt, sans peuplement de zone : pas de zombies dans ces tests.
    shutil.copytree(REPO_ROOT / "content", root / "content", ignore=shutil.ignore_patterns("zones"))
    return root


@pytest.fixture
def zone_client(settings: Settings, engine: AsyncEngine, game_data_dir: Path) -> Iterator[TestClient]:
    """Application complète (REST + WebSocket), lifespan démarré dans la boucle du TestClient."""
    app = create_app(
        settings.model_copy(update={"game_data_dir": game_data_dir}), redis=FakeRedis(decode_responses=True)
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def run_db(zone_client: TestClient) -> RunDb[Any]:
    """Exécute `await fn(session)` dans la boucle de l'application (et donc avec son moteur)."""

    def run(fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
        sessionmaker: async_sessionmaker[AsyncSession] = zone_client.app.state.sessionmaker  # type: ignore[attr-defined]

        async def call() -> T:
            async with sessionmaker() as session:
                result = await fn(session)
                await session.commit()
                return result

        assert zone_client.portal is not None
        return zone_client.portal.call(call)

    return run


@pytest.fixture
def new_player(zone_client: TestClient) -> NewPlayer:
    """Crée un compte et un personnage via l'API REST ; renvoie une fabrique de tickets.

    Chaque appel de la fabrique passe par `POST /api/zones/valcendre/join` et émet un nouveau ticket.
    """

    def create(username: str, name: str) -> IssueTicket:
        credentials = {"username": username, "password": DEFAULT_PASSWORD}
        assert zone_client.post("/api/auth/register", json=credentials).status_code == 201
        login = zone_client.post("/api/auth/login", json=credentials)
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = zone_client.post("/api/characters", json={"name": name}, headers=headers)
        assert created.status_code == 201, created.text
        character_id: str = created.json()["id"]

        def issue() -> tuple[str, str]:
            response = zone_client.post(
                f"/api/zones/{DEFAULT_ZONE_ID}/join", json={"character_id": character_id}, headers=headers
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["ws_path"] == f"/ws/zone/{DEFAULT_ZONE_ID}"
            return body["ticket"], character_id

        return issue

    return create


@pytest.fixture
def join_ticket(new_player: NewPlayer) -> IssueTicket:
    """Fabrique de tickets d'un personnage « Alice » (compte « survivant »)."""
    return new_player("survivant", "Alice")
