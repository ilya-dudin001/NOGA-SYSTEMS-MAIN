from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import OPERATIONS_ALL, OPERATIONS_OWN, has_permission
from app.db import get_session
from app.db.models import City, Noga, Razgruz, Trubka, TrubkaStatus, User
from app.schemas import TrubkaCreateIn, TrubkaOut, TrubkaUpdateIn
from app.services import trubki as trubki_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/trubki", tags=["trubki"])


def can_manage(actor: User) -> bool:
    """Трубки видит вся команда, а заводит и правит — все, кроме роли «нога»."""
    return has_permission(actor.role, OPERATIONS_ALL)


async def get_trubka_or_404(session: AsyncSession, trubka_id: int) -> Trubka:
    trubka = await trubki_service.load(session, trubka_id)
    if trubka is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Трубка не найдена"},
        )
    return trubka


async def require_city(session: AsyncSession, city_id: int) -> City:
    city = await session.scalar(select(City).where(City.id == city_id))
    if city is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Город не найден"},
        )
    return city


async def require_noga(session: AsyncSession, noga_id: int) -> Noga:
    noga = await session.scalar(select(Noga).where(Noga.id == noga_id))
    if noga is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Нога не найдена"},
        )
    return noga


async def require_razgruz(session: AsyncSession, razgruz_id: int) -> Razgruz:
    razgruz = await session.scalar(select(Razgruz).where(Razgruz.id == razgruz_id))
    if razgruz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Разгруз не найден"},
        )
    return razgruz


@router.get("", response_model=list[TrubkaOut])
async def list_trubki(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_OWN))],
    status_filter: Annotated[Optional[TrubkaStatus], Query(alias="status")] = None,
    city_id: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
) -> list[TrubkaOut]:
    items = await trubki_service.load_all(
        session, status=status_filter, city_id=city_id, limit=limit
    )
    manage = can_manage(actor)
    return [trubki_service.to_out(t, can_manage=manage) for t in items]


@router.get("/{trubka_id}", response_model=TrubkaOut)
async def get_trubka(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_OWN))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    return trubki_service.to_out(trubka, can_manage=can_manage(actor))


@router.post("", response_model=TrubkaOut, status_code=status.HTTP_201_CREATED)
async def create_trubka(
    body: TrubkaCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    await require_city(session, body.city_id)
    await require_noga(session, body.noga_id)
    if body.razgruz_id is not None:
        await require_razgruz(session, body.razgruz_id)

    trubka = Trubka(
        status=body.status,
        city_id=body.city_id,
        noga_id=body.noga_id,
        razgruz_id=body.razgruz_id,
        amount=body.amount,
        amount_currency=body.amount_currency,
        customer_name=body.customer_name.strip(),
        customer_address=body.customer_address.strip(),
        delivery=body.delivery,
        created_by_id=actor.id,
    )
    session.add(trubka)
    await session.flush()
    # Адрес и ФИО заказчика в аудит не пишем — только факт создания.
    await write_audit(
        session,
        action="trubka.created",
        actor_user_id=actor.id,
        target_type="trubka",
        target_id=str(trubka.id),
        payload={
            "status": trubka.status.value,
            "city_id": trubka.city_id,
            "noga_id": trubka.noga_id,
            "amount": trubka.amount,
            "currency": trubka.amount_currency.value,
        },
    )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka.id), can_manage=True
    )


@router.patch("/{trubka_id}", response_model=TrubkaOut)
async def update_trubka(
    trubka_id: int,
    body: TrubkaUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)

    # Все SELECT'ы до мутаций: autoflush иначе успеет записать половину правки.
    if body.city_id is not None and body.city_id != trubka.city_id:
        await require_city(session, body.city_id)
    if body.noga_id is not None and body.noga_id != trubka.noga_id:
        await require_noga(session, body.noga_id)
    razgruz_given = "razgruz_id" in body.model_fields_set
    if razgruz_given and body.razgruz_id is not None:
        await require_razgruz(session, body.razgruz_id)

    changes: dict = {}

    def loggable(value):
        return value.value if hasattr(value, "value") else value

    def apply(field: str, value) -> None:
        current = getattr(trubka, field)
        if value == current:
            return
        changes[field] = {"from": loggable(current), "to": loggable(value)}
        setattr(trubka, field, value)

    if body.status is not None:
        apply("status", body.status)
    if body.city_id is not None:
        apply("city_id", body.city_id)
    if body.noga_id is not None:
        apply("noga_id", body.noga_id)
    if razgruz_given:
        apply("razgruz_id", body.razgruz_id)
    if body.amount is not None:
        apply("amount", body.amount)
    if body.amount_currency is not None:
        apply("amount_currency", body.amount_currency)
    if body.delivery is not None:
        apply("delivery", body.delivery)
    # Данные заказчика меняем без записи значений в аудит.
    if body.customer_name is not None:
        name = body.customer_name.strip()
        if name != trubka.customer_name:
            trubka.customer_name = name
            changes["customer_name"] = "изменено"
    if body.customer_address is not None:
        address = body.customer_address.strip()
        if address != trubka.customer_address:
            trubka.customer_address = address
            changes["customer_address"] = "изменён"

    if changes:
        await write_audit(
            session,
            action="trubka.updated",
            actor_user_id=actor.id,
            target_type="trubka",
            target_id=str(trubka.id),
            payload=changes,
        )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=True
    )


@router.delete("/{trubka_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trubka(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> None:
    trubka = await get_trubka_or_404(session, trubka_id)
    await write_audit(
        session,
        action="trubka.deleted",
        actor_user_id=actor.id,
        target_type="trubka",
        target_id=str(trubka.id),
        payload={
            "status": trubka.status.value,
            "city_id": trubka.city_id,
            "noga_id": trubka.noga_id,
            "amount": trubka.amount,
            "currency": trubka.amount_currency.value,
        },
    )
    await session.delete(trubka)
    await session.commit()
