from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Noga, Trubka, TrubkaStatus
from app.schemas import TrubkaOut, TrubkiSummaryOut

# «Чья нога» живёт в noga.created_by, поэтому тянем автора ноги вместе с ногой.
LOAD_OPTIONS = (
    selectinload(Trubka.city),
    selectinload(Trubka.noga).selectinload(Noga.created_by),
    selectinload(Trubka.razgruz),
    selectinload(Trubka.created_by),
)


async def load(session: AsyncSession, trubka_id: int) -> Optional[Trubka]:
    result = await session.execute(
        select(Trubka)
        .options(*LOAD_OPTIONS)
        .where(Trubka.id == trubka_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def load_all(
    session: AsyncSession,
    *,
    status: Optional[TrubkaStatus] = None,
    city_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> Sequence[Trubka]:
    query = select(Trubka).options(*LOAD_OPTIONS)
    if status is not None:
        query = query.where(Trubka.status == status)
    if city_id is not None:
        query = query.where(Trubka.city_id == city_id)
    query = query.order_by(Trubka.created_at.desc(), Trubka.id.desc())
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def count_for(
    session: AsyncSession,
    *,
    city_id: Optional[int] = None,
    noga_id: Optional[int] = None,
    razgruz_id: Optional[int] = None,
) -> int:
    """Сколько трубок висит на городе, ноге или разгрузе — перед их удалением."""
    query = select(func.count()).select_from(Trubka)
    if city_id is not None:
        query = query.where(Trubka.city_id == city_id)
    if noga_id is not None:
        query = query.where(Trubka.noga_id == noga_id)
    if razgruz_id is not None:
        query = query.where(Trubka.razgruz_id == razgruz_id)
    return await session.scalar(query) or 0


async def summary(session: AsyncSession) -> TrubkiSummaryOut:
    result = await session.execute(
        select(Trubka.status, func.count()).group_by(Trubka.status)
    )
    counts = {status: count for status, count in result.all()}
    return TrubkiSummaryOut(
        total=sum(counts.values()),
        zacep=counts.get(TrubkaStatus.zacep, 0),
        vedut=counts.get(TrubkaStatus.vedut, 0),
        srez=counts.get(TrubkaStatus.srez, 0),
        zabrali=counts.get(TrubkaStatus.zabrali, 0),
        razgruzheno=counts.get(TrubkaStatus.razgruzheno, 0),
    )


def to_out(trubka: Trubka, *, can_manage: bool = False) -> TrubkaOut:
    noga_owner = trubka.noga.created_by if trubka.noga else None
    return TrubkaOut(
        id=trubka.id,
        status=trubka.status,
        city_id=trubka.city_id,
        city_name=trubka.city.name,
        amount=trubka.amount,
        amount_currency=trubka.amount_currency,
        noga_id=trubka.noga_id,
        noga_name=trubka.noga.name,
        noga_owner_name=noga_owner.display_name if noga_owner else None,
        razgruz_id=trubka.razgruz_id,
        razgruz_name=trubka.razgruz.name if trubka.razgruz else None,
        customer_name=trubka.customer_name,
        customer_address=trubka.customer_address,
        delivery=trubka.delivery,
        created_at=trubka.created_at,
        updated_at=trubka.updated_at,
        created_by_name=trubka.created_by.display_name if trubka.created_by else None,
        can_manage=can_manage,
    )
