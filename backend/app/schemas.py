from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import (
    ChatRoomKind,
    CityStatus,
    Currency,
    NogaFileKind,
    TrubkaDelivery,
    TrubkaFileKind,
    TrubkaStatus,
    UserRole,
    UserStatus,
)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    display_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    last_seen_at: Optional[datetime] = None


class FeaturesOut(BaseModel):
    chat: bool = False


class MeOut(UserOut):
    permissions: list[str]
    role_label: str
    features: FeaturesOut = Field(default_factory=FeaturesOut)


class AuthTelegramIn(BaseModel):
    init_data: str = Field(..., alias="initData")

    model_config = ConfigDict(populate_by_name=True)


class AuthDevIn(BaseModel):
    telegram_id: int
    secret: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class UserCreateIn(BaseModel):
    telegram_id: int
    role: UserRole = UserRole.noga
    display_name: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None


class MeUpdateIn(BaseModel):
    display_name: str


class UserUpdateIn(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None


class RazgruzOut(BaseModel):
    id: int
    name: str
    commission_percent: float
    contact: Optional[str] = None
    is_active: bool
    created_at: datetime
    created_by_name: Optional[str] = None
    cities_count: int = 0
    # Заказов ещё нет в схеме БД — до появления операций всегда 0.
    completed_orders: int = 0
    can_manage: bool = False
    # Свои разгрузы подставляются в форму нового города, поэтому «мой» и «могу
    # править» — разные флаги: у owner can_manage истинно и для чужих.
    created_by_me: bool = False


class RazgruzCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    commission_percent: float = Field(default=0, ge=0, le=100)
    contact: Optional[str] = Field(default=None, max_length=255)


class RazgruzUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    commission_percent: Optional[float] = Field(default=None, ge=0, le=100)
    contact: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class NogaBriefOut(BaseModel):
    id: int
    name: str
    is_test: bool
    is_active: bool
    created_at: datetime
    created_by_name: Optional[str] = None
    # Своя ли это нога для смотрящего: админ чужую только читает.
    can_manage: bool = False


class CityOut(BaseModel):
    id: int
    name: str
    status: CityStatus
    min_amount: Optional[int] = None
    min_amount_currency: Optional[Currency] = None
    nogas_count: int = 0
    razgruzy: list[RazgruzOut] = Field(default_factory=list)
    created_at: datetime
    created_by_name: Optional[str] = None
    can_manage: bool = False


class CityDetailOut(CityOut):
    nogas: list[NogaBriefOut] = Field(default_factory=list)
    # Последние 5 заказов по городу; операций ещё нет — пока всегда пусто.
    recent_orders: list[dict[str, Any]] = Field(default_factory=list)


class CityCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    status: CityStatus = CityStatus.working
    min_amount: Optional[int] = Field(default=None, ge=0)
    min_amount_currency: Optional[Currency] = None
    razgruz_ids: Optional[list[int]] = None
    # Ноги, которые должны работать в этом городе; остальные от него открепляются.
    noga_ids: Optional[list[int]] = None


class CityUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    status: Optional[CityStatus] = None
    min_amount: Optional[int] = Field(default=None, ge=0)
    min_amount_currency: Optional[Currency] = None
    razgruz_ids: Optional[list[int]] = None
    noga_ids: Optional[list[int]] = None


class NogaOut(BaseModel):
    id: int
    name: str
    city_id: Optional[int] = None
    city_name: Optional[str] = None
    # История привязки: остаётся, даже если город удалили.
    initial_city_name: Optional[str] = None
    last_city_name: Optional[str] = None
    is_test: bool
    is_active: bool
    created_at: datetime
    created_by_name: Optional[str] = None
    can_manage: bool = False


class NogaFileOut(BaseModel):
    id: int
    kind: NogaFileKind
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    uploaded_by_name: Optional[str] = None


class NogaDetailOut(NogaOut):
    """Личные данные отдаём только с правом nogas:personal — иначе поля пустые."""

    address: Optional[str] = None
    phones: list[str] = Field(default_factory=list)
    telegrams: list[str] = Field(default_factory=list)
    files: list[NogaFileOut] = Field(default_factory=list)
    has_personal_access: bool = False


class NogaCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    city_id: Optional[int] = None
    city_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    is_test: bool = False


class NogaUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    # Явный null открепляет ногу от города; отсутствие поля город не меняет.
    city_id: Optional[int] = None
    # Новый город прямо из формы ноги; если указан, city_id игнорируется.
    city_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    is_test: Optional[bool] = None
    is_active: Optional[bool] = None
    address: Optional[str] = Field(default=None, max_length=500)
    phones: Optional[list[str]] = Field(default=None, max_length=20)
    telegrams: Optional[list[str]] = Field(default=None, max_length=20)


MANUAL_TRUBKA_STATUSES = {
    TrubkaStatus.zacep,
    TrubkaStatus.zabrali,
    TrubkaStatus.vyplacheno,
    TrubkaStatus.srez,
}


def validate_manual_trubka_status(value: Optional[TrubkaStatus]) -> Optional[TrubkaStatus]:
    if value is not None and value not in MANUAL_TRUBKA_STATUSES:
        raise ValueError("Статус «Разгружается» выставляется автоматически")
    return value


class TrubkaFileOut(BaseModel):
    id: int
    kind: TrubkaFileKind
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    uploaded_by_name: Optional[str] = None


class TrubkaEventOut(BaseModel):
    id: int
    actor_name: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TrubkaOut(BaseModel):
    id: int
    status: TrubkaStatus
    city_id: int
    city_name: str
    amount: int
    amount_currency: Currency
    noga_id: int
    noga_name: str
    # «Чья нога» — тот, кто её завёл; берётся у ноги, отдельным полем не хранится.
    noga_owner_name: Optional[str] = None
    razgruz_id: Optional[int] = None
    razgruz_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    delivery: Optional[TrubkaDelivery] = None
    recalculation_amount: Optional[int] = None
    noga_payout: Optional[int] = None
    remainder: Optional[int] = None
    usdt_received: Optional[Decimal] = None
    report_sent_at: Optional[datetime] = None
    files: list[TrubkaFileOut] = Field(default_factory=list)
    history: list[TrubkaEventOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None
    can_manage: bool = False


class TrubkaCreateIn(BaseModel):
    status: TrubkaStatus = TrubkaStatus.zacep
    city_id: int
    noga_id: int
    razgruz_id: Optional[int] = None
    amount: int = Field(..., ge=0)
    amount_currency: Currency = Currency.RUB
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    customer_address: Optional[str] = Field(default=None, min_length=1, max_length=500)
    delivery: Optional[TrubkaDelivery] = None

    _manual_status = field_validator("status")(validate_manual_trubka_status)


class TrubkaUpdateIn(BaseModel):
    status: Optional[TrubkaStatus] = None
    city_id: Optional[int] = None
    noga_id: Optional[int] = None
    # Явный null снимает разгруз; отсутствие поля его не трогает.
    razgruz_id: Optional[int] = None
    amount: Optional[int] = Field(default=None, ge=0)
    amount_currency: Optional[Currency] = None
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    customer_address: Optional[str] = Field(default=None, min_length=1, max_length=500)
    delivery: Optional[TrubkaDelivery] = None

    _manual_status = field_validator("status")(validate_manual_trubka_status)


class TrubkaRecalculationIn(BaseModel):
    amount: int = Field(..., ge=0)


class TrubkaUsdtIn(BaseModel):
    amount: Decimal = Field(..., ge=0, max_digits=20, decimal_places=8)


class TrubkiSummaryOut(BaseModel):
    total: int = 0
    zacep: int = 0
    zabrali: int = 0
    vyplacheno: int = 0
    srez: int = 0
    razgruzhaetsya: int = 0


class TrubkiPageOut(BaseModel):
    """Список трубок с total — для пагинации в статистике."""

    items: list[TrubkaOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class GeographyCityOut(BaseModel):
    """Точка на карте дашборда: статус и координаты (если геокодер нашёл)."""

    id: int
    name: str
    status: CityStatus
    lat: Optional[float] = None
    lon: Optional[float] = None


class CitiesSummaryOut(BaseModel):
    total: int = 0
    working: int = 0
    paused: int = 0
    stopped: int = 0
    nogas: int = 0
    razgruzy: int = 0
    geography: list[GeographyCityOut] = Field(default_factory=list)


class DashboardSummaryOut(BaseModel):
    turnover_rub: int = 0
    turnover_usd: int = 0
    created: int = 0
    in_progress: int = 0
    entries: int = 0
    paid: int = 0
    remaining: int = 0
    total_operations: int = 0
    recent_operations: list[dict[str, Any]] = Field(default_factory=list)
    scope: str = "global"  # global | own
    cities: CitiesSummaryOut = Field(default_factory=CitiesSummaryOut)
    trubki: TrubkiSummaryOut = Field(default_factory=TrubkiSummaryOut)


class ErrorOut(BaseModel):
    code: str
    message: str


# --- Chat ---


class ChatPeerBriefOut(BaseModel):
    id: int
    display_name: str
    username: Optional[str] = None
    role: UserRole


class ChatLastMessageOut(BaseModel):
    id: int
    author_name: str
    preview: str
    has_attachments: bool = False
    created_at: datetime


class ChatRoomOut(BaseModel):
    id: int
    kind: ChatRoomKind
    slug: Optional[str] = None
    title: Optional[str] = None
    peer: Optional[ChatPeerBriefOut] = None
    unread_count: int = 0
    unread_mentions: int = 0
    last_message: Optional[ChatLastMessageOut] = None


class ChatRoomsListOut(BaseModel):
    latest_event_id: Optional[int] = None
    total_unread: int = 0
    total_unread_mentions: int = 0
    rooms: list[ChatRoomOut] = Field(default_factory=list)


class ChatPeerOut(BaseModel):
    id: int
    display_name: str
    username: Optional[str] = None
    role: UserRole
    role_label: str
    room_id: Optional[int] = None


class ChatDirectCreateIn(BaseModel):
    peer_user_id: int = Field(..., gt=0)


class ChatAuthorOut(BaseModel):
    id: Optional[int] = None
    display_name: str
    is_current_user: bool = False


class ChatReplyOut(BaseModel):
    id: int
    author_name: str
    preview: str
    is_deleted: bool = False


class ChatAttachmentOut(BaseModel):
    id: int
    original_name: str
    content_type: str
    size_bytes: int


class ChatMessageOut(BaseModel):
    id: int
    room_id: int
    author: ChatAuthorOut
    content: list[dict[str, Any]] = Field(default_factory=list)
    reply: Optional[ChatReplyOut] = None
    attachments: list[ChatAttachmentOut] = Field(default_factory=list)
    is_deleted: bool = False
    can_delete: bool = False
    created_at: datetime


class ChatReadUpdateIn(BaseModel):
    last_read_message_id: int = Field(..., gt=0)


class ChatReadOut(BaseModel):
    room_id: int
    last_read_message_id: Optional[int] = None
    unread_count: int = 0
    unread_mentions: int = 0


class ChatMentionOut(BaseModel):
    id: int
    room_id: int
    room_title: Optional[str] = None
    message_id: int
    author_name: str
    preview: str
    created_at: datetime
    read_at: Optional[datetime] = None


class ChatMentionReadOut(BaseModel):
    id: int
    room_id: int
    message_id: int
    read_at: Optional[datetime] = None
