from __future__ import annotations

from typing import Annotated, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import (
    CITIES_MANAGE,
    CITIES_READ,
    NOGAS_MANAGE,
    NOGAS_READ,
    RAZGRUZ_READ,
    has_permission,
)
from app.db import get_session
from app.db.models import City, Noga, Razgruz, User
from app.schemas import CityCreateIn, CityDetailOut, CityOut, CityUpdateIn
from app.services import cities as cities_service
from app.services import nogas as nogas_service
from app.services import razgruzy as razgruzy_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/cities", tags=["cities"])


async def build_detail(
    session: AsyncSession, city: City, actor: User
) -> CityDetailOut:
    """Состав ответа режется по правам: cities:read есть даже у роли noga."""
    show_nogas = has_permission(actor.role, NOGAS_READ)
    show_razgruzy = has_permission(actor.role, RAZGRUZ_READ)
    nogas = await cities_service.load_nogas(session, city.id) if show_nogas else []
    nogas_count = await session.scalar(
        select(func.count()).select_from(Noga).where(Noga.city_id == city.id)
    )
    return cities_service.to_detail_out(
        city,
        nogas=nogas,
        nogas_count=nogas_count or 0,
        razgruz_city_counts=await razgruzy_service.city_counts(session)
        if show_razgruzy
        else None,
        include_razgruzy=show_razgruzy,
    )


async def get_city_or_404(session: AsyncSession, city_id: int) -> City:
    city = await cities_service.load(session, city_id)
    if city is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Город не найден"},
        )
    return city


async def check_razgruz_ids(session: AsyncSession, razgruz_ids: Sequence[int]) -> None:
    wanted = set(razgruz_ids)
    if not wanted:
        return
    result = await session.execute(select(Razgruz.id).where(Razgruz.id.in_(wanted)))
    missing = wanted - set(result.scalars().all())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "Разгруз не найден: " + ", ".join(str(i) for i in sorted(missing)),
            },
        )


async def check_noga_ids(session: AsyncSession, actor: User, noga_ids: Sequence[int]) -> None:
    """Ноги существуют, актор вправе их двигать, тёзок в новом составе города нет."""
    if not has_permission(actor.role, NOGAS_MANAGE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Нет прав менять состав ног"},
        )
    wanted = set(noga_ids)
    if not wanted:
        return

    result = await session.execute(select(Noga).where(Noga.id.in_(wanted)))
    found = {noga.id: noga for noga in result.scalars().all()}
    missing = wanted - set(found)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "Нога не найдена: " + ", ".join(str(i) for i in sorted(missing)),
            },
        )

    seen: set[str] = set()
    for noga in found.values():
        if noga.name in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFLICT",
                    "message": f"В городе не может быть двух ног с именем «{noga.name}»",
                },
            )
        seen.add(noga.name)


def check_amount(amount: Optional[int], currency) -> None:
    if (amount is None) != (currency is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BAD_REQUEST",
                "message": "Укажите и сумму, и валюту — или не указывайте ни то, ни другое",
            },
        )


@router.get("", response_model=list[CityOut])
async def list_cities(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_READ))],
) -> list[CityOut]:
    cities = await cities_service.load_all(session)
    nogas = await cities_service.noga_counts(session)
    show_razgruzy = has_permission(actor.role, RAZGRUZ_READ)
    razgruz_counts = await razgruzy_service.city_counts(session) if show_razgruzy else {}
    return [
        cities_service.to_out(
            city,
            nogas_count=nogas.get(city.id, 0),
            razgruz_city_counts=razgruz_counts,
            include_razgruzy=show_razgruzy,
        )
        for city in cities
    ]


@router.get("/{city_id}", response_model=CityDetailOut)
async def get_city(
    city_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_READ))],
) -> CityDetailOut:
    city = await get_city_or_404(session, city_id)
    return await build_detail(session, city, actor)


@router.post("", response_model=CityDetailOut, status_code=status.HTTP_201_CREATED)
async def create_city(
    body: CityCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
) -> CityDetailOut:
    check_amount(body.min_amount, body.min_amount_currency)
    razgruz_ids = body.razgruz_ids or []
    await check_razgruz_ids(session, razgruz_ids)

    noga_ids: Optional[list[int]] = None
    if body.noga_ids is not None:
        noga_ids = list(dict.fromkeys(body.noga_ids))
        await check_noga_ids(session, actor, noga_ids)

    if await cities_service.find_by_name(session, body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Такой город уже есть"},
        )

    city = City(
        name=cities_service.normalize(body.name),
        status=body.status,
        min_amount=body.min_amount,
        min_amount_currency=body.min_amount_currency,
        created_by_id=actor.id,
    )
    session.add(city)
    await session.flush()
    await cities_service.replace_razgruzy(session, city.id, razgruz_ids)
    if noga_ids:
        await nogas_service.attach_to_city(session, city.id, noga_ids)
    await write_audit(
        session,
        action="city.created",
        actor_user_id=actor.id,
        target_type="city",
        target_id=str(city.id),
        payload={
            "name": city.name,
            "status": city.status.value,
            "min_amount": city.min_amount,
            "currency": city.min_amount_currency.value if city.min_amount_currency else None,
            "razgruz_ids": razgruz_ids,
            "noga_ids": noga_ids or [],
        },
    )
    await session.commit()
    return await build_detail(session, await get_city_or_404(session, city.id), actor)


@router.patch("/{city_id}", response_model=CityDetailOut)
async def update_city(
    city_id: int,
    body: CityUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
) -> CityDetailOut:
    city = await get_city_or_404(session, city_id)
    provided = body.model_fields_set

    # Всё, что требует SELECT'ов, считаем до мутаций: autoflush иначе упрётся
    # в UNIQUE и отдаст 500 вместо понятного 409.
    target_amount = body.min_amount if "min_amount" in provided else city.min_amount
    target_currency = (
        body.min_amount_currency
        if "min_amount_currency" in provided
        else city.min_amount_currency
    )
    check_amount(target_amount, target_currency)

    razgruz_ids: Optional[list[int]] = None
    if "razgruz_ids" in provided:
        razgruz_ids = body.razgruz_ids or []
        await check_razgruz_ids(session, razgruz_ids)

    noga_ids: Optional[list[int]] = None
    if "noga_ids" in provided:
        noga_ids = list(dict.fromkeys(body.noga_ids or []))
        await check_noga_ids(session, actor, noga_ids)

    new_name: Optional[str] = None
    if body.name is not None:
        new_name = cities_service.normalize(body.name)
        if new_name.lower() != city.name.lower():
            clash = await cities_service.find_by_name(session, new_name)
            if clash is not None and clash.id != city.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "CONFLICT", "message": "Такой город уже есть"},
                )

    changes: dict = {}
    if new_name is not None and new_name != city.name:
        changes["name"] = {"from": city.name, "to": new_name}
        city.name = new_name
    if body.status is not None and body.status != city.status:
        changes["status"] = {"from": city.status.value, "to": body.status.value}
        city.status = body.status
    if target_amount != city.min_amount:
        changes["min_amount"] = {"from": city.min_amount, "to": target_amount}
        city.min_amount = target_amount
    if target_currency != city.min_amount_currency:
        changes["currency"] = {
            "from": city.min_amount_currency.value if city.min_amount_currency else None,
            "to": target_currency.value if target_currency else None,
        }
        city.min_amount_currency = target_currency
    if razgruz_ids is not None:
        before = sorted(r.id for r in city.razgruzy)
        after = sorted(set(razgruz_ids))
        if before != after:
            changes["razgruz_ids"] = {"from": before, "to": after}
            await cities_service.replace_razgruzy(session, city.id, razgruz_ids)
    if noga_ids is not None:
        attached, detached = await nogas_service.attach_to_city(session, city.id, noga_ids)
        if attached or detached:
            changes["nogas"] = {"attached": attached, "detached": detached}

    if changes:
        await write_audit(
            session,
            action="city.updated",
            actor_user_id=actor.id,
            target_type="city",
            target_id=str(city.id),
            payload=changes,
        )
    await session.commit()
    return await build_detail(session, await get_city_or_404(session, city_id), actor)


@router.delete("/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city(
    city_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
) -> None:
    city = await get_city_or_404(session, city_id)

    nogas_left = await session.scalar(
        select(func.count()).select_from(Noga).where(Noga.city_id == city.id)
    )
    if nogas_left:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": (
                    f"В городе ещё {nogas_left} ног(и) — открепите их в форме города "
                    "или удалите перед удалением города"
                ),
            },
        )

    await write_audit(
        session,
        action="city.deleted",
        actor_user_id=actor.id,
        target_type="city",
        target_id=str(city.id),
        payload={
            "name": city.name,
            "status": city.status.value,
            "razgruz_ids": sorted(r.id for r in city.razgruzy),
        },
    )
    # Связи с разгрузами снимает сам ORM: коллекция загружена через selectinload,
    # а FK ON DELETE CASCADE в SQLite по умолчанию не работает.
    await session.delete(city)
    await session.commit()
