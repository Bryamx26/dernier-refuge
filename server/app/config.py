"""Configuration du serveur, lue depuis l'environnement (préfixe `DR_`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-a-changer-en-production-0123456789"
# Racine du dépôt (server/app/config.py → parents[2]) : contient maps/, assets/ et shared/.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DR_", env_file=".env", extra="ignore")

    env: str = Field(default="dev", description="dev, test ou prod")
    database_url: str = "postgresql+asyncpg://refuge:refuge@localhost:5432/refuge"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(default=DEV_JWT_SECRET, min_length=32)
    jwt_ttl_minutes: int = 60 * 24
    zone_ticket_ttl_seconds: int = 30

    tick_rate: int = Field(default=20, ge=1, le=60)
    max_characters_per_account: int = 1
    cors_origins: list[str] = ["http://localhost:5173"]
    game_data_dir: Path = Field(
        default=REPO_ROOT, description="Racine des données de jeu (maps/, shared/movement/), DR_GAME_DATA_DIR"
    )
    auth_rate_limit_per_minute: int = Field(default=20, ge=1, description="Par IP, pour login et register")

    @model_validator(mode="after")
    def _refuse_dev_secret_in_prod(self) -> Settings:
        if self.env == "prod" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("DR_JWT_SECRET doit être défini en production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
