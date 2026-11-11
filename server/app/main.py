"""Point d'entrée ASGI : `uvicorn app.main:app`.

`create_app` assemble l'API REST, le WebSocket de zone et le cycle de vie des ressources
(base, Redis, boucles de zone). Les tests y injectent leur propre moteur et `fakeredis`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api import auth, characters, health, zones
from app.config import Settings, get_settings
from app.db.models import Zone
from app.db.session import create_engine, create_sessionmaker
from app.redis_client import create_redis
from app.zone.gateway import router as zone_router
from app.zone.manager import ZoneManager, ZoneSpec


async def load_zone_specs(sessionmaker: async_sessionmaker[AsyncSession], tick_rate: int) -> list[ZoneSpec]:
    """Lit les zones persistées et en déduit les paramètres des boucles de simulation."""
    async with sessionmaker() as session:
        rows = await session.scalars(select(Zone).order_by(Zone.id))
        return [
            ZoneSpec(id=zone.id, name=zone.name, max_players=zone.max_players, tick_rate=tick_rate)
            for zone in rows
        ]


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    redis: Redis | None = None,
) -> FastAPI:
    """Construit l'application.

    `engine` et `redis`, s'ils sont fournis, appartiennent à l'appelant : l'application
    ne les ferme pas à l'arrêt. Sinon ils sont créés au démarrage depuis `settings`.
    """
    app_settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            db_engine = engine
            if db_engine is None:
                db_engine = create_engine(app_settings.database_url)
                stack.push_async_callback(db_engine.dispose)
            redis_client = redis
            if redis_client is None:
                redis_client = create_redis(app_settings.redis_url)
                stack.push_async_callback(redis_client.aclose)

            sessionmaker = create_sessionmaker(db_engine)
            zone_manager = ZoneManager()
            app.state.settings = app_settings
            app.state.engine = db_engine
            app.state.sessionmaker = sessionmaker
            app.state.redis = redis_client
            app.state.zones = zone_manager

            specs = await load_zone_specs(sessionmaker, app_settings.tick_rate)
            # Enregistré avant `start` : un démarrage partiel est quand même arrêté proprement.
            stack.push_async_callback(zone_manager.stop)
            await zone_manager.start(specs)
            yield

    is_prod = app_settings.env == "prod"
    app = FastAPI(
        title="Dernier Refuge",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )
    # Pour que les dépendances fonctionnent aussi hors lifespan (ex. outils d'introspection).
    app.state.settings = app_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        # Authentification par en-tête Bearer : aucun cookie n'est échangé.
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    api = APIRouter(prefix="/api")
    for module in (health, auth, characters, zones):
        api.include_router(module.router)
    app.include_router(api)
    app.include_router(zone_router)
    return app


app = create_app()
