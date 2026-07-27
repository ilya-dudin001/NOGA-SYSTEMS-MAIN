import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
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
