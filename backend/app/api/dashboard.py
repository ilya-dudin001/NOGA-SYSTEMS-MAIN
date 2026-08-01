from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.permissions import CITIES_READ, DASHBOARD_GLOBAL, has_permission
from app.db import get_session
from app.db.models import City, CityStatus, Noga, Razgruz, User
from app.schemas import CitiesSummaryOut, DashboardSummaryOut, GeographyCityOut
from app.services import geocode as geocode_service
from app.services import trubki as trubki_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def cities_summary(session: AsyncSession) -> CitiesSummaryOut:
    # Дособираем координаты пачками — Nominatim лимитирован, полный прогон на каждом
    # summary не делаем.
    await geocode_service.fill_missing(session, limit=5)

    by_status = await session.execute(
        select(City.status, func.count()).group_by(City.status)
    )
    counts = {status: count for status, count in by_status.all()}
    nogas = await session.scalar(select(func.count()).select_from(Noga)) or 0
    razgruzy = await session.scalar(select(func.count()).select_from(Razgruz)) or 0

    rows = await session.execute(select(City).order_by(City.name.asc()))
    geography = [
        GeographyCityOut(
            id=city.id,
            name=city.name,
            status=city.status,
            lat=city.lat,
            lon=city.lon,
        )
        for city in rows.scalars().all()
    ]

    await session.commit()

    return CitiesSummaryOut(
        total=sum(counts.values()),
        working=counts.get(CityStatus.working, 0),
        paused=counts.get(CityStatus.paused, 0),
        stopped=counts.get(CityStatus.stopped, 0),
        nogas=nogas,
        razgruzy=razgruzy,
        geography=geography,
    )


@router.get("/summary", response_model=DashboardSummaryOut)
async def dashboard_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryOut:
    """Сводка для дашборда. Оборот считать пока не из чего — трубки суммы не подтверждают,
    поэтому денежные поля нули, а живыми приходят блоки `cities` и `trubki`."""
    scope = "global" if has_permission(user.role, DASHBOARD_GLOBAL) else "own"
    cities = (
        await cities_summary(session)
        if has_permission(user.role, CITIES_READ)
        else CitiesSummaryOut()
    )
    trubki = await trubki_service.summary(session)
    return DashboardSummaryOut(scope=scope, cities=cities, trubki=trubki)
