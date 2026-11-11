"""Inscription, connexion et profil (`/api/auth/*`)."""

from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.security import create_access_token
from app.config import Settings
from app.db.models import Account
from app.db.session import create_sessionmaker
from tests.conftest import DEFAULT_PASSWORD, AuthenticatedAccount, CreateAccount


async def _get_account(engine: AsyncEngine, username: str) -> Account:
    async with create_sessionmaker(engine)() as session:
        account = await session.scalar(select(Account).where(Account.username == username))
        assert account is not None
        return account


async def test_register_returns_account_without_secrets(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register", json={"username": "lea_42", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "lea_42"
    assert set(body) == {"id", "username"}


async def test_password_is_hashed(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    await client.post("/api/auth/register", json={"username": "lea", "password": DEFAULT_PASSWORD})
    account = await _get_account(engine, "lea")
    assert account.password_hash.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in account.password_hash


async def test_register_duplicate_username_conflicts(
    client: httpx.AsyncClient, create_account: CreateAccount
) -> None:
    await create_account(username="doublon")
    response = await client.post(
        "/api/auth/register", json={"username": "doublon", "password": "autre-mdp-123"}
    )
    assert response.status_code == 409


async def test_register_validates_input(client: httpx.AsyncClient) -> None:
    for payload in (
        {"username": "ab", "password": DEFAULT_PASSWORD},
        {"username": "espace interdit", "password": DEFAULT_PASSWORD},
        {"username": "valide", "password": "court"},
    ):
        response = await client.post("/api/auth/register", json=payload)
        assert response.status_code == 422, payload


async def test_login_returns_token_and_updates_last_login(
    client: httpx.AsyncClient, engine: AsyncEngine, settings: Settings
) -> None:
    await client.post("/api/auth/register", json={"username": "tom", "password": DEFAULT_PASSWORD})
    assert (await _get_account(engine, "tom")).last_login_at is None

    response = await client.post("/api/auth/login", json={"username": "tom", "password": DEFAULT_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_ttl_minutes * 60
    assert isinstance((await _get_account(engine, "tom")).last_login_at, datetime)


async def test_login_wrong_password_or_unknown_user_is_401(
    client: httpx.AsyncClient, account: AuthenticatedAccount
) -> None:
    wrong_password = await client.post(
        "/api/auth/login", json={"username": account.username, "password": "pas-le-bon-mdp"}
    )
    unknown_user = await client.post(
        "/api/auth/login", json={"username": "fantome", "password": DEFAULT_PASSWORD}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    # Même message : on ne révèle pas l'existence du pseudo.
    assert wrong_password.json() == unknown_user.json()


async def test_banned_account_cannot_login_or_use_token(
    client: httpx.AsyncClient, engine: AsyncEngine, account: AuthenticatedAccount
) -> None:
    async with engine.begin() as conn:
        await conn.execute(update(Account).where(Account.id == account.id).values(is_banned=True))

    login = await client.post(
        "/api/auth/login", json={"username": account.username, "password": account.password}
    )
    assert login.status_code == 403
    me = await client.get("/api/auth/me", headers=account.headers)
    assert me.status_code == 403


async def test_me_returns_current_account(client: httpx.AsyncClient, account: AuthenticatedAccount) -> None:
    response = await client.get("/api/auth/me", headers=account.headers)
    assert response.status_code == 200
    assert response.json() == {"id": str(account.id), "username": account.username}


async def test_me_rejects_missing_invalid_or_foreign_tokens(
    client: httpx.AsyncClient, account: AuthenticatedAccount, settings: Settings
) -> None:
    forged = create_access_token(account.id, "un-autre-secret-de-plus-de-32-caracteres", 60)
    expired = create_access_token(account.id, settings.jwt_secret, -1)
    for headers in (
        {},
        {"Authorization": "Bearer pas-un-jwt"},
        {"Authorization": f"Bearer {forged}"},
        {"Authorization": f"Bearer {expired}"},
    ):
        response = await client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401, headers
