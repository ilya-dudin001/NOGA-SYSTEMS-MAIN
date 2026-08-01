from __future__ import annotations

from typing import Annotated, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import (
    CITIES_ALL,
    CITIES_MANAGE,
    CITIES_READ,
    NOGAS_ALL,
    NOGAS_MANAGE,
    NOGAS_READ,
    RAZGRUZ_READ,
    has_permission,
)
from app.db import get_session
from app.db.models import City, CityStatus, Noga, Razgruz, User
from app.schemas import (
    CityCreateIn,
    CityDetailOut,
    CityOut,
    CitySuggestOut,
    CityUpdateIn,
)
from app.services import cities as cities_service
from app.services import geocode as geocode_service
from app.services import nogas as nogas_service
from app.services import razgruzy as razgruzy_service
from app.services import trubki as trubki_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/cities", tags=["cities"])


def cities_scope_owner(actor: User) -> Optional[int]:
    """None — актор ведёт все города, иначе только заведённые им."""
    return None if has_permission(actor.role, CITIES_ALL) else actor.id


def nogas_scope_owner(actor: User) -> Optional[int]:
    return None if has_permission(actor.role, NOGAS_ALL) else actor.id


def can_manage_city(actor: User, city: City) -> bool:
    return has_permission(actor.role, CITIES_ALL) or city.created_by_id == actor.id


def require_own_city(actor: User, city: City) -> None:
    if not can_manage_city(actor, city):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Город завёл другой пользователь — его можно только смотреть",
            },
        )


async def build_detail(
    session: AsyncSession, city: City, actor: User
) -> CityDetailOut:
    """Состав ответа режется по правам: cities:read есть даже у роли noga."""
    show_nogas = has_permission(actor.role, NOGAS_READ)
    show_razgruzy = has_permission(actor.role, RAZGRUZ_READ)
    # Ноги в деталях города показываем все и с автором: в одном городе работают
    # ноги разных админов, и по счётчику должно сходиться.
    nogas = (
        await cities_service.load_nogas(
            session, city.id, manage_owner_id=nogas_scope_owner(actor)
        )
        if show_nogas
        else []
    )
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
        can_manage=can_manage_city(actor, city),
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


async def check_noga_ids(
    session: AsyncSession,
    actor: User,
    noga_ids: Sequence[int],
    *,
    city_id: Optional[int] = None,
) -> None:
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

    owner_id = nogas_scope_owner(actor)
    if owner_id is not None:
        foreign = [n.name for n in found.values() if n.created_by_id != owner_id]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Чужие ноги двигать нельзя: " + ", ".join(sorted(foreign)),
                },
            )

    seen: set[str] = set()
    if city_id is not None and owner_id is not None:
        # Чужие ноги из города никуда не денутся — тёзку к ним не прикрепить.
        staying = await session.execute(
            select(Noga.name).where(
                Noga.city_id == city_id, Noga.created_by_id != owner_id
            )
        )
        seen.update(staying.scalars().all())

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
    scope: str = Query(default="own", pattern="^(own|working)$"),
) -> list[CityOut]:
    """own — свой участок (у админа: заведённые им и те, где стоят его ноги),
    working — общая витрина городов в работе, одинаковая для всех ролей."""
    if scope == "working":
        cities = await cities_service.load_all(session, status=CityStatus.working)
    else:
        cities = await cities_service.load_all(
            session,
            owner_id=cities_scope_owner(actor),
            with_nogas_of=nogas_scope_owner(actor),
        )
    nogas = await cities_service.noga_counts(session)
    show_razgruzy = has_permission(actor.role, RAZGRUZ_READ)
    razgruz_counts = await razgruzy_service.city_counts(session) if show_razgruzy else {}
    return [
        cities_service.to_out(
            city,
            nogas_count=nogas.get(city.id, 0),
            razgruz_city_counts=razgruz_counts,
            include_razgruzy=show_razgruzy,
            can_manage=can_manage_city(actor, city),
        )
        for city in cities
    ]


@router.get("/suggest", response_model=list[CitySuggestOut])
async def suggest_cities(
    _: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=3, ge=1, le=5),
    lang: str = Query(default="ru", max_length=16),
) -> list[CitySuggestOut]:
    """Подсказки названий (Photon + перевод Nominatim) и валюта страны."""
    rows = await geocode_service.suggest(q, limit=limit, lang=lang)
    return [CitySuggestOut.model_validate(row) for row in rows]


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
    await geocode_service.ensure_city_coords(session, city)
    await cities_service.replace_razgruzy(session, city.id, razgruz_ids)
    if noga_ids:
        await nogas_service.attach_to_city(
            session, city, noga_ids, owner_id=nogas_scope_owner(actor)
        )
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
    require_own_city(actor, city)
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
        await check_noga_ids(session, actor, noga_ids, city_id=city.id)

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
        await nogas_service.rename_city_snapshots(session, city.name, new_name)
        city.name = new_name
        geocode_service.clear_coords(city)
        await geocode_service.ensure_city_coords(session, city)
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
        attached, detached = await nogas_service.attach_to_city(
            session, city, noga_ids, owner_id=nogas_scope_owner(actor)
        )
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
    detach_nogas: bool = Query(
        default=False,
        description="Снять прикреплённые ноги с города и всё-таки удалить его",
    ),
) -> None:
    city = await get_city_or_404(session, city_id)
    require_own_city(actor, city)

    # Трубки ссылаются на город, а история заказов важнее удобства уборки справочника.
    trubki_count = await trubki_service.count_for(session, city_id=city.id)
    if trubki_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CITY_HAS_TRUBKI",
                "message": (
                    f"По городу заведено трубок: {trubki_count}. "
                    "Сначала удалите их или перенесите в другой город"
                ),
                "trubki": trubki_count,
            },
        )

    # Ноги не удаляем вместе с городом никогда: сначала спрашиваем пользователя,
    # он присылает detach_nogas=true, и только тогда снимаем привязку.
    attached = await nogas_service.names_in_city(session, city.id)
    if attached and not detach_nogas:
        lead = (
            "К городу прикреплена нога: "
            if len(attached) == 1
            else "К городу прикреплены ноги: "
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CITY_HAS_NOGAS",
                "message": (
                    lead
                    + ", ".join(attached)
                    + ". При удалении города они автоматически с него снимутся"
                ),
                "nogas": attached,
            },
        )

    detached = await nogas_service.detach_from_city(session, city) if attached else []

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
            "detached_nogas": detached,
        },
    )
    # Связи с разгрузами снимает сам ORM: коллекция загружена через selectinload,
    # а FK ON DELETE CASCADE в SQLite по умолчанию не работает.
    await session.delete(city)
    await session.commit()
