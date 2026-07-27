from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import (
    ROLE_LABELS_RU,
    USERS_MANAGE,
    can_assign_role,
    can_modify_user,
    has_permission,
)
from app.db.models import User, UserRole, UserStatus
from app.services.audit import write_audit

router = Router(name="users_cmd")

ROLE_ALIASES: dict[str, UserRole] = {
    "owner": UserRole.owner,
    "right_hand": UserRole.right_hand,
    "righthand": UserRole.right_hand,
    "правая": UserRole.right_hand,
    "правая_рука": UserRole.right_hand,
    "admin": UserRole.admin,
    "админ": UserRole.admin,
    "администратор": UserRole.admin,
    "noga": UserRole.noga,
    "нога": UserRole.noga,
}


def _denied() -> str:
    return "Доступ закрыт. Обратитесь к Owner."


def _parse_role(raw: str) -> UserRole | None:
    return ROLE_ALIASES.get(raw.strip().lower())


@router.message(Command("users"))
async def cmd_users(
    message: Message,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied())
        return
    if not has_permission(db_user.role, USERS_MANAGE) and not has_permission(
        db_user.role, "users:read"
    ):
        await message.answer("Недостаточно прав.")
        return

    result = await session.execute(select(User).order_by(User.id.asc()))
    users = list(result.scalars().all())
    if not users:
        await message.answer("Пользователей нет.")
        return

    lines = ["<b>Пользователи</b>\n"]
    for u in users:
        mark = "🚫" if u.status == UserStatus.blocked else "✅"
        role = ROLE_LABELS_RU.get(u.role, u.role.value)
        uname = f"@{u.username}" if u.username else "—"
        lines.append(
            f"{mark} <code>{u.telegram_id}</code> · {u.display_name} ({uname}) · {role}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("adduser"))
async def cmd_adduser(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied())
        return
    if not has_permission(db_user.role, USERS_MANAGE):
        await message.answer("Недостаточно прав.")
        return

    args = (command.args or "").split()
    if len(args) < 2:
        await message.answer(
            "Использование: /adduser &lt;telegram_id&gt; &lt;роль&gt;\n"
            "Роли: owner, right_hand, admin, noga"
        )
        return

    try:
        tid = int(args[0])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    role = _parse_role(args[1])
    if role is None:
        await message.answer("Неизвестная роль. Допустимо: owner, right_hand, admin, noga")
        return

    if not can_assign_role(db_user.role, role):
        await message.answer("Вы не можете назначать эту роль.")
        return

    existing = await session.execute(select(User).where(User.telegram_id == tid))
    if existing.scalar_one_or_none() is not None:
        await message.answer("Пользователь уже есть в системе.")
        return

    user = User(
        telegram_id=tid,
        display_name=f"User {tid}",
        role=role,
        status=UserStatus.active,
        created_by_id=db_user.id,
    )
    session.add(user)
    await session.flush()
    await write_audit(
        session,
        action="user.created",
        actor_user_id=db_user.id,
        target_type="user",
        target_id=str(user.id),
        payload={"telegram_id": tid, "role": role.value, "via": "bot"},
    )
    await session.commit()
    await message.answer(
        f"Добавлен <code>{tid}</code> с ролью <b>{ROLE_LABELS_RU[role]}</b>."
    )


@router.message(Command("setrole"))
async def cmd_setrole(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied())
        return
    if not has_permission(db_user.role, USERS_MANAGE):
        await message.answer("Недостаточно прав.")
        return

    args = (command.args or "").split()
    if len(args) < 2:
        await message.answer("Использование: /setrole &lt;telegram_id&gt; &lt;роль&gt;")
        return

    try:
        tid = int(args[0])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    role = _parse_role(args[1])
    if role is None:
        await message.answer("Неизвестная роль.")
        return

    result = await session.execute(select(User).where(User.telegram_id == tid))
    target = result.scalar_one_or_none()
    if target is None:
        await message.answer("Пользователь не найден.")
        return

    if not can_modify_user(db_user.role, target.role) or not can_assign_role(db_user.role, role):
        await message.answer("Недостаточно прав для этой операции.")
        return

    if target.id == db_user.id and target.role == UserRole.owner and role != UserRole.owner:
        await message.answer("Нельзя снять с себя роль Owner.")
        return

    old = target.role
    target.role = role
    await write_audit(
        session,
        action="user.updated",
        actor_user_id=db_user.id,
        target_type="user",
        target_id=str(target.id),
        payload={"role": {"from": old.value, "to": role.value}, "via": "bot"},
    )
    await session.commit()
    await message.answer(
        f"Роль <code>{tid}</code>: {ROLE_LABELS_RU[old]} → <b>{ROLE_LABELS_RU[role]}</b>"
    )


@router.message(Command("block"))
async def cmd_block(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    await _set_status(message, command, session, db_user, is_allowed, UserStatus.blocked)


@router.message(Command("unblock"))
async def cmd_unblock(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    await _set_status(message, command, session, db_user, is_allowed, UserStatus.active)


async def _set_status(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User | None,
    is_allowed: bool,
    new_status: UserStatus,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied())
        return
    if not has_permission(db_user.role, USERS_MANAGE):
        await message.answer("Недостаточно прав.")
        return

    args = (command.args or "").split()
    if len(args) < 1:
        await message.answer("Использование: /block|/unblock &lt;telegram_id&gt;")
        return
    try:
        tid = int(args[0])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    result = await session.execute(select(User).where(User.telegram_id == tid))
    target = result.scalar_one_or_none()
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    if target.id == db_user.id:
        await message.answer("Нельзя заблокировать себя.")
        return
    if not can_modify_user(db_user.role, target.role):
        await message.answer("Недостаточно прав.")
        return

    old = target.status
    target.status = new_status
    await write_audit(
        session,
        action="user.updated",
        actor_user_id=db_user.id,
        target_type="user",
        target_id=str(target.id),
        payload={
            "status": {"from": old.value, "to": new_status.value},
            "via": "bot",
        },
    )
    await session.commit()
    verb = "заблокирован" if new_status == UserStatus.blocked else "разблокирован"
    await message.answer(f"Пользователь <code>{tid}</code> {verb}.")
