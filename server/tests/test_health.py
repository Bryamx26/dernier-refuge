"""Sonde de santé `/api/health`."""

from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError as RedisConnectionError


async def test_health_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "redis": True}


async def test_health_degraded_when_redis_down(
    client: httpx.AsyncClient, redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_ping() -> bool:
        raise RedisConnectionError("panne simulée")

    monkeypatch.setattr(redis, "ping", failing_ping)
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": True, "redis": False}
