"""trubki (orders)

Revision ID: 006_trubki
Revises: 005_noga_city_history
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_trubki"
down_revision: Union[str, None] = "005_noga_city_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRUBKA_STATUS = sa.Enum(
    "zacep",
    "vedut",
    "srez",
    "zabrali",
    "razgruzheno",
    name="trubka_status",
    native_enum=False,
)
TRUBKA_DELIVERY = sa.Enum("zahod", "taxi", name="trubka_delivery", native_enum=False)
CURRENCY = sa.Enum(
    "RUB", "USD", "UZS", "KGS", "KZT", "AZN", "BYN", "MDL", "PRB",
    name="currency",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "trubki",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", TRUBKA_STATUS, nullable=False, server_default="zacep"),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("noga_id", sa.Integer(), nullable=False),
        sa.Column("razgruz_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_currency", CURRENCY, nullable=False, server_default="RUB"),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_address", sa.String(length=500), nullable=False),
        sa.Column("delivery", TRUBKA_DELIVERY, nullable=False, server_default="zahod"),
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
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["noga_id"], ["nogas.id"]),
        sa.ForeignKeyConstraint(["razgruz_id"], ["razgruzy.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trubki_status", "trubki", ["status"])
    op.create_index("ix_trubki_city_id", "trubki", ["city_id"])
    op.create_index("ix_trubki_noga_id", "trubki", ["noga_id"])
    op.create_index("ix_trubki_razgruz_id", "trubki", ["razgruz_id"])


def downgrade() -> None:
    op.drop_index("ix_trubki_razgruz_id", table_name="trubki")
    op.drop_index("ix_trubki_noga_id", table_name="trubki")
    op.drop_index("ix_trubki_city_id", table_name="trubki")
    op.drop_index("ix_trubki_status", table_name="trubki")
    op.drop_table("trubki")
