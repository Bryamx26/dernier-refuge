"""AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 2


class ProtocolModel(BaseModel):
    """Base des charges utiles : champs inconnus refusés, instances immuables."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ErrorCode = Literal["bad_message", "unknown_type", "rate_limited", "internal"]


AnimState = Literal["idle", "walk", "run"]


class EntityState(ProtocolModel):
    """État d'une entité visible dans un snapshot. Positions en tuiles, angle en radians."""

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["player"]
    name: str = Field(max_length=24)
    x: float
    y: float
    aim: float = Field(description="Orientation en radians (0 = vers la droite, sens horaire écran).")
    anim: AnimState


class PingPayload(ProtocolModel):
    """Mesure de latence, envoyé environ une fois par seconde."""

    client_time: float = Field(ge=0, description="Horodatage client en millisecondes (performance.now()).")


class InputPayload(ProtocolModel):
    """Entrée de déplacement pour UN pas de simulation (1/tick_rate s). Envoyé à tick_rate Hz. Le `seq` de l'enveloppe sert de numéro d'entrée pour la réconciliation."""

    move_x: float = Field(ge=-1, le=1, description="Axe horizontal, -1 (gauche) à 1 (droite).")
    move_y: float = Field(ge=-1, le=1, description="Axe vertical, -1 (haut) à 1 (bas).")
    aim: float = Field(ge=-7, le=7, description="Orientation souhaitée en radians.")
    sprint: bool


class WelcomePayload(ProtocolModel):
    """Premier message après l'ouverture du WebSocket."""

    protocol_version: int = Field(ge=1)
    zone_id: str = Field(min_length=1, max_length=64)
    character_id: str = Field(min_length=1, max_length=64)
    tick_rate: int = Field(ge=1, description="Ticks de simulation par seconde.")
    server_time: float = Field(ge=0, description="Horodatage serveur en millisecondes.")
    entity_id: str = Field(min_length=1, max_length=64, description="Identifiant de l'entité du joueur dans les snapshots.")
    map_id: str = Field(min_length=1, max_length=64, description="Carte de la zone, chargée depuis /game/maps/<map_id>.tmj.")


class SnapshotPayload(ProtocolModel):
    """État des entités proches du joueur, envoyé à chaque tick. Une entité absente du snapshot n'est plus visible."""

    ack_seq: int = Field(ge=0, description="`seq` de la dernière entrée du joueur appliquée par le serveur (0 si aucune).")
    entities: list[EntityState]


class PongPayload(ProtocolModel):
    """Réponse à `ping`."""

    client_time: float = Field(ge=0)
    server_time: float = Field(ge=0)


class ErrorPayload(ProtocolModel):
    """Message refusé ou erreur interne. La connexion reste ouverte sauf mention contraire."""

    code: ErrorCode
    message: str = Field(max_length=200)


ClientMessageType = Literal["ping", "input"]
CLIENT_MESSAGES: dict[str, type[ProtocolModel]] = {"ping": PingPayload, "input": InputPayload}

ServerMessageType = Literal["welcome", "snapshot", "pong", "error"]
SERVER_MESSAGES: dict[str, type[ProtocolModel]] = {"welcome": WelcomePayload, "snapshot": SnapshotPayload, "pong": PongPayload, "error": ErrorPayload}
