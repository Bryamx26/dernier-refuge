"""Modèles persistants de la phase 1 : comptes, zones, personnages.

Les vitals, blessures, inventaires et compétences arrivent avec leurs phases
(voir docs/architecture/data-model.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(24), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    characters: Mapped[list[Character]] = relationship(back_populates="account")


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    map_file: Mapped[str] = mapped_column(String(128))
    max_players: Mapped[int] = mapped_column(Integer)
    is_pvp: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    spawn_x: Mapped[float] = mapped_column(Float)
    spawn_y: Mapped[float] = mapped_column(Float)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(24), unique=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    # Position en tuiles (float), orientation en radians.
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    facing: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    is_dead: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    play_time_s: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="characters")
