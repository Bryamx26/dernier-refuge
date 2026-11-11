"""Tests des tickets d'entrée en zone (Redis simulé par fakeredis)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import fakeredis
import pytest
from redis.asyncio import Redis

from app.zone.tickets import TicketInfo, consume_ticket, issue_ticket


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield client
    await client.aclose()


async def test_issue_then_consume(redis: Redis) -> None:
    ticket = await issue_ticket(redis, character_id="c1", zone_id="valcendre", ttl_seconds=30)
    assert len(ticket) >= 40
    assert await consume_ticket(redis, ticket) == TicketInfo(character_id="c1", zone_id="valcendre")


async def test_ticket_is_single_use(redis: Redis) -> None:
    ticket = await issue_ticket(redis, character_id="c1", zone_id="valcendre", ttl_seconds=30)
    assert await consume_ticket(redis, ticket) is not None
    assert await consume_ticket(redis, ticket) is None


async def test_ticket_has_ttl(redis: Redis) -> None:
    ticket = await issue_ticket(redis, character_id="c1", zone_id="valcendre", ttl_seconds=30)
    assert 0 < await redis.ttl(f"zone_ticket:{ticket}") <= 30


async def test_tickets_are_unique(redis: Redis) -> None:
    tickets = {await issue_ticket(redis, character_id="c1", zone_id="z", ttl_seconds=30) for _ in range(20)}
    assert len(tickets) == 20


@pytest.mark.parametrize("ticket", ["", "inconnu", "x" * 1000])
async def test_unknown_ticket(redis: Redis, ticket: str) -> None:
    assert await consume_ticket(redis, ticket) is None


async def test_corrupted_ticket_is_rejected(redis: Redis) -> None:
    await redis.set("zone_ticket:abc", "pas du json")
    assert await consume_ticket(redis, "abc") is None
    assert await redis.exists("zone_ticket:abc") == 0
