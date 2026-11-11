"""Schémas des requêtes et réponses REST (contrat publié via OpenAPI)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_-]{3,24}$"
CHARACTER_NAME_PATTERN = r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,22}[A-Za-zÀ-ÿ]$"


class RegisterRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(max_length=24)
    password: str = Field(max_length=128)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Durée de validité en secondes")


class CharacterCreate(BaseModel):
    name: str = Field(pattern=CHARACTER_NAME_PATTERN)


class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    zone_id: str
    x: float
    y: float
    is_dead: bool


class ZoneOut(BaseModel):
    id: str
    name: str
    max_players: int
    online: int
    is_pvp: bool


class JoinZoneRequest(BaseModel):
    character_id: uuid.UUID


class JoinZoneOut(BaseModel):
    ticket: str = Field(description="Ticket à usage unique, à passer en paramètre `ticket` du WebSocket")
    ws_path: str
    expires_in: int


class HealthOut(BaseModel):
    status: str
    database: bool
    redis: bool
