"""Zones (`/api/zones`) et émission des tickets d'entrée."""

from __future__ import annotations

import uuid

import httpx
from fakeredis.aioredis import FakeRedis
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.characters import DEFAULT_ZONE_ID
from app.config import Settings
from app.db.models import Zone
from app.zone.tickets import TicketInfo, consume_ticket
from tests.conftest import AuthenticatedAccount, CreateAccount, CreateCharacter, kill_character


def _join_url(zone_id: str = DEFAULT_ZONE_ID) -> str:
    return f"/api/zones/{zone_id}/join"


async def test_list_zones(client: httpx.AsyncClient, account: AuthenticatedAccount) -> None:
    response = await client.get("/api/zones", headers=account.headers)
    assert response.status_code == 200
    assert response.json() == [
        {"id": DEFAULT_ZONE_ID, "name": "Valcendre", "max_players": 32, "online": 0, "is_pvp": False}
    ]


async def test_zones_require_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/zones")).status_code == 401
    response = await client.post(_join_url(), json={"character_id": str(uuid.uuid4())})
    assert response.status_code == 401


async def test_join_issues_single_use_ticket(
    client: httpx.AsyncClient,
    redis: FakeRedis,
    settings: Settings,
    account: AuthenticatedAccount,
    create_character: CreateCharacter,
) -> None:
    character = await create_character(account)
    response = await client.post(_join_url(), json={"character_id": character["id"]}, headers=account.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ws_path"] == f"/ws/zone/{DEFAULT_ZONE_ID}"
    assert body["expires_in"] == settings.zone_ticket_ttl_seconds

    expected = TicketInfo(character_id=character["id"], zone_id=DEFAULT_ZONE_ID)
    assert await consume_ticket(redis, body["ticket"]) == expected
    assert await consume_ticket(redis, body["ticket"]) is None


async def test_join_unknown_zone_or_character_is_404(
    client: httpx.AsyncClient,
    create_account: CreateAccount,
    create_character: CreateCharacter,
) -> None:
    owner, intruder = await create_account(), await create_account()
    character = await create_character(owner)

    unknown_zone = await client.post(
        _join_url("nulle-part"), json={"character_id": character["id"]}, headers=owner.headers
    )
    unknown_character = await client.post(
        _join_url(), json={"character_id": str(uuid.uuid4())}, headers=owner.headers
    )
    foreign_character = await client.post(
        _join_url(), json={"character_id": character["id"]}, headers=intruder.headers
    )
    assert unknown_zone.status_code == unknown_character.status_code == foreign_character.status_code == 404


async def test_join_dead_character_conflicts(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    account: AuthenticatedAccount,
    create_character: CreateCharacter,
) -> None:
    character = await create_character(account)
    await kill_character(engine, character["id"])
    response = await client.post(_join_url(), json={"character_id": character["id"]}, headers=account.headers)
    assert response.status_code == 409


async def test_join_other_zone_conflicts(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    account: AuthenticatedAccount,
    create_character: CreateCharacter,
) -> None:
    character = await create_character(account)
    async with engine.begin() as conn:
        await conn.execute(
            insert(Zone).values(
                id="cendrelune",
                name="Cendrelune",
                map_file="maps/cendrelune.tmj",
                max_players=8,
                is_pvp=True,
                spawn_x=1.0,
                spawn_y=1.0,
            )
        )
    response = await client.post(
        _join_url("cendrelune"), json={"character_id": character["id"]}, headers=account.headers
    )
    assert response.status_code == 409
