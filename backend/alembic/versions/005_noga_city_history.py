"""noga city history snapshots

Revision ID: 005_noga_city_history
Revises: 004_noga_personal
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_noga_city_history"
down_revision: Union[str, None] = "004_noga_personal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("nogas") as batch:
        batch.add_column(sa.Column("initial_city_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("last_city_name", sa.String(length=120), nullable=True))

    # У уже заведённых ног история равна текущему городу: другого мы не знаем.
    op.execute(
        """
        UPDATE nogas
           SET initial_city_name = (SELECT name FROM cities WHERE cities.id = nogas.city_id),
               last_city_name    = (SELECT name FROM cities WHERE cities.id = nogas.city_id)
         WHERE city_id IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("nogas") as batch:
        batch.drop_column("last_city_name")
        batch.drop_column("initial_city_name")
