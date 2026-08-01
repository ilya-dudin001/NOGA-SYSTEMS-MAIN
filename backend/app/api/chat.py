"""REST API внутреннего чата (без SSE — этап 4)."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.permissions import CHAT_DIRECT, CHAT_READ, CHAT_WRITE, has_permission
from app.config import Settings, get_settings
from app.db import get_session
from app.db.models import User
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
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_direct)],
    response: Response,
) -> ChatRoomOut:
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
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_write)],
    content: Annotated[str, Form()],
    reply_to_id: Annotated[Optional[int], Form()] = None,
    files: Annotated[Optional[list[UploadFile]], File()] = None,
) -> ChatMessageOut:
    staged: list[chat_service.StagedFile] = []
    try:
        try:
            content_raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения") from exc

        # Staging вне write-lock: файлы читаются чанками во временный каталог.
        staged = await chat_service.stage_uploads(files or [])
        data = await chat_service.create_message(
            session,
            actor,
            room_id,
            content_raw=content_raw,
            reply_to_id=reply_to_id,
            staged_files=staged,
        )
    except ChatError as exc:
        chat_service.cleanup_staged(staged)
        _raise_chat(exc)
        raise  # pragma: no cover
    except Exception:
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
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_chat_write)],
) -> None:
    try:
        await chat_service.soft_delete_message(session, actor, message_id)
    except ChatError as exc:
        _raise_chat(exc)


@router.patch("/rooms/{room_id}/read", response_model=ChatReadOut)
async def update_read(
    room_id: int,
    body: ChatReadUpdateIn,
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
    except ChatError as exc:
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
