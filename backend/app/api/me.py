from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.db.models import User
from app.schemas import MeOut
from app.services.users import user_to_me

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
async def get_me(user: Annotated[User, Depends(get_current_user)]) -> MeOut:
    return user_to_me(user)
