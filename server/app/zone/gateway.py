"""Passerelle WebSocket des zones : `/ws/zone/{zone_id}?ticket=…`.

Cycle de connexion :
1. le client obtient un ticket via `POST /api/zones/{zone_id}/join` ;
2. il ouvre le WebSocket avec ce ticket, consommé ici (usage unique) ;
3. le serveur répond `welcome`, puis traite les messages reçus.

Les refus avant `welcome` se font par fermeture avec un code 4xxx (voir docs/architecture/protocol.md).

Tous les envois passent par la file sortante de la session (`ClientSession.post`), vidée par une
tâche d'écriture ; la réception tourne dans sa propre tâche. La connexion se termine quand le client
part, quand la session se ferme (4008, 4009, 1001) ou quand la zone s'arrête.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from enum import IntEnum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.protocol.codec import ClientEnvelope, ProtocolError, decode_client
from app.protocol.generated import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorPayload,
    PingPayload,
    PongPayload,
    WelcomePayload,
)
from app.zone.manager import ZoneManager
from app.zone.persistence import PlayerStore, SavedPosition, SqlPlayerStore
from app.zone.runtime import AlreadyConnectedError, ZoneFullError
from app.zone.session import CLOSE_TOO_SLOW, ClientSession
from app.zone.tickets import consume_ticket

logger = logging.getLogger(__name__)

router = APIRouter()

# Nombre de messages refusés (débit ou protocole) entraînant la fermeture 4008.
MAX_REJECTED_MESSAGES = 50


class CloseCode(IntEnum):
    """Codes de fermeture applicatifs (contrat phase 1)."""

    # Ticket refusé, ou personnage introuvable, mort, dans une autre zone ou compte suspendu.
    INVALID_TICKET = 4001
    ALREADY_CONNECTED = 4002
    ZONE_FULL = 4003
    UNKNOWN_ZONE = 4004
    TOO_MANY_REJECTED = 4008
    TOO_SLOW = CLOSE_TOO_SLOW


def server_time_ms() -> float:
    """Horodatage serveur (epoch) en millisecondes."""
    return time.time() * 1000


@router.websocket("/ws/zone/{zone_id}")
async def zone_websocket(websocket: WebSocket, zone_id: str, ticket: str = "") -> None:
    # On accepte avant toute vérification : un refus avant `accept` serait vu par le
    # navigateur comme un échec HTTP 403, sans code de fermeture exploitable.
    await websocket.accept()

    zones: ZoneManager = websocket.app.state.zones
    zone = zones.get(zone_id)
    if zone is None:
        await websocket.close(CloseCode.UNKNOWN_ZONE, "zone inconnue")
        return

    redis: Redis = websocket.app.state.redis
    info = await consume_ticket(redis, ticket)
    if info is None or info.zone_id != zone_id:
        await websocket.close(CloseCode.INVALID_TICKET, "ticket invalide")
        return

    store = zones.store if zones.store is not None else SqlPlayerStore(websocket.app.state.sessionmaker)
    character = await store.load_character(info.character_id)
    if character is None or character.is_dead or character.account_banned or character.zone_id != zone_id:
        await websocket.close(CloseCode.INVALID_TICKET, "personnage indisponible")
        return

    session = ClientSession(websocket, character_id=info.character_id, tick_source=lambda: zone.tick)
    try:
        player = zone.register(
            session, name=character.name, position=(character.x, character.y), aim=character.facing
        )
    except AlreadyConnectedError:
        await websocket.close(CloseCode.ALREADY_CONNECTED, "personnage déjà connecté")
        return
    except ZoneFullError:
        await websocket.close(CloseCode.ZONE_FULL, "zone pleine")
        return

    # Aucun `await` entre l'inscription et ce `post` : `welcome` est toujours le message n° 1,
    # avant le premier snapshot.
    session.post(
        "welcome",
        WelcomePayload(
            protocol_version=PROTOCOL_VERSION,
            zone_id=zone_id,
            character_id=info.character_id,
            tick_rate=zone.spec.tick_rate,
            server_time=server_time_ms(),
            entity_id=player.entity_id,
            map_id=zone.map.map_id,
        ),
    )
    session.start_writer()
    logger.info("zone %s : connexion de %s (%s)", zone_id, info.character_id, player.entity_id)
    try:
        await _serve(session)
    finally:
        try:
            # Sauvegarde avant désinscription : une reconnexion immédiate relit la bonne position
            # (au pire, elle est refusée en 4002 pendant ces quelques millisecondes). Protégée de
            # l'annulation : le serveur peut annuler le gestionnaire dès la déconnexion.
            current = zone.player(session)
            if current is not None:
                await asyncio.shield(_save_position(store, current.saved_position(), zone_id))
        finally:
            zone.unregister(session)
            try:
                await session.shutdown()
            finally:
                session.abort()
            logger.info("zone %s : déconnexion de %s", zone_id, info.character_id)


async def _save_position(store: PlayerStore, position: SavedPosition, zone_id: str) -> None:
    try:
        await store.save_positions([position])
    except Exception:
        logger.exception("zone %s : échec de la sauvegarde de %s", zone_id, position.character_id)


async def _serve(session: ClientSession) -> None:
    """Attend la fin de la réception (client parti, abus) ou la fermeture de la session (4009, 1001)."""
    receiver = asyncio.create_task(_receive_loop(session))
    closed = asyncio.create_task(session.closed.wait())
    try:
        await asyncio.wait({receiver, closed}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (receiver, closed):
            task.cancel()
        for task in (receiver, closed):
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await task


async def _receive_loop(session: ClientSession) -> None:
    """Lit les messages jusqu'à la déconnexion ou la fermeture pour abus."""
    websocket = session.websocket
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        raw: str | bytes | None = message.get("text")
        if raw is None:
            raw = message.get("bytes") or b""

        if not session.allow_message():
            if not _reject(session, "rate_limited", "trop de messages"):
                return
            continue
        try:
            envelope = decode_client(raw)
        except ProtocolError as exc:
            if not _reject(session, exc.code, exc.message):
                return
            continue
        _dispatch(session, envelope)


def _dispatch(session: ClientSession, envelope: ClientEnvelope) -> None:
    """Traite un message valide."""
    payload = envelope.payload
    if isinstance(payload, PingPayload):
        # Message de transport : réponse immédiate, hors boucle de simulation.
        session.post("pong", PongPayload(client_time=payload.client_time, server_time=server_time_ms()))
        return
    # Message de jeu (`input`) : appliqué par la zone aux prochains ticks. File bornée : si elle
    # déborde, les entrées les plus anciennes sont jetées (le client les rejouera après ack).
    session.enqueue_input(envelope)


def _reject(session: ClientSession, code: ErrorCode, message: str) -> bool:
    """Signale un refus au client. Renvoie False si la connexion est fermée (abus)."""
    session.rejected_count += 1
    if session.rejected_count >= MAX_REJECTED_MESSAGES:
        logger.warning("connexion de %s fermée : trop de messages refusés", session.character_id)
        session.close(CloseCode.TOO_MANY_REJECTED, "trop de messages refusés")
        return False
    session.post("error", ErrorPayload(code=code, message=message))
    return True
