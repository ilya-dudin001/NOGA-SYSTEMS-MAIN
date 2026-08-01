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
    chat_enabled: bool = Field(default=True, alias="CHAT_ENABLED")
    chat_message_max_chars: int = Field(
        default=4000, ge=1, le=50000, alias="CHAT_MESSAGE_MAX_CHARS"
    )
    chat_files_max_count: int = Field(
        default=10, ge=1, le=50, alias="CHAT_FILES_MAX_COUNT"
    )
    chat_upload_max_total_mb: int = Field(
        default=100, ge=1, le=1024, alias="CHAT_UPLOAD_MAX_TOTAL_MB"
    )
    chat_sse_heartbeat_seconds: int = Field(
        default=15, ge=5, le=300, alias="CHAT_SSE_HEARTBEAT_SECONDS"
    )
    chat_sse_revalidate_seconds: int = Field(
        default=60, ge=10, le=3600, alias="CHAT_SSE_REVALIDATE_SECONDS"
    )
    chat_sse_queue_size: int = Field(
        default=100, ge=10, le=10000, alias="CHAT_SSE_QUEUE_SIZE"
    )
    chat_event_retention_days: int = Field(
        default=7, ge=1, le=365, alias="CHAT_EVENT_RETENTION_DAYS"
    )
    chat_telegram_notifications_enabled: bool = Field(
        default=True, alias="CHAT_TELEGRAM_NOTIFICATIONS_ENABLED"
    )
    chat_notify_poll_seconds: int = Field(
        default=2, ge=1, le=300, alias="CHAT_NOTIFY_POLL_SECONDS"
    )
    chat_notify_max_attempts: int = Field(
        default=8, ge=1, le=20, alias="CHAT_NOTIFY_MAX_ATTEMPTS"
    )
    chat_rate_messages_per_minute: int = Field(
        default=30, ge=1, le=1000, alias="CHAT_RATE_MESSAGES_PER_MINUTE"
    )
    chat_rate_uploads_per_10_minutes: int = Field(
        default=5, ge=1, le=100, alias="CHAT_RATE_UPLOADS_PER_10_MINUTES"
    )
    chat_rate_directs_per_minute: int = Field(
        default=20, ge=1, le=1000, alias="CHAT_RATE_DIRECTS_PER_MINUTE"
    )
    chat_sse_max_streams_per_user: int = Field(
        default=3, ge=1, le=20, alias="CHAT_SSE_MAX_STREAMS_PER_USER"
    )

    @field_validator(
        "bot_polling_enabled",
        "dev_auth_enabled",
        "chat_enabled",
        "chat_telegram_notifications_enabled",
        mode="before",
    )
    @classmethod
    def parse_bool(cls, v):  # noqa: ANN001
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

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
