from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    owner_telegram_ids: str = Field(default="", alias="OWNER_TELEGRAM_IDS")
    webapp_url: str = Field(
        default="https://ilya-dudin001.github.io/NOGA-SYSTEMS-MAIN/",
        alias="WEBAPP_URL",
    )
    cors_origins: str = Field(
        default="https://ilya-dudin001.github.io,http://localhost:5500,http://127.0.0.1:5500",
        alias="CORS_ORIGINS",
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/noga.db",
        alias="DATABASE_URL",
    )
    # Паспорта и видео ног лежат на диске рядом с базой, в git не попадают.
    uploads_dir: str = Field(default="./data/uploads", alias="UPLOADS_DIR")
    jwt_expire_hours: int = Field(default=12, alias="JWT_EXPIRE_HOURS")
    initdata_max_age_seconds: int = Field(default=86400, alias="INITDATA_MAX_AGE_SECONDS")
    dev_auth_enabled: bool = Field(default=False, alias="DEV_AUTH_ENABLED")
    dev_auth_secret: str = Field(default="dev-only-secret", alias="DEV_AUTH_SECRET")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    bot_polling_enabled: bool = Field(default=True, alias="BOT_POLLING_ENABLED")

    @field_validator("bot_polling_enabled", mode="before")
    @classmethod
    def parse_bot_enabled(cls, v):  # noqa: ANN001
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return bool(v)

    @property
    def owner_ids(self) -> List[int]:
        if not self.owner_telegram_ids.strip():
            return []
        result: List[int] = []
        for part in self.owner_telegram_ids.split(","):
            part = part.strip()
            if part:
                result.append(int(part))
        return result

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("dev_auth_enabled", mode="before")
    @classmethod
    def parse_bool(cls, v):  # noqa: ANN001
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return bool(v)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
