"""Accès base de données des serveurs de zone : chargement du personnage, sauvegarde des positions.

Toutes les opérations sont asynchrones et appelées hors de la boucle de tick (passerelle à la
connexion/déconnexion, tâche de sauvegarde périodique de la zone).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Account, Character


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    """Personnage chargé à l'ouverture du WebSocket, avec l'état de son compte."""

    id: str
    name: str
    zone_id: str
    x: float
    y: float
    facing: float
    is_dead: bool
    account_banned: bool


@dataclass(frozen=True, slots=True)
class SavedPosition:
    """Position persistée d'un personnage (tuiles, radians)."""

    character_id: str
    x: float
    y: float
    facing: float


class PlayerStore(Protocol):
    """Persistance utilisée par les zones (implémentation SQL ci-dessous, mémoire dans les tests)."""

    async def load_character(self, character_id: str) -> CharacterRecord | None: ...

    async def save_positions(self, positions: list[SavedPosition]) -> None: ...


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class SqlPlayerStore:
    """`PlayerStore` sur SQLAlchemy (Postgres en production, SQLite en test)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def load_character(self, character_id: str) -> CharacterRecord | None:
        key = _parse_uuid(character_id)
        if key is None:
            return None
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(Character, Account.is_banned)
                    .join(Account, Account.id == Character.account_id)
                    .where(Character.id == key)
                )
            ).first()
        if row is None:
            return None
        character, banned = row
        return CharacterRecord(
            id=str(character.id),
            name=character.name,
            zone_id=character.zone_id,
            x=character.x,
            y=character.y,
            facing=character.facing,
            is_dead=character.is_dead,
            account_banned=bool(banned),
        )

    async def save_positions(self, positions: list[SavedPosition]) -> None:
        """Met à jour `x`, `y`, `facing` de plusieurs personnages en une transaction."""
        rows = [
            {"id": key, "x": p.x, "y": p.y, "facing": p.facing}
            for p in positions
            if (key := _parse_uuid(p.character_id)) is not None
        ]
        if not rows:
            return
        async with self._sessionmaker() as session:
            # « Bulk UPDATE by primary key » de SQLAlchemy 2 : un executemany.
            await session.execute(update(Character), rows)
            await session.commit()
