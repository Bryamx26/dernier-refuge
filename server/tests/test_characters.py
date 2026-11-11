"""Personnages (`/api/characters`)."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.characters import DEFAULT_ZONE_ID
from tests.conftest import (
    DEFAULT_ZONE_SPAWN,
    AuthenticatedAccount,
    CreateAccount,
    CreateCharacter,
    kill_character,
)


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/characters")).status_code == 401
    assert (await client.post("/api/characters", json={"name": "Mara"})).status_code == 401


async def test_create_spawns_in_default_zone(
    client: httpx.AsyncClient, account: AuthenticatedAccount
) -> None:
    response = await client.post("/api/characters", json={"name": "Élise Durand"}, headers=account.headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Élise Durand"
    assert body["zone_id"] == DEFAULT_ZONE_ID
    assert (body["x"], body["y"]) == DEFAULT_ZONE_SPAWN
    assert body["is_dead"] is False


async def test_list_returns_only_own_living_characters(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    create_account: CreateAccount,
    create_character: CreateCharacter,
) -> None:
    alice, bob = await create_account(), await create_account()
    alice_char = await create_character(alice, name="Alice")
    await create_character(bob, name="Bobby")

    listed = await client.get("/api/characters", headers=alice.headers)
    assert listed.status_code == 200
    assert listed.json() == [alice_char]

    await kill_character(engine, alice_char["id"])
    assert (await client.get("/api/characters", headers=alice.headers)).json() == []


async def test_name_taken_conflicts(
    client: httpx.AsyncClient, create_account: CreateAccount, create_character: CreateCharacter
) -> None:
    await create_character(await create_account(), name="Unique")
    other = await create_account()
    response = await client.post("/api/characters", json={"name": "Unique"}, headers=other.headers)
    assert response.status_code == 409


async def test_living_character_limit(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    account: AuthenticatedAccount,
    create_character: CreateCharacter,
) -> None:
    first = await create_character(account, name="Premier")
    response = await client.post("/api/characters", json={"name": "Second"}, headers=account.headers)
    assert response.status_code == 409

    # Un personnage mort ne compte plus : le joueur peut recommencer.
    await kill_character(engine, first["id"])
    await create_character(account, name="Second")


async def test_invalid_name_rejected(client: httpx.AsyncClient, account: AuthenticatedAccount) -> None:
    for name in ("A", "1nvalide", "Trop" * 10, "Fin-"):
        response = await client.post("/api/characters", json={"name": name}, headers=account.headers)
        assert response.status_code == 422, name
