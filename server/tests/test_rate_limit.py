"""Limitation de débit sur l'authentification et refus du secret de dev en production."""

from __future__ import annotations

import httpx
import pytest

from app.config import DEV_JWT_SECRET, Settings


async def test_login_rate_limited(client: httpx.AsyncClient, settings: Settings) -> None:
    body = {"username": "inconnu", "password": "mauvais-mdp"}
    for _ in range(settings.auth_rate_limit_per_minute):
        response = await client.post("/api/auth/login", json=body)
        assert response.status_code == 401
    response = await client.post("/api/auth/login", json=body)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_prod_refuses_dev_secret() -> None:
    with pytest.raises(ValueError, match="DR_JWT_SECRET"):
        Settings(env="prod", jwt_secret=DEV_JWT_SECRET)
    assert Settings(env="prod", jwt_secret="x" * 40).env == "prod"
