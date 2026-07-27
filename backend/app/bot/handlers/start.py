from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import ROLE_LABELS_RU
from app.config import Settings
from app.db.models import User, UserStatus

router = Router(name="start")


def _denied_text() -> str:
    return (
        "Доступ закрыт.\n\n"
        "Этот бот работает только для участников NOGA Systems.\n"
        "Обратитесь к Owner, чтобы вас добавили в систему."
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    settings: Settings,
    db_user: User | None,
    is_allowed: bool,
    session: AsyncSession,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied_text())
        return

    # Sync basic profile fields from Telegram
    if message.from_user:
        if message.from_user.username:
            db_user.username = message.from_user.username
        if message.from_user.first_name:
            db_user.first_name = message.from_user.first_name
            if db_user.display_name in ("Owner",) or not db_user.display_name:
                db_user.display_name = message.from_user.first_name
        await session.commit()

    webapp = WebAppInfo(url=settings.webapp_url)
    try:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="NOGA", web_app=webapp),
        )
    except Exception:
        pass

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть NOGA", web_app=webapp)]
        ]
    )
    role_label = ROLE_LABELS_RU.get(db_user.role, db_user.role.value)
    await message.answer(
        f"Добро пожаловать, <b>{db_user.display_name}</b>\n"
        f"Роль: <b>{role_label}</b>\n\n"
        f"Нажмите кнопку ниже, чтобы открыть личный кабинет.",
        reply_markup=kb,
    )


@router.message(Command("whoami"))
async def cmd_whoami(
    message: Message,
    db_user: User | None,
    is_allowed: bool,
) -> None:
    if not is_allowed or db_user is None:
        await message.answer(_denied_text())
        return
    role_label = ROLE_LABELS_RU.get(db_user.role, db_user.role.value)
    status = "активен" if db_user.status == UserStatus.active else "заблокирован"
    uname = f"@{db_user.username}" if db_user.username else "—"
    await message.answer(
        f"<b>{db_user.display_name}</b>\n"
        f"ID: <code>{db_user.telegram_id}</code>\n"
        f"Username: {uname}\n"
        f"Роль: {role_label}\n"
        f"Статус: {status}"
    )
