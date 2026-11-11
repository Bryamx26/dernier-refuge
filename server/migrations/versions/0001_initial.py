"""Schéma initial : comptes, zones, personnages, et zone par défaut Valcendre.

Révision : 0001
Parente : aucune
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=24), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_banned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("username", name=op.f("uq_accounts_username")),
    )
    zones = op.create_table(
        "zones",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("map_file", sa.String(length=128), nullable=False),
        sa.Column("max_players", sa.Integer(), nullable=False),
        sa.Column("is_pvp", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("spawn_x", sa.Float(), nullable=False),
        sa.Column("spawn_y", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zones")),
    )
    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=24), nullable=False),
        sa.Column("zone_id", sa.String(length=64), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("facing", sa.Float(), server_default="0", nullable=False),
        sa.Column("is_dead", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("play_time_s", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_characters_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], name=op.f("fk_characters_zone_id_zones")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_characters")),
        sa.UniqueConstraint("name", name=op.f("uq_characters_name")),
    )
    op.create_index(op.f("ix_characters_account_id"), "characters", ["account_id"], unique=False)

    assert zones is not None
    op.bulk_insert(
        zones,
        [
            {
                "id": "valcendre",
                "name": "Valcendre",
                "map_file": "maps/valcendre.tmj",
                "max_players": 32,
                "is_pvp": False,
                "spawn_x": 64.0,
                "spawn_y": 64.0,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_characters_account_id"), table_name="characters")
    op.drop_table("characters")
    op.drop_table("zones")
    op.drop_table("accounts")
