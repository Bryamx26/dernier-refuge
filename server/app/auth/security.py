"""Hachage des mots de passe (Argon2id) et jetons d'accès JWT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(account_id: uuid.UUID, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(account_id), "iat": now, "exp": now + timedelta(minutes=ttl_minutes)}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> uuid.UUID | None:
    """Renvoie l'identifiant du compte, ou None si le jeton est invalide ou expiré."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]})
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
