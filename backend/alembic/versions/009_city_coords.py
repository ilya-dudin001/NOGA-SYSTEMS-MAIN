"""city lat/lon for geography widget

Revision ID: 009_city_coords
Revises: 008_trubka_lifecycle
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_city_coords"
down_revision: Union[str, None] = "008_trubka_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cities", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("cities", sa.Column("lon", sa.Float(), nullable=True))
    op.add_column(
        "cities",
        sa.Column(
            "geocode_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("cities", "geocode_failed")
    op.drop_column("cities", "lon")
    op.drop_column("cities", "lat")
