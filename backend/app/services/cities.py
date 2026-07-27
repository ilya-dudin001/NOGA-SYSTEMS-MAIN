from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import City, User


def normalize(name: str) -> str:
    return " ".join(name.split())


async def find_by_name(session: AsyncSession, name: str) -> Optional[City]:
    """Case-insensitive lookup done in Python: SQLite's lower() is ASCII-only."""
    wanted = normalize(name).lower()
    result = await session.execute(select(City))
    for city in result.scalars().all():
        if city.name.lower() == wanted:
            return city
    return None


async def get_or_create(session: AsyncSession, name: str, actor: User) -> City:
    existing = await find_by_name(session, name)
    if existing is not None:
        return existing
    city = City(name=normalize(name), created_by_id=actor.id)
    session.add(city)
    await session.flush()
    return city
