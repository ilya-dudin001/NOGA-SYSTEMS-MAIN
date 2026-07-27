from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CityRazgruz, Razgruz
from app.schemas import RazgruzOut

LOAD_OPTIONS = (selectinload(Razgruz.created_by),)


def normalize(name: str) -> str:
    return " ".join(name.split())


async def find_by_name(
    session: AsyncSession, name: str, *, exclude_id: Optional[int] = None
) -> Optional[Razgruz]:
    """Case-insensitive lookup done in Python: SQLite's lower() is ASCII-only."""
    wanted = normalize(name).lower()
    result = await session.execute(select(Razgruz))
    for razgruz in result.scalars().all():
        if razgruz.name.lower() == wanted and razgruz.id != exclude_id:
            return razgruz
    return None


async def city_counts(session: AsyncSession) -> dict[int, int]:
    """razgruz_id → сколько городов на нём висит."""
    result = await session.execute(
        select(CityRazgruz.razgruz_id, func.count()).group_by(CityRazgruz.razgruz_id)
    )
    return {razgruz_id: count for razgruz_id, count in result.all()}


async def load(
    session: AsyncSession, razgruz_id: int, *, with_cities: bool = False
) -> Optional[Razgruz]:
    """with_cities обязателен перед удалением: Razgruz.cities объявлена lazy="raise",
    а ORM грузит эту коллекцию, чтобы снять связи в city_razgruzy."""
    options = list(LOAD_OPTIONS)
    if with_cities:
        options.append(selectinload(Razgruz.cities))
    result = await session.execute(
        select(Razgruz)
        .options(*options)
        .where(Razgruz.id == razgruz_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def load_all(
    session: AsyncSession, *, only_active: bool = False
) -> Sequence[Razgruz]:
    query = select(Razgruz).options(*LOAD_OPTIONS)
    if only_active:
        query = query.where(Razgruz.is_active.is_(True))
    result = await session.execute(query.order_by(Razgruz.name.asc()))
    return result.scalars().all()


def to_out(razgruz: Razgruz, *, cities_count: int = 0) -> RazgruzOut:
    return RazgruzOut(
        id=razgruz.id,
        name=razgruz.name,
        commission_percent=float(razgruz.commission_percent),
        contact=razgruz.contact,
        is_active=razgruz.is_active,
        created_at=razgruz.created_at,
        created_by_name=razgruz.created_by.display_name if razgruz.created_by else None,
        cities_count=cities_count,
        completed_orders=0,
    )
