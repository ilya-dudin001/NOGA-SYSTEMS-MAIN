from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import chat as chat_api
from app.api import cities as cities_api
from app.api import dashboard as dashboard_api
from app.api import me as me_api
from app.api import nogas as nogas_api
from app.api import places as places_api
from app.api import razgruzy as razgruzy_api
from app.api import trubki as trubki_api
from app.api import users as users_api
from app.bot import create_bot, create_dispatcher, ensure_data_dir, run_polling
from app.config import get_settings
from app.db import SessionLocal, engine
from app.db import Base
from app.db.bootstrap import bootstrap_chat_rooms, bootstrap_owners
from app.services import chat as chat_service
from app.services import geocode as geocode_service
from app.services import nogas as nogas_service
from app.services.chat_broker import ChatBroker, ChatRateLimiter
from app.services.chat_notifications import run_notification_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("noga")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ensure_data_dir(settings.database_url)
    nogas_service.ensure_uploads_dir()

    # Create tables (Alembic preferred in prod; create_all is fine for SQLite bootstrap)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all не добавляет колонки в уже существующие таблицы SQLite
        await geocode_service.ensure_schema(conn)

    async with SessionLocal() as session:
        await bootstrap_owners(session, settings)
        await bootstrap_chat_rooms(session)

    app.state.settings = settings
    app.state.chat_broker = ChatBroker(settings.chat_sse_queue_size)
    app.state.chat_rate_limiter = ChatRateLimiter()
    bot = None
    poll_task: asyncio.Task | None = None
    chat_cleanup_task: asyncio.Task | None = None
    chat_notification_task: asyncio.Task | None = None

    async def _chat_cleanup_worker() -> None:
        while True:
            try:
                async with SessionLocal() as session:
                    deleted = await chat_service.cleanup_expired_events(
                        session, settings.chat_event_retention_days
                    )
                if deleted:
                    logger.info("chat.events.cleanup deleted=%s", deleted)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("chat.events.cleanup failed")
            await asyncio.sleep(60 * 60)

    if settings.chat_enabled:
        chat_cleanup_task = asyncio.create_task(
            _chat_cleanup_worker(), name="chat-event-cleanup"
        )

    notifications_enabled = (
        settings.chat_enabled and settings.chat_telegram_notifications_enabled
    )
    if settings.bot_polling_enabled or notifications_enabled:
        bot = create_bot(settings)
        app.state.bot = bot

    if settings.bot_polling_enabled and bot is not None:
        dp = create_dispatcher(settings)
        app.state.dp = dp

        async def _polling_safe() -> None:
            try:
                await run_polling(bot, dp)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Bot polling stopped with error (API keeps running)")

        poll_task = asyncio.create_task(_polling_safe(), name="bot-polling")

    if notifications_enabled and bot is not None:
        chat_notification_task = asyncio.create_task(
            run_notification_worker(bot, settings),
            name="chat-notifications",
        )

    logger.info(
        "API started bot_polling=%s chat_notifications=%s",
        settings.bot_polling_enabled,
        notifications_enabled,
    )

    try:
        yield
    finally:
        tasks = [
            task
            for task in (poll_task, chat_cleanup_task, chat_notification_task)
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await app.state.chat_broker.close()
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
    app.include_router(cities_api.router)
    app.include_router(nogas_api.router)
    app.include_router(razgruzy_api.router)
    app.include_router(trubki_api.router)
    app.include_router(chat_api.router)
    app.include_router(dashboard_api.router)
    app.include_router(places_api.router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
