"""Personnages du compte courant."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.schemas import CharacterCreate, CharacterOut
from app.auth.deps import AppSettings, CurrentAccount, DbSession
from app.db.models import Account, Character, Zone

# Zone d'apparition des nouveaux personnages (insérée par la migration initiale).
DEFAULT_ZONE_ID = "valcendre"

router = APIRouter(prefix="/characters", tags=["personnages"])


@router.get("", response_model=list[CharacterOut])
async def list_characters(account: CurrentAccount, db: DbSession) -> Sequence[Character]:
    """Personnages vivants du compte, du plus ancien au plus récent."""
    result = await db.scalars(
        select(Character)
        .where(Character.account_id == account.id, Character.is_dead.is_(False))
        .order_by(Character.created_at, Character.id)
    )
    return result.all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CharacterOut)
async def create_character(
    body: CharacterCreate, account: CurrentAccount, db: DbSession, settings: AppSettings
) -> Character:
    # Verrouille la ligne du compte (Postgres) : deux créations simultanées ne peuvent
    # pas dépasser la limite. Sans effet sur SQLite, qui sérialise déjà les écritures.
    await db.execute(select(Account.id).where(Account.id == account.id).with_for_update())
    alive_count = await db.scalar(
        select(func.count())
        .select_from(Character)
        .where(Character.account_id == account.id, Character.is_dead.is_(False))
    )
    if (alive_count or 0) >= settings.max_characters_per_account:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nombre maximal de personnages atteint")

    zone = await db.get(Zone, DEFAULT_ZONE_ID)
    if zone is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Zone d'apparition indisponible")

    character = Character(
        account_id=account.id, name=body.name, zone_id=zone.id, x=zone.spawn_x, y=zone.spawn_y
    )
    db.add(character)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce nom de personnage est déjà pris") from None
    return character
