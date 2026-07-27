from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.auth.permissions import DASHBOARD_GLOBAL, has_permission
from app.db.models import User
from app.schemas import DashboardSummaryOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
async def dashboard_summary(
    user: Annotated[User, Depends(get_current_user)],
) -> DashboardSummaryOut:
    """Aggregates for the home screen. Operations table not yet implemented — zeros with role scope."""
    scope = "global" if has_permission(user.role, DASHBOARD_GLOBAL) else "own"
    return DashboardSummaryOut(scope=scope)
