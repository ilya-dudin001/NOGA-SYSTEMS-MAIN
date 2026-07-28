from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import PROFILE_RENAME
from app.db import get_session
from app.db.models import User
from app.schemas import MeOut, MeUpdateIn
from app.services.users import UserActionError, rename_self, user_to_me

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
async def get_me(user: Annotated[User, Depends(get_current_user)]) -> MeOut:
    return user_to_me(user)


@router.patch("/me", response_model=MeOut)
async def update_me(
    body: MeUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(PROFILE_RENAME))],
) -> MeOut:
    """Смена собственного ника. Роль и статус отсюда не меняются никогда."""
    try:
        user = await rename_self(session, actor=actor, display_name=body.display_name)
    except UserActionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return user_to_me(user)
