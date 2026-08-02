"""places cache tables

Revision ID: 010_places_cache
Revises: 009_city_coords
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_places_cache"
down_revision: Union[str, None] = "009_city_coords"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "place_address_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_norm", sa.String(length=160), nullable=False),
        sa.Column("street_norm", sa.String(length=200), nullable=False),
        sa.Column("house_norm", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column(
            "queried_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city_norm",
            "street_norm",
            "house_norm",
            name="uq_place_address_norm",
        ),
    )
    op.create_table(
        "place_object_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("bank", sa.String(length=160), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("street_key", sa.String(length=64), nullable=False),
        sa.Column("geohash", sa.String(length=16), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_place_object_source_ext"),
    )
    op.create_index(
        "ix_place_object_street_key", "place_object_cache", ["street_key"], unique=False
    )
    op.create_index(
        "ix_place_object_geohash", "place_object_cache", ["geohash"], unique=False
    )
    op.create_index(
        "ix_place_object_fetched_at",
        "place_object_cache",
        ["fetched_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_place_object_fetched_at", table_name="place_object_cache")
    op.drop_index("ix_place_object_geohash", table_name="place_object_cache")
    op.drop_index("ix_place_object_street_key", table_name="place_object_cache")
    op.drop_table("place_object_cache")
    op.drop_table("place_address_cache")
