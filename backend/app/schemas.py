from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import UserRole, UserStatus


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


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool


class CityCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class CityUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    is_active: Optional[bool] = None


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


class ErrorOut(BaseModel):
    code: str
    message: str
