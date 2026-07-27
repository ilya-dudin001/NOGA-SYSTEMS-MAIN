"""noga personal data, optional city, files

Revision ID: 004_noga_personal
Revises: 003_city_status_razgruzy
Create Date: 2026-07-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_noga_personal"
down_revision: Union[str, None] = "003_city_status_razgruzy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOGA_FILE_KIND = sa.Enum(
    "passport", "passport_selfie", "face_video", name="noga_file_kind", native_enum=False
)


def upgrade() -> None:
    with op.batch_alter_table("nogas") as batch:
        batch.add_column(sa.Column("address", sa.String(length=500), nullable=True))
        batch.add_column(
            sa.Column("phones", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.add_column(
            sa.Column("telegrams", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        # Нога может существовать без города — её прикрепляют из формы города.
        batch.alter_column("city_id", existing_type=sa.Integer(), nullable=True)

    op.create_table(
        "noga_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("noga_id", sa.Integer(), nullable=False),
        sa.Column("kind", NOGA_FILE_KIND, nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["noga_id"], ["nogas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_noga_files_noga_id", "noga_files", ["noga_id"])


def downgrade() -> None:
    op.drop_index("ix_noga_files_noga_id", table_name="noga_files")
    op.drop_table("noga_files")

    # Город снова обязателен, поэтому неприкреплённые ноги теряются.
    op.execute("DELETE FROM nogas WHERE city_id IS NULL")

    with op.batch_alter_table("nogas") as batch:
        batch.alter_column("city_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("telegrams")
        batch.drop_column("phones")
        batch.drop_column("address")
