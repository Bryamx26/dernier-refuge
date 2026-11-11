"""Inscription, connexion et profil du compte courant."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.api.rate_limit import rate_limit
from app.api.schemas import AccountOut, LoginRequest, RegisterRequest, TokenOut
from app.auth.deps import AppSettings, CurrentAccount, DbSession
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import Account

router = APIRouter(prefix="/auth", tags=["authentification"])


@cache
def _dummy_password_hash() -> str:
    """Hash Argon2id factice, vérifié quand le compte n'existe pas.

    Le temps de réponse d'une connexion ne révèle ainsi pas si le pseudo existe.
    Calculé une seule fois, au premier besoin.
    """
    return hash_password("mot-de-passe-factice-jamais-valide")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AccountOut,
    dependencies=[Depends(rate_limit("register"))],
)
async def register(body: RegisterRequest, db: DbSession) -> Account:
    # Argon2id est volontairement coûteux : on le sort de la boucle d'événements (ticks de zone).
    password_hash = await run_in_threadpool(hash_password, body.password)
    account = Account(username=body.username, password_hash=password_hash)
    db.add(account)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà pris") from None
    return account


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("login"))])
async def login(body: LoginRequest, db: DbSession, settings: AppSettings) -> TokenOut:
    account = await db.scalar(select(Account).where(Account.username == body.username))
    password_hash = account.password_hash if account is not None else _dummy_password_hash()
    password_ok = await run_in_threadpool(verify_password, password_hash, body.password)
    if account is None or not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Pseudo ou mot de passe invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if account.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu")

    account.last_login_at = datetime.now(UTC)
    await db.commit()
    token = create_access_token(account.id, settings.jwt_secret, settings.jwt_ttl_minutes)
    return TokenOut(access_token=token, expires_in=settings.jwt_ttl_minutes * 60)


@router.get("/me", response_model=AccountOut)
async def me(account: CurrentAccount) -> Account:
    return account
