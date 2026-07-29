from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
sqlite_connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if "sqlite" in settings.database_url
    else {}
)
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=sqlite_connect_args,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
