from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import City, CityRazgruz, CityStatus, Noga, Razgruz, User
from app.schemas import CityDetailOut, CityOut, NogaBriefOut
from app.services import geocode as geocode_service
from app.services import razgruzy as razgruzy_service

LOAD_OPTIONS = (
    selectinload(City.created_by),
    selectinload(City.razgruzy).selectinload(Razgruz.created_by),
)


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
    await geocode_service.ensure_city_coords(session, city)
    return city


async def load(session: AsyncSession, city_id: int) -> Optional[City]:
    result = await session.execute(
        select(City)
        .options(*LOAD_OPTIONS)
        .where(City.id == city_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def load_all(
    session: AsyncSession,
    *,
    status: Optional[CityStatus] = None,
    owner_id: Optional[int] = None,
    with_nogas_of: Optional[int] = None,
) -> Sequence[City]:
    """owner_id — свои города; with_nogas_of добавляет чужие, где стоят мои ноги."""
    query = select(City).options(*LOAD_OPTIONS)
    if status is not None:
        query = query.where(City.status == status)
    if owner_id is not None:
        mine = City.created_by_id == owner_id
        if with_nogas_of is not None:
            query = query.where(
                or_(
                    mine,
                    City.id.in_(
                        select(Noga.city_id).where(Noga.created_by_id == with_nogas_of)
                    ),
                )
            )
        else:
            query = query.where(mine)
    result = await session.execute(query.order_by(City.name.asc()))
    return result.scalars().all()


async def noga_counts(session: AsyncSession) -> dict[int, int]:
    """city_id → сколько ног в городе."""
    result = await session.execute(
        select(Noga.city_id, func.count()).group_by(Noga.city_id)
    )
    return {city_id: count for city_id, count in result.all()}


async def load_nogas(
    session: AsyncSession, city_id: int, *, manage_owner_id: Optional[int] = None
) -> list[NogaBriefOut]:
    """Все ноги города, включая чужие: счётчик и состав общие для всех админов."""
    result = await session.execute(
        select(Noga)
        .options(selectinload(Noga.created_by))
        .where(Noga.city_id == city_id)
        .order_by(Noga.name.asc())
    )
    return [
        NogaBriefOut(
            id=noga.id,
            name=noga.name,
            is_test=noga.is_test,
            is_active=noga.is_active,
            created_at=noga.created_at,
            created_by_name=noga.created_by.display_name if noga.created_by else None,
            can_manage=manage_owner_id is None or noga.created_by_id == manage_owner_id,
        )
        for noga in result.scalars().all()
    ]


async def replace_razgruzy(
    session: AsyncSession, city_id: int, razgruz_ids: Sequence[int]
) -> None:
    """Пересобирает связи города с разгрузами. Существование id проверяет вызывающий."""
    await session.execute(delete(CityRazgruz).where(CityRazgruz.city_id == city_id))
    for razgruz_id in dict.fromkeys(razgruz_ids):
        session.add(CityRazgruz(city_id=city_id, razgruz_id=razgruz_id))


def to_out(
    city: City,
    *,
    nogas_count: int = 0,
    razgruz_city_counts: Optional[dict[int, int]] = None,
    include_razgruzy: bool = True,
    can_manage: bool = False,
) -> CityOut:
    """include_razgruzy=False для ролей без razgruz:read — иначе комиссии утекут
    всем, у кого есть cities:read (в том числе роли noga)."""
    counts = razgruz_city_counts or {}
    return CityOut(
        id=city.id,
        name=city.name,
        status=city.status,
        min_amount=city.min_amount,
        min_amount_currency=city.min_amount_currency,
        nogas_count=nogas_count,
        razgruzy=[
            razgruzy_service.to_out(r, cities_count=counts.get(r.id, 0))
            for r in city.razgruzy
        ]
        if include_razgruzy
        else [],
        created_at=city.created_at,
        created_by_name=city.created_by.display_name if city.created_by else None,
        can_manage=can_manage,
    )


def to_detail_out(
    city: City,
    *,
    nogas: list[NogaBriefOut],
    nogas_count: Optional[int] = None,
    razgruz_city_counts: Optional[dict[int, int]] = None,
    include_razgruzy: bool = True,
    can_manage: bool = False,
) -> CityDetailOut:
    base = to_out(
        city,
        nogas_count=len(nogas) if nogas_count is None else nogas_count,
        razgruz_city_counts=razgruz_city_counts,
        include_razgruzy=include_razgruzy,
        can_manage=can_manage,
    )
    return CityDetailOut(
        **base.model_dump(),
        nogas=nogas,
        # Таблицы операций ещё нет — до неё последние заказы по городу всегда пусты.
        recent_orders=[],
    )
