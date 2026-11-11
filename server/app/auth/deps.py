"""Dépendances FastAPI d'authentification."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.config import Settings
from app.db.models import Account
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_current_account(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> Account:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Authentification requise", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    account_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    if account_id is None:
        raise unauthorized
    account = await db.get(Account, account_id)
    if account is None:
        raise unauthorized
    if account.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu")
    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
