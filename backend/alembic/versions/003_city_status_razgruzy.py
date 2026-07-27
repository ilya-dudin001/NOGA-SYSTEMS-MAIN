"""city status, min amount, razgruzy

Revision ID: 003_city_status_razgruzy
Revises: 002_cities_nogas
Create Date: 2026-07-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_city_status_razgruzy"
down_revision: Union[str, None] = "002_cities_nogas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CITY_STATUS = sa.Enum(
    "working", "paused", "stopped", name="city_status", native_enum=False
)
CURRENCY = sa.Enum(
    "RUB", "USD", "UZS", "KGS", "KZT", "AZN", "BYN", "MDL", "PRB",
    name="currency",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "razgruzy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "commission_percent", sa.Numeric(5, 2), nullable=False, server_default="0"
        ),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "city_razgruzy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("razgruz_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["razgruz_id"], ["razgruzy.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city_id", "razgruz_id", name="uq_city_razgruz"),
    )
    op.create_index("ix_city_razgruzy_city_id", "city_razgruzy", ["city_id"])
    op.create_index("ix_city_razgruzy_razgruz_id", "city_razgruzy", ["razgruz_id"])

    with op.batch_alter_table("cities") as batch:
        batch.add_column(
            sa.Column("status", CITY_STATUS, nullable=False, server_default="working")
        )
        batch.add_column(sa.Column("min_amount", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("min_amount_currency", CURRENCY, nullable=True))

    # Выключенные города переезжают в «стоп полностью», остальные — «в работе».
    op.execute("UPDATE cities SET status = 'stopped' WHERE is_active = 0")

    with op.batch_alter_table("cities") as batch:
        batch.drop_column("is_active")


def downgrade() -> None:
    with op.batch_alter_table("cities") as batch:
        batch.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    op.execute("UPDATE cities SET is_active = 0 WHERE status != 'working'")

    with op.batch_alter_table("cities") as batch:
        batch.drop_column("min_amount_currency")
        batch.drop_column("min_amount")
        batch.drop_column("status")

    op.drop_index("ix_city_razgruzy_razgruz_id", table_name="city_razgruzy")
    op.drop_index("ix_city_razgruzy_city_id", table_name="city_razgruzy")
    op.drop_table("city_razgruzy")
    op.drop_table("razgruzy")
