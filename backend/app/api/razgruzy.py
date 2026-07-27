from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import RAZGRUZ_ALL, RAZGRUZ_MANAGE, RAZGRUZ_READ, has_permission
from app.db import get_session
from app.db.models import Razgruz, User
from app.schemas import RazgruzCreateIn, RazgruzOut, RazgruzUpdateIn
from app.services import razgruzy as razgruzy_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/razgruzy", tags=["razgruzy"])


async def get_razgruz_or_404(
    session: AsyncSession, razgruz_id: int, *, with_cities: bool = False
) -> Razgruz:
    razgruz = await razgruzy_service.load(session, razgruz_id, with_cities=with_cities)
    if razgruz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Разгруз не найден"},
        )
    return razgruz


def can_manage(actor: User, razgruz: Razgruz) -> bool:
    return has_permission(actor.role, RAZGRUZ_ALL) or razgruz.created_by_id == actor.id


def require_own(actor: User, razgruz: Razgruz) -> None:
    """Разгрузы видит вся команда, а правит и удаляет только тот, кто их завёл."""
    if not can_manage(actor, razgruz):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Разгруз завёл другой пользователь — его можно только смотреть",
            },
        )


def out(actor: User, razgruz: Razgruz, *, cities_count: int = 0) -> RazgruzOut:
    return razgruzy_service.to_out(
        razgruz,
        cities_count=cities_count,
        can_manage=can_manage(actor, razgruz),
        created_by_me=razgruz.created_by_id == actor.id,
    )


@router.get("", response_model=list[RazgruzOut])
async def list_razgruzy(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_READ))],
    only_active: bool = Query(default=False),
) -> list[RazgruzOut]:
    items = await razgruzy_service.load_all(session, only_active=only_active)
    counts = await razgruzy_service.city_counts(session)
    return [out(actor, r, cities_count=counts.get(r.id, 0)) for r in items]


@router.post("", response_model=RazgruzOut, status_code=status.HTTP_201_CREATED)
async def create_razgruz(
    body: RazgruzCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_MANAGE))],
) -> RazgruzOut:
    if await razgruzy_service.find_by_name(session, body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Разгруз с таким названием уже есть"},
        )

    razgruz = Razgruz(
        name=razgruzy_service.normalize(body.name),
        commission_percent=body.commission_percent,
        contact=(body.contact or "").strip() or None,
        is_active=True,
        created_by_id=actor.id,
    )
    session.add(razgruz)
    await session.flush()
    await write_audit(
        session,
        action="razgruz.created",
        actor_user_id=actor.id,
        target_type="razgruz",
        target_id=str(razgruz.id),
        payload={"name": razgruz.name, "commission_percent": body.commission_percent},
    )
    await session.commit()
    return out(actor, await get_razgruz_or_404(session, razgruz.id))


@router.patch("/{razgruz_id}", response_model=RazgruzOut)
async def update_razgruz(
    razgruz_id: int,
    body: RazgruzUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_MANAGE))],
) -> RazgruzOut:
    razgruz = await get_razgruz_or_404(session, razgruz_id)
    require_own(actor, razgruz)

    # Проверка дубликата до мутаций: иначе autoflush перед SELECT'ом
    # упрётся в UNIQUE и отдаст 500 вместо понятного 409.
    new_name: str | None = None
    if body.name is not None:
        new_name = razgruzy_service.normalize(body.name)
        clash = await razgruzy_service.find_by_name(
            session, new_name, exclude_id=razgruz.id
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CONFLICT", "message": "Разгруз с таким названием уже есть"},
            )

    changes: dict = {}
    if new_name is not None and new_name != razgruz.name:
        changes["name"] = {"from": razgruz.name, "to": new_name}
        razgruz.name = new_name
    if body.commission_percent is not None:
        current = float(razgruz.commission_percent)
        if body.commission_percent != current:
            changes["commission_percent"] = {
                "from": current,
                "to": body.commission_percent,
            }
            razgruz.commission_percent = body.commission_percent
    if "contact" in body.model_fields_set:
        new_contact = (body.contact or "").strip() or None
        if new_contact != razgruz.contact:
            changes["contact"] = {"from": razgruz.contact, "to": new_contact}
            razgruz.contact = new_contact
    if body.is_active is not None and body.is_active != razgruz.is_active:
        changes["is_active"] = {"from": razgruz.is_active, "to": body.is_active}
        razgruz.is_active = body.is_active

    if changes:
        await write_audit(
            session,
            action="razgruz.updated",
            actor_user_id=actor.id,
            target_type="razgruz",
            target_id=str(razgruz.id),
            payload=changes,
        )
    await session.commit()

    counts = await razgruzy_service.city_counts(session)
    fresh = await get_razgruz_or_404(session, razgruz_id)
    return out(actor, fresh, cities_count=counts.get(fresh.id, 0))


@router.delete("/{razgruz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_razgruz(
    razgruz_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_MANAGE))],
    detach_cities: bool = Query(
        default=False,
        description="Отвязать разгруз от городов и всё-таки удалить его",
    ),
) -> None:
    # cities грузим всегда: коллекция объявлена lazy="raise", а ORM снимает
    # строки city_razgruzy только по загруженной коллекции.
    razgruz = await get_razgruz_or_404(session, razgruz_id, with_cities=True)
    require_own(actor, razgruz)

    linked = await razgruzy_service.city_names(session, razgruz.id)
    if linked and not detach_cities:
        lead = (
            "Разгруз привязан к городу: "
            if len(linked) == 1
            else "Разгруз привязан к городам: "
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "RAZGRUZ_HAS_CITIES",
                "message": (
                    lead
                    + ", ".join(linked)
                    + ". При удалении разгруза они автоматически от него отвяжутся"
                ),
                "cities": linked,
            },
        )

    await write_audit(
        session,
        action="razgruz.deleted",
        actor_user_id=actor.id,
        target_type="razgruz",
        target_id=str(razgruz.id),
        payload={
            "name": razgruz.name,
            "commission_percent": float(razgruz.commission_percent),
            "detached_cities": linked,
        },
    )
    # Связи в city_razgruzy снимает сам ORM — города остаются, разгруз уходит.
    await session.delete(razgruz)
    await session.commit()
