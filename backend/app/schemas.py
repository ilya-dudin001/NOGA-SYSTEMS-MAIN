from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import CityStatus, Currency, UserRole, UserStatus


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


class MeOut(UserOut):
    permissions: list[str]
    role_label: str


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


class CityUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    status: Optional[CityStatus] = None
    min_amount: Optional[int] = Field(default=None, ge=0)
    min_amount_currency: Optional[Currency] = None
    razgruz_ids: Optional[list[int]] = None


class NogaOut(BaseModel):
    id: int
    name: str
    city_id: int
    city_name: str
    is_test: bool
    is_active: bool
    created_at: datetime


class NogaCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    city_id: Optional[int] = None
    city_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    is_test: bool = False


class NogaUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    city_id: Optional[int] = None
    is_test: Optional[bool] = None
    is_active: Optional[bool] = None


class CitiesSummaryOut(BaseModel):
    total: int = 0
    working: int = 0
    paused: int = 0
    stopped: int = 0
    nogas: int = 0
    razgruzy: int = 0


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


class ErrorOut(BaseModel):
    code: str
    message: str
