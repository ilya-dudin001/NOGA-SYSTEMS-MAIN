from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import CITIES_MANAGE, CITIES_READ
from app.db import get_session
from app.db.models import City, User
from app.schemas import CityCreateIn, CityOut, CityUpdateIn
from app.services import cities as cities_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/cities", tags=["cities"])


@router.get("", response_model=list[CityOut])
async def list_cities(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_READ))],
) -> list[City]:
    result = await session.execute(select(City).order_by(City.name.asc()))
    return list(result.scalars().all())


@router.post("", response_model=CityOut, status_code=status.HTTP_201_CREATED)
async def create_city(
    body: CityCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
) -> City:
    if await cities_service.find_by_name(session, body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "Такой город уже есть"},
        )

    city = City(name=cities_service.normalize(body.name), created_by_id=actor.id)
    session.add(city)
    await session.flush()
    await write_audit(
        session,
        action="city.created",
        actor_user_id=actor.id,
        target_type="city",
        target_id=str(city.id),
        payload={"name": city.name},
    )
    await session.commit()
    await session.refresh(city)
    return city


@router.patch("/{city_id}", response_model=CityOut)
async def update_city(
    city_id: int,
    body: CityUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(CITIES_MANAGE))],
) -> City:
    city = await session.get(City, city_id)
    if city is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Город не найден"},
        )

    changes: dict = {}
    if body.name is not None:
        new_name = cities_service.normalize(body.name)
        clash = await cities_service.find_by_name(session, new_name)
        if clash is not None and clash.id != city.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CONFLICT", "message": "Такой город уже есть"},
            )
        changes["name"] = {"from": city.name, "to": new_name}
        city.name = new_name
    if body.is_active is not None and body.is_active != city.is_active:
        changes["is_active"] = {"from": city.is_active, "to": body.is_active}
        city.is_active = body.is_active

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
    await session.refresh(city)
    return city
