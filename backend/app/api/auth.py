from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.initdata import InitDataError, validate_init_data
from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.db import get_session
from app.db.models import UserStatus
from app.schemas import AuthDevIn, AuthOut, AuthTelegramIn
from app.services.audit import write_audit
from app.services.users import (
    get_active_user_by_telegram_id,
    log_auth_attempt,
    sync_profile_from_telegram,
    touch_last_seen,
    user_to_me,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthOut)
async def auth_telegram(
    body: AuthTelegramIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthOut:
    telegram_id: int | None = None
    try:
        validated = validate_init_data(
            body.init_data,
            settings.bot_token,
            max_age_seconds=settings.initdata_max_age_seconds,
        )
        telegram_id = validated.user.id
    except InitDataError as exc:
        await log_auth_attempt(
            session, telegram_id=telegram_id, success=False, reason=exc.code
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED
            if exc.code in ("BAD_SIGNATURE", "EXPIRED")
            else status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    user = await get_active_user_by_telegram_id(session, telegram_id)
    if user is None:
        await log_auth_attempt(
            session, telegram_id=telegram_id, success=False, reason="NOT_ALLOWED"
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_ALLOWED", "message": "User is not in allowlist"},
        )

    if user.status == UserStatus.blocked:
        await log_auth_attempt(
            session, telegram_id=telegram_id, success=False, reason="BLOCKED"
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "BLOCKED", "message": "User is blocked"},
        )

    sync_profile_from_telegram(user, validated.user)
    await touch_last_seen(session, user)
    await log_auth_attempt(session, telegram_id=telegram_id, success=True, reason="OK")
    await write_audit(
        session,
        action="user.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        payload={"via": "telegram_initdata"},
    )
    await session.commit()
    await session.refresh(user)

    token = create_access_token(
        user_id=user.id,
        telegram_id=user.telegram_id,
        role=user.role.value,
        settings=settings,
    )
    return AuthOut(access_token=token, user=user_to_me(user))


@router.post("/dev", response_model=AuthOut)
async def auth_dev(
    body: AuthDevIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthOut:
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Dev auth disabled"},
        )
    if body.secret != settings.dev_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid dev secret"},
        )

    user = await get_active_user_by_telegram_id(session, body.telegram_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_ALLOWED", "message": "User is not in allowlist"},
        )
    if user.status == UserStatus.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "BLOCKED", "message": "User is blocked"},
        )

    user.last_seen_at = datetime.now(timezone.utc)
    await write_audit(
        session,
        action="user.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        payload={"via": "dev"},
    )
    await session.commit()
    await session.refresh(user)

    token = create_access_token(
        user_id=user.id,
        telegram_id=user.telegram_id,
        role=user.role.value,
        settings=settings,
    )
    return AuthOut(access_token=token, user=user_to_me(user))
