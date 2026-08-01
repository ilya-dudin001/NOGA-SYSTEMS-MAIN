"""REST API и durable SSE внутреннего чата."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import bearer_scheme, get_current_user
from app.auth.jwt import decode_access_token
from app.auth.permissions import CHAT_DIRECT, CHAT_READ, CHAT_WRITE, has_permission
from app.config import Settings, get_settings
from app.db import SessionLocal, get_session
from app.db.models import User, UserStatus
from app.schemas import (
    ChatDirectCreateIn,
    ChatMentionOut,
    ChatMentionReadOut,
    ChatMessageOut,
    ChatPeerOut,
    ChatReadOut,
    ChatReadUpdateIn,
    ChatRoomOut,
    ChatRoomsListOut,
)
from app.services import chat as chat_service
from app.services.chat import ChatError
from app.services.chat_broker import (
    OVERFLOW,
    ChatBroker,
    ChatRateLimiter,
    ChatSubscription,
)

logger = logging.getLogger(__name__)


async def require_chat_enabled(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.chat_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Не найдено"},
        )


router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
    dependencies=[Depends(require_chat_enabled)],
)


def _raise_chat(exc: ChatError) -> None:
    raise HTTPException(
        status_code=chat_service.http_status_for(
            exc.code, status_code=exc.status_code
        ),
        detail={"code": exc.code, "message": exc.message},
    ) from exc


async def require_chat_user(permission: str, user: User) -> User:
    if not has_permission(user.role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CHAT_FORBIDDEN", "message": "Нет доступа к чату"},
        )
    return user


async def require_chat_read(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return await require_chat_user(CHAT_READ, user)


async def require_chat_write(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return await require_chat_user(CHAT_WRITE, user)


async def require_chat_direct(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return await require_chat_user(CHAT_DIRECT, user)


async def _publish_committed(request: Request, session: AsyncSession) -> None:
    event_ids = chat_service.consume_committed_event_ids(session)
    broker: ChatBroker = request.app.state.chat_broker
    for event_id in event_ids:
        try:
            await broker.publish(event_id)
        except Exception:
            # REST уже committed; durable catch-up доставит событие без broker.
            logger.exception("chat.sse.publish_failed event_id=%s", event_id)


async def _check_rate(
    request: Request,
    actor: User,
    action: str,
    *,
    limit: int,
    period_seconds: float,
) -> None:
    limiter: ChatRateLimiter = request.app.state.chat_rate_limiter
    if not await limiter.allow(
        action,
        actor.id,
        limit=limit,
        period_seconds=period_seconds,
    ):
        logger.warning("chat.rate_limited user_id=%s action=%s", actor.id, action)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "CHAT_RATE_LIMITED",
                "message": "Слишком много запросов. Попробуйте позже",
            },
        )


def _sse_frame(event_type: str, data: dict, event_id: Optional[int] = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(
        "data: "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    return "\n".join(lines) + "\n\n"


def _heartbeat_frame() -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return f": heartbeat {now}\n\n"


async def _authenticate_stream(
    credentials: Optional[HTTPAuthorizationCredentials],
    settings: Settings,
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing bearer token"},
        )
    try:
        payload = decode_access_token(credentials.credentials, settings)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or expired token"},
        ) from exc
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "User not found"},
            )
        if user.status != UserStatus.active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "BLOCKED", "message": "User is blocked"},
            )
        if not has_permission(user.role, CHAT_READ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "CHAT_FORBIDDEN", "message": "Нет доступа к чату"},
            )
        # Все scalar-поля загружены; stream хранит только detached snapshot.
        session.expunge(user)
        return user


async def _revalidate_stream(
    user_id: int, room_id: Optional[int]
) -> tuple[Optional[User], set[int]]:
    async with SessionLocal() as session:
        try:
            return await chat_service.stream_access(session, user_id, room_id)
        except ChatError:
            return None, set()


async def _chat_stream(
    request: Request,
    *,
    actor: User,
    room_id: Optional[int],
    cursor: Optional[int],
    subscription: ChatSubscription,
    broker: ChatBroker,
    limiter: ChatRateLimiter,
    settings: Settings,
):
    last_sent_id = cursor
    last_revalidation = time.monotonic()
    replayed = 0
    try:
        current_actor, room_ids = await _revalidate_stream(actor.id, room_id)
        if current_actor is None:
            yield _sse_frame(
                "access.revoked",
                {"event_id": None, "type": "access.revoked", "room_id": room_id, "data": {}},
            )
            return
        actor = current_actor

        async with SessionLocal() as session:
            earliest, latest = await chat_service.event_bounds(session)
            if (
                last_sent_id is not None
                and earliest is not None
                and last_sent_id < earliest - 1
            ):
                reset_cursor = int(latest or 0)
                logger.info(
                    "chat.sse.reset user_id=%s cursor=%s latest=%s",
                    actor.id,
                    last_sent_id,
                    reset_cursor,
                )
                yield _sse_frame(
                    "stream.reset",
                    {
                        "event_id": reset_cursor,
                        "type": "stream.reset",
                        "room_id": room_id,
                        "data": {"latest_event_id": reset_cursor},
                        "created_at": datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                    reset_cursor,
                )
                return
            if last_sent_id is None:
                last_sent_id = await chat_service.latest_stream_event_id(
                    session, user_id=actor.id, room_ids=room_ids
                )

        while True:
            async with SessionLocal() as session:
                events = await chat_service.stream_events_after(
                    session,
                    user_id=actor.id,
                    room_ids=room_ids,
                    after_id=last_sent_id or 0,
                )
            if not events:
                break
            for event in events:
                if event.id <= (last_sent_id or 0):
                    continue
                last_sent_id = event.id
                replayed += 1
                yield _sse_frame(
                    event.type,
                    chat_service.event_envelope(event, actor),
                    event.id,
                )
            if len(events) < 500:
                break
        if replayed:
            logger.info("chat.sse.replay user_id=%s count=%s", actor.id, replayed)

        while not await request.is_disconnected():
            try:
                queued = await asyncio.wait_for(
                    subscription.queue.get(),
                    timeout=settings.chat_sse_heartbeat_seconds,
                )
            except asyncio.TimeoutError:
                queued = None

            if queued is OVERFLOW:
                logger.warning("chat.sse.queue_overflow user_id=%s", actor.id)
                return

            now = time.monotonic()
            if now - last_revalidation >= settings.chat_sse_revalidate_seconds:
                current_actor, current_rooms = await _revalidate_stream(actor.id, room_id)
                if current_actor is None:
                    yield _sse_frame(
                        "access.revoked",
                        {
                            "event_id": None,
                            "type": "access.revoked",
                            "room_id": room_id,
                            "data": {},
                        },
                    )
                    return
                actor = current_actor
                room_ids = current_rooms
                last_revalidation = now

            if isinstance(queued, int) and queued > (last_sent_id or 0):
                async with SessionLocal() as session:
                    event = await chat_service.stream_event_by_id(
                        session,
                        event_id=queued,
                        user_id=actor.id,
                        room_ids=room_ids,
                    )
                if event is not None:
                    last_sent_id = event.id
                    yield _sse_frame(
                        event.type,
                        chat_service.event_envelope(event, actor),
                        event.id,
                    )

            if queued is None:
                # Heartbeat cadence также является durable DB catch-up на случай
                # временно пропущенной in-memory публикации.
                yield _heartbeat_frame()
                async with SessionLocal() as session:
                    events = await chat_service.stream_events_after(
                        session,
                        user_id=actor.id,
                        room_ids=room_ids,
                        after_id=last_sent_id or 0,
                    )
                for event in events:
                    if event.id <= (last_sent_id or 0):
                        continue
                    last_sent_id = event.id
                    yield _sse_frame(
                        event.type,
                        chat_service.event_envelope(event, actor),
                        event.id,
                    )
    except asyncio.CancelledError:
        raise
    finally:
        await broker.unsubscribe(subscription)
        await limiter.release_stream(actor.id)
        logger.info("chat.sse.disconnected user_id=%s", actor.id)


@router.get("/stream")
async def stream(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    room_id: Optional[int] = Query(default=None, ge=1),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    actor = await _authenticate_stream(credentials, settings)
    try:
        cursor = int(last_event_id) if last_event_id not in (None, "") else None
        if cursor is not None and cursor < 0:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_REQUEST", "message": "Некорректный Last-Event-ID"},
        ) from exc

    current_actor, _ = await _revalidate_stream(actor.id, room_id)
    if current_actor is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CHAT_ROOM_FORBIDDEN", "message": "Нет доступа к комнате"},
        )

    limiter: ChatRateLimiter = request.app.state.chat_rate_limiter
    if not await limiter.acquire_stream(
        actor.id, limit=settings.chat_sse_max_streams_per_user
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "CHAT_RATE_LIMITED",
                "message": "Слишком много подключений к чату",
            },
        )
    broker: ChatBroker = request.app.state.chat_broker
    try:
        subscription = await broker.subscribe(actor.id)
    except Exception:
        await limiter.release_stream(actor.id)
        raise

    logger.info("chat.sse.connected user_id=%s room_id=%s", actor.id, room_id)
    return StreamingResponse(
        _chat_stream(
            request,
            actor=actor,
            room_id=room_id,
            cursor=cursor,
            subscription=subscription,
            broker=broker,
            limiter=limiter,
            settings=settings,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/rooms", response_model=ChatRoomsListOut)
async def list_rooms(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
) -> ChatRoomsListOut:
    try:
        data = await chat_service.list_rooms(session, actor)
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return ChatRoomsListOut.model_validate(data)


@router.get("/peers", response_model=list[ChatPeerOut])
async def list_peers(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_direct)],
) -> list[ChatPeerOut]:
    try:
        rows = await chat_service.list_peers(session, actor)
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return [ChatPeerOut.model_validate(r) for r in rows]


@router.post("/direct", response_model=ChatRoomOut)
async def create_direct(
    body: ChatDirectCreateIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_direct)],
    response: Response,
) -> ChatRoomOut:
    settings = get_settings()
    await _check_rate(
        request,
        actor,
        "direct",
        limit=settings.chat_rate_directs_per_minute,
        period_seconds=60,
    )
    try:
        room, created = await chat_service.get_or_create_direct(
            session, actor, body.peer_user_id
        )
        data = chat_service.room_to_direct_out(room, actor)
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ChatRoomOut.model_validate(data)


@router.get("/rooms/{room_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    room_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
    before_id: Optional[int] = Query(default=None, ge=1),
    around_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ChatMessageOut]:
    try:
        rows = await chat_service.list_messages(
            session,
            actor,
            room_id,
            before_id=before_id,
            around_id=around_id,
            limit=limit,
        )
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return [ChatMessageOut.model_validate(r) for r in rows]


@router.post(
    "/rooms/{room_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    room_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_write)],
    content: Annotated[str, Form()],
    reply_to_id: Annotated[Optional[int], Form()] = None,
    files: Annotated[Optional[list[UploadFile]], File()] = None,
) -> ChatMessageOut:
    staged: list[chat_service.StagedFile] = []
    try:
        settings = get_settings()
        await _check_rate(
            request,
            actor,
            "message",
            limit=settings.chat_rate_messages_per_minute,
            period_seconds=60,
        )
        try:
            content_raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения") from exc

        # Staging вне write-lock: файлы читаются чанками во временный каталог.
        staged = await chat_service.stage_uploads(files or [])
        if staged:
            await _check_rate(
                request,
                actor,
                "upload",
                limit=settings.chat_rate_uploads_per_10_minutes,
                period_seconds=600,
            )
        data = await chat_service.create_message(
            session,
            actor,
            room_id,
            content_raw=content_raw,
            reply_to_id=reply_to_id,
            staged_files=staged,
        )
        await _publish_committed(request, session)
        logger.info(
            "chat.message.created user_id=%s room_id=%s message_id=%s files=%s",
            actor.id,
            room_id,
            data.get("id"),
            len(staged),
        )
    except ChatError as exc:
        chat_service.discard_pending_event_ids(session)
        chat_service.cleanup_staged(staged)
        _raise_chat(exc)
        raise  # pragma: no cover
    except Exception:
        chat_service.discard_pending_event_ids(session)
        chat_service.cleanup_staged(staged)
        raise
    return ChatMessageOut.model_validate(data)


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
) -> FileResponse:
    try:
        attachment, path = await chat_service.resolve_attachment_download(
            session, actor, attachment_id
        )
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=attachment.original_name,
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_message(
    message_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_write)],
) -> None:
    try:
        deleted = await chat_service.soft_delete_message(session, actor, message_id)
        await _publish_committed(request, session)
        if deleted:
            logger.info(
                "chat.message.deleted user_id=%s message_id=%s",
                actor.id,
                message_id,
            )
    except ChatError as exc:
        chat_service.discard_pending_event_ids(session)
        _raise_chat(exc)


@router.patch("/rooms/{room_id}/read", response_model=ChatReadOut)
async def update_read(
    room_id: int,
    body: ChatReadUpdateIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
) -> ChatReadOut:
    try:
        data = await chat_service.update_read_cursor(
            session,
            actor,
            room_id,
            last_read_message_id=body.last_read_message_id,
        )
        await _publish_committed(request, session)
    except ChatError as exc:
        chat_service.discard_pending_event_ids(session)
        _raise_chat(exc)
        raise  # pragma: no cover
    return ChatReadOut.model_validate(data)


@router.get("/mentions", response_model=list[ChatMentionOut])
async def list_mentions(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ChatMentionOut]:
    try:
        rows = await chat_service.list_mentions(
            session, actor, unread_only=unread_only, limit=limit
        )
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return [ChatMentionOut.model_validate(r) for r in rows]


@router.patch("/mentions/{mention_id}/read", response_model=ChatMentionReadOut)
async def read_mention(
    mention_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_read)],
) -> ChatMentionReadOut:
    try:
        data = await chat_service.mark_mention_read(session, actor, mention_id)
    except ChatError as exc:
        _raise_chat(exc)
        raise  # pragma: no cover
    return ChatMentionReadOut.model_validate(data)
