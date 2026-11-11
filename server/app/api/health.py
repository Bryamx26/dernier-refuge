"""Sonde de santé : vérifie l'accès à la base et à Redis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas import HealthOut
from app.auth.deps import DbSession
from app.redis_client import RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["santé"])


@router.get("/health", response_model=HealthOut)
async def health(db: DbSession, redis: RedisClient, response: Response) -> HealthOut:
    """Renvoie 200 si tout répond, 503 (même corps) si une dépendance est indisponible."""
    database_ok = await _check_database(db)
    redis_ok = await _check_redis(redis)
    healthy = database_ok and redis_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(status="ok" if healthy else "degraded", database=database_ok, redis=redis_ok)


async def _check_database(db: DbSession) -> bool:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        logger.exception("Sonde de santé : base de données injoignable")
        return False
    return True


async def _check_redis(redis: RedisClient) -> bool:
    try:
        return bool(await redis.ping())
    except (RedisError, OSError):
        logger.exception("Sonde de santé : Redis injoignable")
        return False
