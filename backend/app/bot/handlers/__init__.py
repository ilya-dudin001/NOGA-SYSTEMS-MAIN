from __future__ import annotations

from aiogram import Router

from app.bot.handlers.start import router as start_router
from app.bot.handlers.users_cmd import router as users_router

router = Router(name="root")
router.include_router(start_router)
router.include_router(users_router)
