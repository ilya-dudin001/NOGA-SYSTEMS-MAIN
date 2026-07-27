from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import dashboard as dashboard_api
from app.api import me as me_api
from app.api import users as users_api
from app.bot import create_bot, create_dispatcher, ensure_data_dir, run_polling
from app.config import get_settings
from app.db import SessionLocal, engine
from app.db import Base
from app.db.bootstrap import bootstrap_owners

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("noga")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ensure_data_dir(settings.database_url)

    # Create tables (Alembic preferred in prod; create_all is fine for SQLite bootstrap)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await bootstrap_owners(session, settings)

    app.state.settings = settings
    bot = None
    poll_task: asyncio.Task | None = None

    if settings.bot_polling_enabled:
        bot = create_bot(settings)
        dp = create_dispatcher(settings)
        app.state.bot = bot
        app.state.dp = dp

        async def _polling_safe() -> None:
            try:
                await run_polling(bot, dp)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Bot polling stopped with error (API keeps running)")

        poll_task = asyncio.create_task(_polling_safe(), name="bot-polling")
        logger.info("API + bot started")
    else:
        logger.info("API started (bot polling disabled)")

    try:
        yield
    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
        if bot is not None:
            await bot.session.close()
        await engine.dispose()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NOGA Systems API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_api.router)
    app.include_router(me_api.router)
    app.include_router(users_api.router)
    app.include_router(dashboard_api.router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
