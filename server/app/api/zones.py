"""Liste des zones et émission des tickets d'entrée WebSocket."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.schemas import JoinZoneOut, JoinZoneRequest, ZoneOut
from app.auth.deps import AppSettings, CurrentAccount, DbSession
from app.db.models import Character, Zone
from app.redis_client import RedisClient
from app.zone.manager import ZoneManager
from app.zone.tickets import issue_ticket

router = APIRouter(prefix="/zones", tags=["zones"])


def get_zone_manager(request: Request) -> ZoneManager:
    zones: ZoneManager = request.app.state.zones
    return zones


Zones = Annotated[ZoneManager, Depends(get_zone_manager)]


@router.get("", response_model=list[ZoneOut])
async def list_zones(_: CurrentAccount, db: DbSession, zones: Zones) -> list[ZoneOut]:
    result = await db.scalars(select(Zone).order_by(Zone.id))
    return [
        ZoneOut(
            id=zone.id,
            name=zone.name,
            max_players=zone.max_players,
            online=zones.online_count(zone.id),
            is_pvp=zone.is_pvp,
        )
        for zone in result
    ]


@router.post("/{zone_id}/join", response_model=JoinZoneOut)
async def join_zone(
    zone_id: str,
    body: JoinZoneRequest,
    account: CurrentAccount,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> JoinZoneOut:
    zone = await db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone inconnue")
    character = await db.get(Character, body.character_id)
    # Le personnage d'un autre compte est traité comme inexistant (pas de fuite d'information).
    if character is None or character.account_id != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Personnage inconnu")
    if character.is_dead:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce personnage est mort")
    if character.zone_id != zone.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce personnage se trouve dans une autre zone")

    ttl = settings.zone_ticket_ttl_seconds
    ticket = await issue_ticket(redis, character_id=str(character.id), zone_id=zone.id, ttl_seconds=ttl)
    return JoinZoneOut(ticket=ticket, ws_path=f"/ws/zone/{zone.id}", expires_in=ttl)
