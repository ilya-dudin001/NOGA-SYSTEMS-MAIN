from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import RAZGRUZ_MANAGE, RAZGRUZ_READ
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


@router.get("", response_model=list[RazgruzOut])
async def list_razgruzy(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_READ))],
    only_active: bool = Query(default=False),
) -> list[RazgruzOut]:
    items = await razgruzy_service.load_all(session, only_active=only_active)
    counts = await razgruzy_service.city_counts(session)
    return [razgruzy_service.to_out(r, cities_count=counts.get(r.id, 0)) for r in items]


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
    return razgruzy_service.to_out(await get_razgruz_or_404(session, razgruz.id))


@router.patch("/{razgruz_id}", response_model=RazgruzOut)
async def update_razgruz(
    razgruz_id: int,
    body: RazgruzUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_MANAGE))],
) -> RazgruzOut:
    razgruz = await get_razgruz_or_404(session, razgruz_id)

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
    return razgruzy_service.to_out(fresh, cities_count=counts.get(fresh.id, 0))


@router.delete("/{razgruz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_razgruz(
    razgruz_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(RAZGRUZ_MANAGE))],
) -> None:
    razgruz = await get_razgruz_or_404(session, razgruz_id, with_cities=True)

    counts = await razgruzy_service.city_counts(session)
    linked = counts.get(razgruz.id, 0)
    if linked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICT",
                "message": (
                    f"Разгруз привязан к {linked} городам — сначала отвяжите его от них"
                ),
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
        },
    )
    await session.delete(razgruz)
    await session.commit()
