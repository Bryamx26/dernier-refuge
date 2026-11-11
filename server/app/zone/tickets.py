"""Tickets d'entrée en zone, à usage unique, stockés dans Redis.

La route REST `POST /api/zones/{zone_id}/join` émet un ticket ; le WebSocket de zone
le consomme à l'ouverture. Le ticket évite de faire transiter le JWT dans l'URL du
WebSocket et lie la connexion à un personnage et une zone précis.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

from redis.asyncio import Redis

_KEY_PREFIX = "zone_ticket:"
# 32 octets aléatoires → 43 caractères en base64 URL ; borne large pour filtrer les entrées absurdes.
_TICKET_BYTES = 32
_MAX_TICKET_LENGTH = 128


@dataclass(frozen=True)
class TicketInfo:
    character_id: str
    zone_id: str


def _key(ticket: str) -> str:
    return f"{_KEY_PREFIX}{ticket}"


async def issue_ticket(redis: Redis, *, character_id: str, zone_id: str, ttl_seconds: int) -> str:
    """Crée un ticket valable `ttl_seconds` secondes et le renvoie."""
    ticket = secrets.token_urlsafe(_TICKET_BYTES)
    value = json.dumps({"character_id": character_id, "zone_id": zone_id})
    await redis.set(_key(ticket), value, ex=ttl_seconds)
    return ticket


async def consume_ticket(redis: Redis, ticket: str) -> TicketInfo | None:
    """Consomme le ticket (GETDEL atomique). Renvoie `None` s'il est absent, expiré ou déjà utilisé."""
    if not ticket or len(ticket) > _MAX_TICKET_LENGTH:
        return None
    raw = await redis.getdel(_key(ticket))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return TicketInfo(character_id=str(data["character_id"]), zone_id=str(data["zone_id"]))
    except (ValueError, TypeError, KeyError):
        # Valeur corrompue : le ticket est refusé (et déjà supprimé par GETDEL).
        return None
