"""new trubka lifecycle, files and event history

Revision ID: 008_trubka_lifecycle
Revises: 007_chat
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_trubka_lifecycle"
down_revision: Union[str, None] = "007_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUS = sa.Enum(
    "zacep",
    "vedut",
    "srez",
    "zabrali",
    "razgruzheno",
    name="trubka_status",
    native_enum=False,
)
NEW_STATUS = sa.Enum(
    "zacep",
    "zabrali",
    "vyplacheno",
    "srez",
    "razgruzhaetsya",
    name="trubka_status",
    native_enum=False,
)
TRUBKA_DELIVERY = sa.Enum(
    "zahod", "taxi", name="trubka_delivery", native_enum=False
)
TRUBKA_FILE_KIND = sa.Enum(
    "money_photo",
    "receipt_photo",
    name="trubka_file_kind",
    native_enum=False,
)


def upgrade() -> None:
    op.execute("UPDATE trubki SET status = 'zacep' WHERE status = 'vedut'")
    op.execute(
        "UPDATE trubki SET status = 'vyplacheno' WHERE status = 'razgruzheno'"
    )

    with op.batch_alter_table("trubki", recreate="always") as batch:
        batch.alter_column(
            "status",
            existing_type=OLD_STATUS,
            type_=NEW_STATUS,
            existing_nullable=False,
            existing_server_default="zacep",
        )
        batch.alter_column(
            "customer_name",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch.alter_column(
            "customer_address",
            existing_type=sa.String(length=500),
            nullable=True,
        )
        batch.alter_column(
            "delivery",
            existing_type=TRUBKA_DELIVERY,
            nullable=True,
            server_default=None,
        )
        batch.add_column(
            sa.Column("recalculation_amount", sa.BigInteger(), nullable=True)
        )
        batch.add_column(
            sa.Column("usdt_received", sa.Numeric(20, 8), nullable=True)
        )
        batch.add_column(
            sa.Column("report_sent_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "trubka_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trubka_id", sa.Integer(), nullable=False),
        sa.Column("kind", TRUBKA_FILE_KIND, nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trubka_id"], ["trubki.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trubka_id", "kind", name="uq_trubka_file_kind"
        ),
    )
    op.create_index("ix_trubka_files_trubka_id", "trubka_files", ["trubka_id"])

    op.create_table(
        "trubka_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trubka_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trubka_id"], ["trubki.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trubka_events_trubka_id", "trubka_events", ["trubka_id"])
    op.create_index("ix_trubka_events_action", "trubka_events", ["action"])
    op.create_index(
        "ix_trubka_events_trubka_id_id",
        "trubka_events",
        ["trubka_id", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trubka_events_trubka_id_id", table_name="trubka_events"
    )
    op.drop_index("ix_trubka_events_action", table_name="trubka_events")
    op.drop_index("ix_trubka_events_trubka_id", table_name="trubka_events")
    op.drop_table("trubka_events")
    op.drop_index("ix_trubka_files_trubka_id", table_name="trubka_files")
    op.drop_table("trubka_files")

    op.execute(
        "UPDATE trubki SET status = 'razgruzheno' WHERE status = 'vyplacheno'"
    )
    op.execute(
        "UPDATE trubki SET status = 'vedut' WHERE status = 'razgruzhaetsya'"
    )
    op.execute("UPDATE trubki SET customer_name = '' WHERE customer_name IS NULL")
    op.execute("UPDATE trubki SET customer_address = '' WHERE customer_address IS NULL")
    op.execute("UPDATE trubki SET delivery = 'zahod' WHERE delivery IS NULL")
    with op.batch_alter_table("trubki", recreate="always") as batch:
        batch.drop_column("report_sent_at")
        batch.drop_column("usdt_received")
        batch.drop_column("recalculation_amount")
        batch.alter_column(
            "delivery",
            existing_type=TRUBKA_DELIVERY,
            nullable=False,
            server_default="zahod",
        )
        batch.alter_column(
            "customer_address",
            existing_type=sa.String(length=500),
            nullable=False,
        )
        batch.alter_column(
            "customer_name",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch.alter_column(
            "status",
            existing_type=NEW_STATUS,
            type_=OLD_STATUS,
            existing_nullable=False,
            existing_server_default="zacep",
        )
