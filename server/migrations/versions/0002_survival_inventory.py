"""Phase 3 : jauges de survie et inventaire des personnages.

Révision : 0002
Parente : 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch:
        batch.add_column(sa.Column("health", sa.Float(), server_default="100", nullable=False))
        batch.add_column(sa.Column("hunger", sa.Float(), server_default="100", nullable=False))
        batch.add_column(sa.Column("thirst", sa.Float(), server_default="100", nullable=False))
        batch.add_column(sa.Column("bleeding", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("inventory", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("characters") as batch:
        batch.drop_column("inventory")
        batch.drop_column("bleeding")
        batch.drop_column("thirst")
        batch.drop_column("hunger")
        batch.drop_column("health")
