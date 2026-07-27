from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import NOGAS_MANAGE, NOGAS_READ
from app.db import get_session
from app.db.models import City, Noga, User
from app.schemas import NogaCreateIn, NogaOut, NogaUpdateIn
from app.services import cities as cities_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/nogas", tags=["nogas"])


def to_out(noga: Noga) -> NogaOut:
    return NogaOut(
        id=noga.id,
        name=noga.name,
        city_id=noga.city_id,
        city_name=noga.city.name,
        is_test=noga.is_test,
        is_active=noga.is_active,
        created_at=noga.created_at,
    )


async def load_noga(session: AsyncSession, noga_id: int) -> Noga:
    result = await session.execute(
        select(Noga)
        .options(selectinload(Noga.city))
        .where(Noga.id == noga_id)
        .execution_options(populate_existing=True)
    )
    noga = result.scalar_one_or_none()
    if noga is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Нога не найдена"},
        )
    return noga


@router.get("", response_model=list[NogaOut])
async def list_nogas(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_READ))],
    city_id: Optional[int] = Query(default=None),
    include_test: bool = Query(default=True),
    only_active: bool = Query(default=False),
) -> list[NogaOut]:
    query = select(Noga).options(selectinload(Noga.city))
    if city_id is not None:
        query = query.where(Noga.city_id == city_id)
    if not include_test:
        query = query.where(Noga.is_test.is_(False))
    if only_active:
        query = query.where(Noga.is_active.is_(True))

    result = await session.execute(query.order_by(Noga.name.asc()))
    return [to_out(n) for n in result.scalars().all()]


@router.post("", response_model=NogaOut, status_code=status.HTTP_201_CREATED)
async def create_noga(
    body: NogaCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> NogaOut:
    if body.city_id is None and not body.city_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_REQUEST", "message": "Укажите город"},
        )

    if body.city_id is not None:
        city = await session.get(City, body.city_id)
        if city is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Город не найден"},
            )
    else:
        city = await cities_service.get_or_create(session, body.city_name or "", actor)

    name = " ".join(body.name.split())
    existing = await session.execute(
        select(Noga).where(Noga.city_id == city.id, Noga.name == name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Нога с таким именем в этом городе уже есть"},
        )

    noga = Noga(
        name=name,
        city_id=city.id,
        is_test=body.is_test,
        is_active=True,
        created_by_id=actor.id,
    )
    session.add(noga)
    await session.flush()
    await write_audit(
        session,
        action="noga.created",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga.id),
        payload={"name": noga.name, "city": city.name, "is_test": noga.is_test},
    )
    await session.commit()
    return to_out(await load_noga(session, noga.id))


@router.patch("/{noga_id}", response_model=NogaOut)
async def update_noga(
    noga_id: int,
    body: NogaUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> NogaOut:
    noga = await load_noga(session, noga_id)

    # Целевые значения считаем до мутаций: иначе autoflush перед SELECT'ом
    # упрётся в UNIQUE и отдаст 500 вместо понятного 409.
    new_city: City | None = None
    if body.city_id is not None and body.city_id != noga.city_id:
        new_city = await session.get(City, body.city_id)
        if new_city is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Город не найден"},
            )

    target_city_id = new_city.id if new_city is not None else noga.city_id
    target_name = " ".join(body.name.split()) if body.name is not None else noga.name

    if (target_city_id, target_name) != (noga.city_id, noga.name):
        clash = await session.execute(
            select(Noga).where(
                Noga.city_id == target_city_id,
                Noga.name == target_name,
                Noga.id != noga.id,
            )
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFLICT",
                    "message": "Нога с таким именем в этом городе уже есть",
                },
            )

    changes: dict = {}
    if new_city is not None:
        changes["city"] = {"from": noga.city.name, "to": new_city.name}
        noga.city_id = new_city.id
    if target_name != noga.name:
        changes["name"] = {"from": noga.name, "to": target_name}
        noga.name = target_name
    if body.is_test is not None and body.is_test != noga.is_test:
        changes["is_test"] = {"from": noga.is_test, "to": body.is_test}
        noga.is_test = body.is_test
    if body.is_active is not None and body.is_active != noga.is_active:
        changes["is_active"] = {"from": noga.is_active, "to": body.is_active}
        noga.is_active = body.is_active

    if changes:
        await write_audit(
            session,
            action="noga.updated",
            actor_user_id=actor.id,
            target_type="noga",
            target_id=str(noga.id),
            payload=changes,
        )

    await session.commit()
    return to_out(await load_noga(session, noga_id))


@router.delete("/{noga_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_noga(
    noga_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> None:
    noga = await load_noga(session, noga_id)
    await write_audit(
        session,
        action="noga.deleted",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga.id),
        payload={"name": noga.name, "city": noga.city.name, "is_test": noga.is_test},
    )
    await session.delete(noga)
    await session.commit()
