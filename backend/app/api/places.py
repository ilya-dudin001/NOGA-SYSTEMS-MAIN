"""API справочника банкоматов / терминалов / крупных POI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import PLACES_READ
from app.config import Settings, get_settings
from app.db import get_session
from app.db.models import User
from app.schemas import PlaceItemOut, PlacesNearbyIn, PlacesNearbyOut
from app.services import places as places_service
from app.services.audit import write_audit
from app.services.places import PlacesError


async def require_places_enabled(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.places_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Не найдено"},
        )


router = APIRouter(
    prefix="/api/places",
    tags=["places"],
    dependencies=[Depends(require_places_enabled)],
)


@router.post("/nearby", response_model=PlacesNearbyOut)
async def places_nearby(
    body: PlacesNearbyIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(PLACES_READ))],
) -> PlacesNearbyOut:
    try:
        result = await places_service.search_nearby(
            session,
            city=body.city,
            street=body.street,
            house=body.house,
        )
    except PlacesError as exc:
        code = status.HTTP_400_BAD_REQUEST
        if exc.code == "GEOCODE_FAILED":
            code = status.HTTP_404_NOT_FOUND
        elif exc.code == "PLACES_PROVIDER_ERROR":
            code = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    await write_audit(
        session,
        action="places.nearby",
        actor_user_id=actor.id,
        target_type="places",
        payload={
            "city": result["query"]["city"],
            "street": result["query"]["street"],
            "house": result["query"].get("house"),
            "items": len(result["items"]),
            "partial": result["partial"],
        },
    )
    await session.commit()

    return PlacesNearbyOut(
        query=result["query"],
        center=result["center"],
        partial=result["partial"],
        items=[PlaceItemOut(**item) for item in result["items"]],
    )
