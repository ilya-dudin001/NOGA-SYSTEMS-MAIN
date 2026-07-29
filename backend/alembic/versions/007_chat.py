"""internal chat foundation

Revision ID: 007_chat
Revises: 006_trubki
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_chat"
down_revision: Union[str, None] = "006_trubki"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHAT_ROOM_KIND = sa.Enum(
    "system", "direct", name="chat_room_kind", native_enum=False
)
CHAT_TELEGRAM_STATUS = sa.Enum(
    "pending",
    "sending",
    "sent",
    "retry",
    "failed",
    "cancelled",
    name="chat_telegram_status",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", CHAT_ROOM_KIND, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("direct_key", sa.String(length=64), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("direct_key", name="uq_chat_rooms_direct_key"),
        sa.UniqueConstraint("slug", name="uq_chat_rooms_slug"),
    )
    op.create_index("ix_chat_rooms_kind", "chat_rooms", ["kind"])

    op.create_table(
        "chat_room_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["chat_rooms.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id", "user_id", name="uq_chat_room_member"
        ),
    )
    op.create_index(
        "ix_chat_room_members_room_id", "chat_room_members", ["room_id"]
    )
    op.create_index(
        "ix_chat_room_members_user_id", "chat_room_members", ["user_id"]
    )
    op.create_index(
        "ix_chat_room_members_user_room",
        "chat_room_members",
        ["user_id", "room_id"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=4000), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("reply_to_id", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"], ["chat_messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["chat_rooms.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_room_id", "chat_messages", ["room_id"])
    op.create_index(
        "ix_chat_messages_author_id", "chat_messages", ["author_id"]
    )
    op.create_index(
        "ix_chat_messages_reply_to_id", "chat_messages", ["reply_to_id"]
    )
    op.create_index(
        "ix_chat_messages_room_id_id", "chat_messages", ["room_id", "id"]
    )

    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
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
            ["message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stored_path", name="uq_chat_attachments_stored_path"
        ),
    )
    op.create_index(
        "ix_chat_attachments_message_id", "chat_attachments", ["message_id"]
    )

    op.create_table(
        "chat_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=255), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "telegram_status",
            CHAT_TELEGRAM_STATUS,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "telegram_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "telegram_next_retry_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "telegram_locked_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "telegram_sent_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("telegram_last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id", "user_id", name="uq_chat_mention_message_user"
        ),
    )
    op.create_index(
        "ix_chat_mentions_message_id", "chat_mentions", ["message_id"]
    )
    op.create_index("ix_chat_mentions_user_id", "chat_mentions", ["user_id"])
    op.create_index("ix_chat_mentions_read_at", "chat_mentions", ["read_at"])
    op.create_index(
        "ix_chat_mentions_telegram_next_retry_at",
        "chat_mentions",
        ["telegram_next_retry_at"],
    )
    op.create_index(
        "ix_chat_mentions_user_read",
        "chat_mentions",
        ["user_id", "read_at"],
    )
    op.create_index(
        "ix_chat_mentions_telegram_due",
        "chat_mentions",
        ["telegram_status", "telegram_next_retry_at"],
    )

    op.create_table(
        "chat_reads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_read_message_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["last_read_message_id"],
            ["chat_messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["chat_rooms.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id", "user_id", name="uq_chat_read_room_user"
        ),
    )
    op.create_index("ix_chat_reads_room_id", "chat_reads", ["room_id"])
    op.create_index("ix_chat_reads_user_id", "chat_reads", ["user_id"])
    op.create_index(
        "ix_chat_reads_user_room", "chat_reads", ["user_id", "room_id"]
    )

    op.create_table(
        "chat_events",
        # SQLite autoincrement requires exactly INTEGER PRIMARY KEY.
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["chat_rooms.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_events_room_id", "chat_events", ["room_id"])
    op.create_index(
        "ix_chat_events_target_user_id", "chat_events", ["target_user_id"]
    )
    op.create_index("ix_chat_events_type", "chat_events", ["type"])
    op.create_index(
        "ix_chat_events_created_at", "chat_events", ["created_at"]
    )
    op.create_index(
        "ix_chat_events_room_id_id", "chat_events", ["room_id", "id"]
    )
    op.create_index(
        "ix_chat_events_target_user_id_id",
        "chat_events",
        ["target_user_id", "id"],
    )

    rooms = sa.table(
        "chat_rooms",
        sa.column("kind", CHAT_ROOM_KIND),
        sa.column("slug", sa.String()),
        sa.column("title", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        rooms,
        [
            {
                "kind": "system",
                "slug": "general",
                "title": "Общий",
                "is_active": True,
                "sort_order": 10,
            },
            {
                "kind": "system",
                "slug": "team",
                "title": "Команда",
                "is_active": True,
                "sort_order": 20,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_events_target_user_id_id", table_name="chat_events")
    op.drop_index("ix_chat_events_room_id_id", table_name="chat_events")
    op.drop_index("ix_chat_events_created_at", table_name="chat_events")
    op.drop_index("ix_chat_events_type", table_name="chat_events")
    op.drop_index("ix_chat_events_target_user_id", table_name="chat_events")
    op.drop_index("ix_chat_events_room_id", table_name="chat_events")
    op.drop_table("chat_events")

    op.drop_index("ix_chat_reads_user_room", table_name="chat_reads")
    op.drop_index("ix_chat_reads_user_id", table_name="chat_reads")
    op.drop_index("ix_chat_reads_room_id", table_name="chat_reads")
    op.drop_table("chat_reads")

    op.drop_index("ix_chat_mentions_telegram_due", table_name="chat_mentions")
    op.drop_index("ix_chat_mentions_user_read", table_name="chat_mentions")
    op.drop_index(
        "ix_chat_mentions_telegram_next_retry_at", table_name="chat_mentions"
    )
    op.drop_index("ix_chat_mentions_read_at", table_name="chat_mentions")
    op.drop_index("ix_chat_mentions_user_id", table_name="chat_mentions")
    op.drop_index("ix_chat_mentions_message_id", table_name="chat_mentions")
    op.drop_table("chat_mentions")

    op.drop_index(
        "ix_chat_attachments_message_id", table_name="chat_attachments"
    )
    op.drop_table("chat_attachments")

    op.drop_index("ix_chat_messages_room_id_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_reply_to_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_author_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(
        "ix_chat_room_members_user_room", table_name="chat_room_members"
    )
    op.drop_index(
        "ix_chat_room_members_user_id", table_name="chat_room_members"
    )
    op.drop_index(
        "ix_chat_room_members_room_id", table_name="chat_room_members"
    )
    op.drop_table("chat_room_members")

    op.drop_index("ix_chat_rooms_kind", table_name="chat_rooms")
    op.drop_table("chat_rooms")
