"""AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1


class ProtocolModel(BaseModel):
    """Base des charges utiles : champs inconnus refusés, instances immuables."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ErrorCode = Literal["bad_message", "unknown_type", "rate_limited", "internal"]


class PingPayload(ProtocolModel):
    """Mesure de latence, envoyé environ une fois par seconde."""

    client_time: float = Field(ge=0, description="Horodatage client en millisecondes (performance.now()).")


class WelcomePayload(ProtocolModel):
    """Premier message après l'ouverture du WebSocket."""

    protocol_version: int = Field(ge=1)
    zone_id: str = Field(min_length=1, max_length=64)
    character_id: str = Field(min_length=1, max_length=64)
    tick_rate: int = Field(ge=1, description="Ticks de simulation par seconde.")
    server_time: float = Field(ge=0, description="Horodatage serveur en millisecondes.")


class PongPayload(ProtocolModel):
    """Réponse à `ping`."""

    client_time: float = Field(ge=0)
    server_time: float = Field(ge=0)


class ErrorPayload(ProtocolModel):
    """Message refusé ou erreur interne. La connexion reste ouverte sauf mention contraire."""

    code: ErrorCode
    message: str = Field(max_length=200)


ClientMessageType = Literal["ping"]
CLIENT_MESSAGES: dict[str, type[ProtocolModel]] = {"ping": PingPayload}

ServerMessageType = Literal["welcome", "pong", "error"]
SERVER_MESSAGES: dict[str, type[ProtocolModel]] = {"welcome": WelcomePayload, "pong": PongPayload, "error": ErrorPayload}
