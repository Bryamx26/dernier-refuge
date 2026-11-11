"""Limitation de débit des routes sensibles (fenêtre fixe d'une minute, stockée dans Redis)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status

from app.auth.deps import AppSettings
from app.redis_client import RedisClient

WINDOW_SECONDS = 60


def rate_limit(scope: str) -> Callable[[Request, RedisClient, AppSettings], Awaitable[None]]:
    """Dépendance qui refuse (429) au-delà de `settings.auth_rate_limit_per_minute` requêtes par IP."""

    async def dependency(request: Request, redis: RedisClient, settings: AppSettings) -> None:
        client_ip = request.client.host if request.client else "inconnu"
        key = f"rate:{scope}:{client_ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, WINDOW_SECONDS)
        if count > settings.auth_rate_limit_per_minute:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Trop de tentatives, réessaie dans une minute",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

    return dependency
