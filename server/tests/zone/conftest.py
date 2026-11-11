"""Fixtures des tests de bout en bout du WebSocket de zone.

`starlette.testclient.TestClient` exécute l'application dans sa propre boucle d'événements
(autre thread). On réutilise donc les fixtures partagées `engine` (schéma + zone
`valcendre`) et `settings`, mais l'application crée son propre moteur sur
`settings.database_url` (cf. tests/conftest.py) et reçoit une instance fakeredis neuve,
utilisée uniquement dans la boucle du TestClient.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.characters import DEFAULT_ZONE_ID
from app.config import Settings
from app.main import create_app
from tests.conftest import DEFAULT_PASSWORD

# Fabrique de tickets : renvoie `(ticket, character_id)`.
IssueTicket = Callable[[], tuple[str, str]]


@pytest.fixture
def zone_client(settings: Settings, engine: AsyncEngine) -> Iterator[TestClient]:
    """Application complète (REST + WebSocket), lifespan démarré dans la boucle du TestClient."""
    app = create_app(settings, redis=FakeRedis(decode_responses=True))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def join_ticket(zone_client: TestClient) -> IssueTicket:
    """Crée un compte et un personnage via l'API REST, puis renvoie une fabrique de tickets.

    Chaque appel passe par `POST /api/zones/valcendre/join` et émet un nouveau ticket.
    """
    credentials = {"username": "survivant", "password": DEFAULT_PASSWORD}
    assert zone_client.post("/api/auth/register", json=credentials).status_code == 201
    login = zone_client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = zone_client.post("/api/characters", json={"name": "Alice"}, headers=headers)
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
