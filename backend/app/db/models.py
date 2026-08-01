import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


class UserRole(str, enum.Enum):
    owner = "owner"
    right_hand = "right_hand"
    admin = "admin"
    noga = "noga"


class UserStatus(str, enum.Enum):
    active = "active"
    blocked = "blocked"


class ChatRoomKind(str, enum.Enum):
    system = "system"
    direct = "direct"


class ChatTelegramStatus(str, enum.Enum):
    pending = "pending"
    sending = "sending"
    sent = "sent"
    retry = "retry"
    failed = "failed"
    cancelled = "cancelled"


class CityStatus(str, enum.Enum):
    """Город работает, стоит временно или снят с работы полностью."""

    working = "working"
    paused = "paused"
    stopped = "stopped"


class NogaFileKind(str, enum.Enum):
    """Что за файл в личных данных ноги."""

    passport = "passport"  # фото паспорта
    passport_selfie = "passport_selfie"  # паспорт вместе с лицом
    face_video = "face_video"  # короткое видео с лицом


class TrubkaStatus(str, enum.Enum):
    """Стадии трубки (заказа) от зацепа до разгруза."""

    zacep = "zacep"  # Зацеп
    vedut = "vedut"  # Ведут
    srez = "srez"  # Срез
    zabrali = "zabrali"  # Забрали
    razgruzheno = "razgruzheno"  # Разгружено


class TrubkaDelivery(str, enum.Enum):
    """Как посылка попадает к ноге."""

    zahod = "zahod"  # нога сама заходит на адрес
    taxi = "taxi"  # заказчик отправляет такси


class Currency(str, enum.Enum):
    RUB = "RUB"  # рубли
    USD = "USD"  # доллары
    UZS = "UZS"  # узбекские сумы
    KGS = "KGS"  # киргизские сомы
    KZT = "KZT"  # казахские тенге
    AZN = "AZN"  # азербайджанские манаты
    BYN = "BYN"  # белорусские рубли
    MDL = "MDL"  # молдавские леи
    PRB = "PRB"  # приднестровские рубли (кода ISO нет, используем неофициальный)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.noga,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=False),
        nullable=False,
        default=UserStatus.active,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional["User"]] = relationship(remote_side=[id], foreign_keys=[created_by_id])


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[ChatRoomKind] = mapped_column(
        Enum(ChatRoomKind, name="chat_room_kind", native_enum=False),
        nullable=False,
        index=True,
    )
    slug: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    direct_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    members: Mapped[list["ChatRoomMember"]] = relationship(
        back_populates="room", lazy="raise", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="room", lazy="raise", cascade="all, delete-orphan"
    )


class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_room_member"),
        Index("ix_chat_room_members_user_room", "user_id", "room_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["ChatRoom"] = relationship(back_populates="members", lazy="raise")
    user: Mapped["User"] = relationship(lazy="raise")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_room_id_id", "room_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(String(4000), nullable=True)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    reply_to_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["ChatRoom"] = relationship(back_populates="messages", lazy="raise")
    author: Mapped[Optional["User"]] = relationship(
        foreign_keys=[author_id], lazy="raise"
    )
    deleted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[deleted_by_id], lazy="raise"
    )
    reply_to: Mapped[Optional["ChatMessage"]] = relationship(
        remote_side=[id], foreign_keys=[reply_to_id], lazy="raise"
    )
    attachments: Mapped[list["ChatAttachment"]] = relationship(
        back_populates="message", lazy="raise", cascade="all, delete-orphan"
    )
    mentions: Mapped[list["ChatMention"]] = relationship(
        back_populates="message", lazy="raise", cascade="all, delete-orphan"
    )


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="attachments", lazy="raise")
    uploaded_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[uploaded_by_id], lazy="raise"
    )


class ChatMention(Base):
    __tablename__ = "chat_mentions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_chat_mention_message_user"),
        Index("ix_chat_mentions_user_read", "user_id", "read_at"),
        Index(
            "ix_chat_mentions_telegram_due",
            "telegram_status",
            "telegram_next_retry_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    telegram_status: Mapped[ChatTelegramStatus] = mapped_column(
        Enum(ChatTelegramStatus, name="chat_telegram_status", native_enum=False),
        nullable=False,
        default=ChatTelegramStatus.pending,
    )
    telegram_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    telegram_next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    telegram_locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telegram_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telegram_last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="mentions", lazy="raise")
    user: Mapped[Optional["User"]] = relationship(lazy="raise")


class ChatRead(Base):
    __tablename__ = "chat_reads"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_read_room_user"),
        Index("ix_chat_reads_user_room", "user_id", "room_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_read_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    room: Mapped["ChatRoom"] = relationship(lazy="raise")
    user: Mapped["User"] = relationship(lazy="raise")
    last_read_message: Mapped[Optional["ChatMessage"]] = relationship(lazy="raise")


class ChatEvent(Base):
    __tablename__ = "chat_events"
    __table_args__ = (
        Index("ix_chat_events_room_id_id", "room_id", "id"),
        Index("ix_chat_events_target_user_id_id", "target_user_id", "id"),
    )

    # SQLite autoincrement requires exactly INTEGER PRIMARY KEY.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    room: Mapped[Optional["ChatRoom"]] = relationship(lazy="raise")
    target_user: Mapped[Optional["User"]] = relationship(lazy="raise")


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[CityStatus] = mapped_column(
        Enum(CityStatus, name="city_status", native_enum=False),
        nullable=False,
        default=CityStatus.working,
    )
    # Порог, с которого город запускается в работу. Валюта произвольная из Currency.
    min_amount: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    min_amount_currency: Mapped[Optional[Currency]] = mapped_column(
        Enum(Currency, name="currency", native_enum=False), nullable=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id], lazy="raise"
    )
    razgruzy: Mapped[list["Razgruz"]] = relationship(
        secondary="city_razgruzy", back_populates="cities", lazy="raise", order_by="Razgruz.name"
    )


class Razgruz(Base):
    """Разгруз — сервис международных переводов: комиссия, статус, привязка к городам."""

    __tablename__ = "razgruzy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    commission_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id], lazy="raise"
    )
    cities: Mapped[list["City"]] = relationship(
        secondary="city_razgruzy", back_populates="razgruzy", lazy="raise", order_by="City.name"
    )


class CityRazgruz(Base):
    """Город работает через несколько разгрузов, разгруз обслуживает несколько городов."""

    __tablename__ = "city_razgruzy"
    __table_args__ = (UniqueConstraint("city_id", "razgruz_id", name="uq_city_razgruz"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    razgruz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("razgruzy.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Noga(Base):
    """Нога — исполнитель, привязанный к городу. Тестовые ноги не идут в реальный оборот."""

    __tablename__ = "nogas"
    __table_args__ = (UniqueConstraint("name", "city_id", name="uq_noga_name_city"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # NULL — нога заведена, но пока не прикреплена ни к одному городу.
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cities.id"), nullable=True, index=True
    )
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Снимки названий городов, а не FK: город могут удалить, а история должна остаться.
    initial_city_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_city_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Списки строк: телефонов и телеграм-контактов у ноги может быть несколько.
    phones: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    telegrams: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    city: Mapped[Optional["City"]] = relationship(lazy="raise")
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id], lazy="raise"
    )
    files: Mapped[list["NogaFile"]] = relationship(
        back_populates="noga",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="NogaFile.created_at",
    )


class NogaFile(Base):
    """Скан паспорта, селфи с паспортом или видео — лежит на диске, в БД только метаданные."""

    __tablename__ = "noga_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    noga_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nogas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[NogaFileKind] = mapped_column(
        Enum(NogaFileKind, name="noga_file_kind", native_enum=False), nullable=False
    )
    # Путь относительно uploads_dir, чтобы каталог можно было переносить.
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    noga: Mapped["Noga"] = relationship(back_populates="files", lazy="raise")
    uploaded_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[uploaded_by_id], lazy="raise"
    )


class Trubka(Base):
    """Трубка (заказ): город, нога, сумма и заказчик на каждой стадии работы."""

    __tablename__ = "trubki"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[TrubkaStatus] = mapped_column(
        Enum(TrubkaStatus, name="trubka_status", native_enum=False),
        nullable=False,
        default=TrubkaStatus.zacep,
        index=True,
    )
    city_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cities.id"), nullable=False, index=True
    )
    noga_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nogas.id"), nullable=False, index=True
    )
    # Через какой сервис ушли деньги — известно не сразу, поэтому необязателен.
    razgruz_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("razgruzy.id"), nullable=True, index=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency", native_enum=False),
        nullable=False,
        default=Currency.RUB,
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_address: Mapped[str] = mapped_column(String(500), nullable=False)
    delivery: Mapped[TrubkaDelivery] = mapped_column(
        Enum(TrubkaDelivery, name="trubka_delivery", native_enum=False),
        nullable=False,
        default=TrubkaDelivery.zahod,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    city: Mapped["City"] = relationship(lazy="raise")
    noga: Mapped["Noga"] = relationship(lazy="raise")
    razgruz: Mapped[Optional["Razgruz"]] = relationship(lazy="raise")
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id], lazy="raise"
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
