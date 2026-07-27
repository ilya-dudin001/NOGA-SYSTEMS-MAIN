from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import (
    USERS_DELETE,
    USERS_MANAGE,
    USERS_READ,
    can_assign_role,
    can_modify_user,
    has_permission,
)
from app.db import get_session
from app.db.models import User, UserRole, UserStatus
from app.schemas import UserCreateIn, UserOut, UserUpdateIn
from app.services.audit import write_audit

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(USERS_READ))],
) -> list[User]:
    result = await session.execute(select(User).order_by(User.id.asc()))
    return list(result.scalars().all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(USERS_MANAGE))],
) -> User:
    if not can_assign_role(actor.role, body.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot assign this role"},
        )

    existing = await session.execute(select(User).where(User.telegram_id == body.telegram_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": "User with this telegram_id already exists"},
        )

    display = body.display_name or body.first_name or f"User {body.telegram_id}"
    user = User(
        telegram_id=body.telegram_id,
        username=body.username,
        first_name=body.first_name,
        display_name=display,
        role=body.role,
        status=UserStatus.active,
        created_by_id=actor.id,
    )
    session.add(user)
    await session.flush()
    await write_audit(
        session,
        action="user.created",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user.id),
        payload={"telegram_id": body.telegram_id, "role": body.role.value},
    )
    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(USERS_MANAGE))],
) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "User not found"},
        )

    if not can_modify_user(actor.role, target.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot modify this user"},
        )

    changes: dict = {}
    if body.role is not None and body.role != target.role:
        if not can_assign_role(actor.role, body.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Cannot assign this role"},
            )
        # Prevent demoting the last owner accidentally — soft check: cannot demote self from owner
        if target.role == UserRole.owner and target.id == actor.id and body.role != UserRole.owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "BAD_REQUEST", "message": "Cannot demote yourself from owner"},
            )
        changes["role"] = {"from": target.role.value, "to": body.role.value}
        target.role = body.role

    if body.status is not None and body.status != target.status:
        if target.id == actor.id and body.status == UserStatus.blocked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "BAD_REQUEST", "message": "Cannot block yourself"},
            )
        changes["status"] = {"from": target.status.value, "to": body.status.value}
        target.status = body.status

    if body.display_name is not None:
        changes["display_name"] = body.display_name
        target.display_name = body.display_name
    if body.username is not None:
        target.username = body.username
    if body.first_name is not None:
        target.first_name = body.first_name

    if changes:
        await write_audit(
            session,
            action="user.updated",
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(target.id),
            payload=changes,
        )
    await session.commit()
    await session.refresh(target)
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    if not has_permission(actor.role, USERS_DELETE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Missing permission: users:delete"},
        )

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "User not found"},
        )
    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_REQUEST", "message": "Cannot delete yourself"},
        )
    if target.role == UserRole.owner and actor.role != UserRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot delete owner"},
        )

    await write_audit(
        session,
        action="user.deleted",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(target.id),
        payload={"telegram_id": target.telegram_id, "role": target.role.value},
    )
    await session.delete(target)
    await session.commit()
