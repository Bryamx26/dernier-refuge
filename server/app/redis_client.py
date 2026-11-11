"""Client Redis asynchrone partagé par l'application."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis


def create_redis(redis_url: str) -> Redis:
    """Crée un client `redis.asyncio` qui renvoie des `str` (decode_responses=True)."""
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    return client


def get_redis(request: Request) -> Redis:
    """Dépendance FastAPI : le client Redis créé (ou injecté) au démarrage de l'application."""
    redis: Redis = request.app.state.redis
    return redis


RedisClient = Annotated[Redis, Depends(get_redis)]
