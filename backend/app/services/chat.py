"""Доменный слой внутреннего чата: доступ, content, unread, события (без broker)."""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from sqlalchemy import Select, and_, func, inspect as sa_inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth.permissions import (
    CHAT_DELETE_ANY,
    CHAT_DELETE_OWN,
    CHAT_DIRECT,
    CHAT_READ,
    CHAT_WRITE,
    ROLE_LABELS_RU,
    has_permission,
)
from app.config import get_settings
from app.db.models import (
    ChatAttachment,
    ChatEvent,
    ChatMention,
    ChatMessage,
    ChatRead,
    ChatRoom,
    ChatRoomKind,
    ChatRoomMember,
    ChatTelegramStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

INTERNAL_ROLES = frozenset({UserRole.owner, UserRole.right_hand, UserRole.admin})
PREVIEW_MAX = 160
DELETED_PREVIEW = "Сообщение удалено"
CHUNK_BYTES = 1024 * 1024
CHAT_STORAGE_PREFIX = "chat"
CHAT_STAGING_PREFIX = "chat/_staging"

# Подменяемые в тестах лимиты (не создавать 100 МБ fixture).
_UPLOAD_MAX_TOTAL_BYTES_OVERRIDE: Optional[int] = None
_UPLOAD_MAX_COUNT_OVERRIDE: Optional[int] = None


class ChatError(Exception):
    """Бизнес-ошибка чата → HTTP detail {code, message}."""

    def __init__(
        self, code: str, message: str, *, status_code: Optional[int] = None
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


CHAT_HTTP_STATUS: dict[str, int] = {
    "CHAT_EMPTY_MESSAGE": 400,
    "CHAT_TEXT_TOO_LONG": 400,
    "CHAT_TOO_MANY_FILES": 400,
    "CHAT_FILES_TOO_LARGE": 413,
    "CHAT_BAD_CONTENT": 400,
    "CHAT_SELF_DIRECT": 400,
    "CHAT_FORBIDDEN": 403,
    "CHAT_ROOM_FORBIDDEN": 403,
    "CHAT_PEER_FORBIDDEN": 403,
    "CHAT_DELETE_FORBIDDEN": 403,
    "CHAT_ROOM_NOT_FOUND": 404,
    "CHAT_MESSAGE_NOT_FOUND": 404,
    "CHAT_ATTACHMENT_NOT_FOUND": 404,
    "CHAT_MENTION_NOT_FOUND": 404,
    "CHAT_ROOM_INACTIVE": 409,
    "CHAT_DIRECT_UNAVAILABLE": 409,
    "CHAT_RATE_LIMITED": 429,
}


def http_status_for(code: str, *, status_code: Optional[int] = None) -> int:
    if status_code is not None:
        return status_code
    return CHAT_HTTP_STATUS.get(code, 400)


def uploads_root() -> Path:
    return Path(get_settings().uploads_dir).resolve()


def upload_max_total_bytes() -> int:
    if _UPLOAD_MAX_TOTAL_BYTES_OVERRIDE is not None:
        return _UPLOAD_MAX_TOTAL_BYTES_OVERRIDE
    return get_settings().chat_upload_max_total_mb * 1024 * 1024


def upload_max_count() -> int:
    if _UPLOAD_MAX_COUNT_OVERRIDE is not None:
        return _UPLOAD_MAX_COUNT_OVERRIDE
    return get_settings().chat_files_max_count


@dataclass
class StagedFile:
    temp_path: Path
    staging_dir: Path
    original_name: str
    content_type: str
    size_bytes: int


def safe_original_name(filename: Optional[str]) -> str:
    """Имя для metadata/Content-Disposition; в filesystem path не идёт."""
    name = Path(filename or "file").name.replace("\x00", "").strip() or "file"
    return name[:255]


def absolute_stored_path(stored_path: str) -> Path:
    return uploads_root() / stored_path


def ensure_under_chat_root(path: Path) -> Path:
    """Гарантирует, что путь лежит в UPLOADS_DIR/chat (не staging)."""
    resolved = path.resolve()
    chat_root = (uploads_root() / CHAT_STORAGE_PREFIX).resolve()
    try:
        resolved.relative_to(chat_root)
    except ValueError as exc:
        raise ChatError(
            "CHAT_ATTACHMENT_NOT_FOUND", "Вложение не найдено"
        ) from exc
    if "_staging" in resolved.parts:
        raise ChatError("CHAT_ATTACHMENT_NOT_FOUND", "Вложение не найдено")
    return resolved


def cleanup_staged(staged: Sequence[StagedFile]) -> None:
    dirs: set[Path] = set()
    for item in staged:
        dirs.add(item.staging_dir)
        try:
            item.temp_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove staged chat file %s", item.temp_path)
    for directory in dirs:
        shutil.rmtree(directory, ignore_errors=True)


def delete_stored_files(stored_paths: Sequence[str]) -> None:
    """Удаляет файлы после commit. Ошибки только в лог."""
    parents: set[Path] = set()
    for stored in stored_paths:
        try:
            path = absolute_stored_path(stored)
            ensure_under_chat_root(path)
            parents.add(path.parent)
            path.unlink(missing_ok=True)
        except ChatError:
            logger.warning("Skip deleting unsafe chat path %s", stored)
        except OSError:
            logger.exception("Failed to delete chat attachment %s", stored)
    for parent in parents:
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
            grand = parent.parent
            if grand.is_dir() and not any(grand.iterdir()):
                grand.rmdir()
        except OSError:
            logger.exception("Failed to remove empty chat dir %s", parent)


async def stage_uploads(uploads: Sequence[Any]) -> list[StagedFile]:
    """Пишет UploadFile во временный каталог, проверяя лимиты по чанкам."""
    candidates = [u for u in uploads if getattr(u, "filename", None)]
    max_count = upload_max_count()
    if len(candidates) > max_count:
        raise ChatError(
            "CHAT_TOO_MANY_FILES",
            f"Не больше {max_count} файлов в одном сообщении",
        )

    max_total = upload_max_total_bytes()
    staging_dir = uploads_root() / CHAT_STAGING_PREFIX / uuid.uuid4().hex
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged: list[StagedFile] = []
    total = 0
    try:
        for upload in candidates:
            original_name = safe_original_name(upload.filename)
            declared = getattr(upload, "content_type", None) or "application/octet-stream"
            content_type = str(declared)[:120] or "application/octet-stream"
            temp_path = staging_dir / uuid.uuid4().hex
            size = 0
            with temp_path.open("wb") as out:
                while True:
                    chunk = await upload.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    size += len(chunk)
                    total += len(chunk)
                    if total > max_total:
                        raise ChatError(
                            "CHAT_FILES_TOO_LARGE",
                            "Суммарный размер файлов превышает лимит",
                            status_code=413,
                        )
                    out.write(chunk)
            if size == 0:
                temp_path.unlink(missing_ok=True)
                continue
            staged.append(
                StagedFile(
                    temp_path=temp_path,
                    staging_dir=staging_dir,
                    original_name=original_name,
                    content_type=content_type,
                    size_bytes=size,
                )
            )
        if not staged:
            shutil.rmtree(staging_dir, ignore_errors=True)
        return staged
    except Exception:
        cleanup_staged(staged)
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def commit_staged_file(
    room_id: int, message_id: int, staged: StagedFile
) -> str:
    """Переносит файл из staging в конечный каталог. Возвращает relative stored_path."""
    relative = Path(CHAT_STORAGE_PREFIX) / str(room_id) / str(message_id) / uuid.uuid4().hex
    target = uploads_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged.temp_path), str(target))
    return relative.as_posix()


def direct_key(user_a: int, user_b: int) -> str:
    lo, hi = (user_a, user_b) if user_a < user_b else (user_b, user_a)
    return f"{lo}:{hi}"


def is_chat_eligible(user: User, *, need_write: bool = False) -> bool:
    if user.status != UserStatus.active:
        return False
    if user.role not in INTERNAL_ROLES:
        return False
    if not has_permission(user.role, CHAT_READ):
        return False
    if need_write and not has_permission(user.role, CHAT_WRITE):
        return False
    return True


def can_delete_message(actor: User, message: ChatMessage) -> bool:
    if message.deleted_at is not None:
        return False
    if has_permission(actor.role, CHAT_DELETE_ANY):
        return True
    if has_permission(actor.role, CHAT_DELETE_OWN) and message.author_id == actor.id:
        return True
    return False


def preview_text(body: Optional[str], *, has_attachments: bool, is_deleted: bool) -> str:
    if is_deleted:
        return DELETED_PREVIEW
    text = (body or "").strip()
    if text:
        if len(text) > PREVIEW_MAX:
            return text[: PREVIEW_MAX - 1] + "…"
        return text
    if has_attachments:
        return "Вложение"
    return ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Content parts
# ---------------------------------------------------------------------------


def normalize_content(
    raw: Any,
    *,
    mention_users: dict[int, User],
    max_chars: int,
) -> tuple[list[dict[str, Any]], str, list[int]]:
    """Нормализует content parts → (content, body, unique mention user ids)."""
    if raw is None:
        raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")
    if not isinstance(raw, list):
        raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")

    parts: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")
        kind = item.get("type")
        if kind == "text":
            text = item.get("text")
            if text is None:
                raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")
            if not isinstance(text, str):
                raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")
            if not text:
                continue
            if parts and parts[-1]["type"] == "text":
                parts[-1]["text"] = parts[-1]["text"] + text
            else:
                parts.append({"type": "text", "text": text})
        elif kind == "mention":
            uid = item.get("user_id")
            if not isinstance(uid, int) or isinstance(uid, bool):
                raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")
            user = mention_users.get(uid)
            if user is None:
                raise ChatError(
                    "CHAT_PEER_FORBIDDEN",
                    "Упомянутый пользователь недоступен в этой комнате",
                )
            parts.append(
                {
                    "type": "mention",
                    "user_id": user.id,
                    "label": user.display_name,
                }
            )
        else:
            raise ChatError("CHAT_BAD_CONTENT", "Некорректные части сообщения")

    body_chunks: list[str] = []
    mention_ids: list[int] = []
    seen: set[int] = set()
    for part in parts:
        if part["type"] == "text":
            body_chunks.append(part["text"])
        else:
            body_chunks.append("@" + part["label"])
            uid = int(part["user_id"])
            if uid not in seen:
                seen.add(uid)
                mention_ids.append(uid)

    body = "".join(body_chunks)
    if len(body) > max_chars:
        raise ChatError(
            "CHAT_TEXT_TOO_LONG",
            f"Текст сообщения длиннее {max_chars} символов",
        )
    return parts, body, mention_ids


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


async def load_room(session: AsyncSession, room_id: int) -> Optional[ChatRoom]:
    return await session.scalar(
        select(ChatRoom)
        .where(ChatRoom.id == room_id)
        .options(selectinload(ChatRoom.members).selectinload(ChatRoomMember.user))
        .execution_options(populate_existing=True)
    )


async def user_is_direct_member(session: AsyncSession, room_id: int, user_id: int) -> bool:
    mid = await session.scalar(
        select(ChatRoomMember.id).where(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id,
        )
    )
    return mid is not None


async def assert_room_access(
    session: AsyncSession,
    actor: User,
    room: ChatRoom,
    *,
    need_write: bool = False,
) -> None:
    if not is_chat_eligible(actor, need_write=need_write):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")
    if not room.is_active:
        raise ChatError("CHAT_ROOM_INACTIVE", "Комната отключена")

    if room.kind == ChatRoomKind.system:
        return

    if room.kind == ChatRoomKind.direct:
        if not await user_is_direct_member(session, room.id, actor.id):
            raise ChatError("CHAT_ROOM_FORBIDDEN", "Нет доступа к этой комнате")
        if need_write:
            members = list(room.members)
            if len(members) != 2:
                raise ChatError(
                    "CHAT_DIRECT_UNAVAILABLE",
                    "Собеседник больше недоступен для переписки",
                )
            peers = [member.user for member in members if member.user_id != actor.id]
            if (
                len(peers) != 1
                or not is_chat_eligible(peers[0], need_write=True)
            ):
                raise ChatError(
                    "CHAT_DIRECT_UNAVAILABLE",
                    "Собеседник больше недоступен для переписки",
                )
        return

    raise ChatError("CHAT_ROOM_FORBIDDEN", "Нет доступа к этой комнате")


async def require_room(
    session: AsyncSession,
    actor: User,
    room_id: int,
    *,
    need_write: bool = False,
) -> ChatRoom:
    room = await load_room(session, room_id)
    if room is None:
        raise ChatError("CHAT_ROOM_NOT_FOUND", "Комната не найдена")
    await assert_room_access(session, actor, room, need_write=need_write)
    return room


async def find_direct_peer(
    session: AsyncSession, room: ChatRoom, actor_id: int
) -> Optional[User]:
    if "members" not in sa_inspect(room).unloaded:
        for member in room.members:
            if member.user_id != actor_id:
                return member.user
    # Для объектов из join без eager load не обращаемся к lazy="raise".
    row = await session.scalar(
        select(ChatRoomMember)
        .where(
            ChatRoomMember.room_id == room.id,
            ChatRoomMember.user_id != actor_id,
        )
        .options(selectinload(ChatRoomMember.user))
    )
    return row.user if row is not None else None


async def mentionable_users(
    session: AsyncSession, actor: User, room: ChatRoom
) -> list[User]:
    """Кого можно упомянуть в комнате (включая себя — UI обычно фильтрует)."""
    await assert_room_access(session, actor, room)
    if room.kind == ChatRoomKind.system:
        result = await session.execute(
            select(User)
            .where(
                User.status == UserStatus.active,
                User.role.in_(tuple(INTERNAL_ROLES)),
            )
            .order_by(User.display_name.asc(), User.id.asc())
        )
        users = list(result.scalars().all())
        return [u for u in users if has_permission(u.role, CHAT_READ)]

    # direct — только двое участников
    result = await session.execute(
        select(User)
        .join(ChatRoomMember, ChatRoomMember.user_id == User.id)
        .where(ChatRoomMember.room_id == room.id)
        .order_by(User.display_name.asc(), User.id.asc())
    )
    return [user for user in result.scalars().all() if is_chat_eligible(user)]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def append_event(
    session: AsyncSession,
    *,
    type: str,
    payload: dict[str, Any],
    room_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
) -> ChatEvent:
    event = ChatEvent(
        type=type,
        payload=payload,
        room_id=room_id,
        target_user_id=target_user_id,
    )
    session.add(event)
    await session.flush()
    return event


async def latest_event_id_for_user(session: AsyncSession, actor: User) -> Optional[int]:
    room_ids = await accessible_room_ids(session, actor)
    if not room_ids:
        targeted = await session.scalar(
            select(func.max(ChatEvent.id)).where(ChatEvent.target_user_id == actor.id)
        )
        return int(targeted) if targeted is not None else None

    stmt = select(func.max(ChatEvent.id)).where(
        or_(
            ChatEvent.target_user_id == actor.id,
            and_(
                ChatEvent.target_user_id.is_(None),
                ChatEvent.room_id.in_(room_ids),
            ),
        )
    )
    value = await session.scalar(stmt)
    return int(value) if value is not None else None


async def accessible_room_ids(session: AsyncSession, actor: User) -> list[int]:
    if not is_chat_eligible(actor):
        return []
    system_ids = list(
        (
            await session.execute(
                select(ChatRoom.id).where(
                    ChatRoom.kind == ChatRoomKind.system,
                    ChatRoom.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    direct_ids = list(
        (
            await session.execute(
                select(ChatRoom.id)
                .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
                .where(
                    ChatRoom.kind == ChatRoomKind.direct,
                    ChatRoom.is_active.is_(True),
                    ChatRoomMember.user_id == actor.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return system_ids + direct_ids


# ---------------------------------------------------------------------------
# Unread
# ---------------------------------------------------------------------------


async def unread_count_for_room(
    session: AsyncSession, *, room_id: int, user_id: int, last_read_id: Optional[int]
) -> int:
    conditions = [
        ChatMessage.room_id == room_id,
        ChatMessage.deleted_at.is_(None),
        or_(ChatMessage.author_id.is_(None), ChatMessage.author_id != user_id),
    ]
    if last_read_id is not None:
        conditions.append(ChatMessage.id > last_read_id)
    value = await session.scalar(select(func.count()).select_from(ChatMessage).where(*conditions))
    return int(value or 0)


async def unread_mentions_for_room(
    session: AsyncSession, *, room_id: int, user_id: int
) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(ChatMention)
        .join(ChatMessage, ChatMessage.id == ChatMention.message_id)
        .where(
            ChatMention.user_id == user_id,
            ChatMention.read_at.is_(None),
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None),
        )
    )
    return int(value or 0)


async def get_read_cursor(
    session: AsyncSession, *, room_id: int, user_id: int
) -> Optional[ChatRead]:
    return await session.scalar(
        select(ChatRead)
        .where(ChatRead.room_id == room_id, ChatRead.user_id == user_id)
        .execution_options(populate_existing=True)
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

MESSAGE_LOAD = (
    selectinload(ChatMessage.attachments),
    selectinload(ChatMessage.reply_to).selectinload(ChatMessage.attachments),
)


async def load_message(session: AsyncSession, message_id: int) -> Optional[ChatMessage]:
    return await session.scalar(
        select(ChatMessage)
        .where(ChatMessage.id == message_id)
        .options(*MESSAGE_LOAD)
        .execution_options(populate_existing=True)
    )


def attachment_to_dict(att: Any) -> dict[str, Any]:
    return {
        "id": att.id,
        "original_name": att.original_name,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
    }


def message_to_dict(message: ChatMessage, *, actor: User) -> dict[str, Any]:
    is_deleted = message.deleted_at is not None
    reply_dict = None
    if message.reply_to_id is not None and message.reply_to is not None:
        reply = message.reply_to
        reply_deleted = reply.deleted_at is not None
        reply_has_files = bool(reply.attachments) and not reply_deleted
        reply_dict = {
            "id": reply.id,
            "author_name": reply.author_name,
            "preview": preview_text(
                reply.body, has_attachments=reply_has_files, is_deleted=reply_deleted
            ),
            "is_deleted": reply_deleted,
        }
    elif message.reply_to_id is not None:
        reply_dict = {
            "id": message.reply_to_id,
            "author_name": "",
            "preview": DELETED_PREVIEW,
            "is_deleted": True,
        }

    author_id = message.author_id
    author_name = message.author_name
    return {
        "id": message.id,
        "room_id": message.room_id,
        "author": {
            "id": author_id,
            "display_name": author_name,
            "is_current_user": author_id is not None and author_id == actor.id,
        },
        "content": [] if is_deleted else list(message.content or []),
        "reply": reply_dict,
        "attachments": []
        if is_deleted
        else [attachment_to_dict(a) for a in (message.attachments or [])],
        "is_deleted": is_deleted,
        "can_delete": can_delete_message(actor, message),
        "created_at": message.created_at,
    }


def last_message_preview(message: ChatMessage) -> dict[str, Any]:
    is_deleted = message.deleted_at is not None
    has_files = bool(message.attachments) and not is_deleted
    return {
        "id": message.id,
        "author_name": message.author_name,
        "preview": preview_text(
            message.body, has_attachments=has_files, is_deleted=is_deleted
        ),
        "has_attachments": has_files,
        "created_at": message.created_at,
    }


# ---------------------------------------------------------------------------
# Rooms / peers / direct
# ---------------------------------------------------------------------------


async def list_rooms(session: AsyncSession, actor: User) -> dict[str, Any]:
    if not is_chat_eligible(actor):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")

    system_rooms = list(
        (
            await session.execute(
                select(ChatRoom)
                .where(
                    ChatRoom.kind == ChatRoomKind.system,
                    ChatRoom.is_active.is_(True),
                )
                .order_by(ChatRoom.sort_order.asc(), ChatRoom.id.asc())
            )
        )
        .scalars()
        .all()
    )

    direct_rooms = list(
        (
            await session.execute(
                select(ChatRoom)
                .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
                .where(
                    ChatRoom.kind == ChatRoomKind.direct,
                    ChatRoom.is_active.is_(True),
                    ChatRoomMember.user_id == actor.id,
                )
                .options(selectinload(ChatRoom.members).selectinload(ChatRoomMember.user))
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    rooms_out: list[dict[str, Any]] = []
    total_unread = 0
    total_unread_mentions = 0

    async def build_room_card(room: ChatRoom) -> dict[str, Any]:
        nonlocal total_unread, total_unread_mentions
        read = await get_read_cursor(session, room_id=room.id, user_id=actor.id)
        last_read_id = read.last_read_message_id if read else None
        unread = await unread_count_for_room(
            session, room_id=room.id, user_id=actor.id, last_read_id=last_read_id
        )
        unread_m = await unread_mentions_for_room(
            session, room_id=room.id, user_id=actor.id
        )
        total_unread += unread
        total_unread_mentions += unread_m

        last = await session.scalar(
            select(ChatMessage)
            .where(ChatMessage.room_id == room.id)
            .options(selectinload(ChatMessage.attachments))
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )

        peer = None
        title = room.title
        if room.kind == ChatRoomKind.direct:
            other = await find_direct_peer(session, room, actor.id)
            if other is not None:
                peer = {
                    "id": other.id,
                    "display_name": other.display_name,
                    "username": other.username,
                    "role": other.role,
                }
                title = other.display_name
            else:
                title = "Диалог"

        return {
            "id": room.id,
            "kind": room.kind,
            "slug": room.slug,
            "title": title,
            "peer": peer,
            "unread_count": unread,
            "unread_mentions": unread_m,
            "last_message": last_message_preview(last) if last is not None else None,
            "last_message_id": last.id if last is not None else None,
            "created_at": room.created_at,
        }

    for room in system_rooms:
        rooms_out.append(await build_room_card(room))

    direct_cards: list[dict[str, Any]] = []
    for room in direct_rooms:
        direct_cards.append(await build_room_card(room))

    def direct_sort_key(card: dict[str, Any]) -> tuple:
        # новее сверху: last_message_id desc, иначе created_at desc
        last_id = card.get("last_message_id") or 0
        created = card.get("created_at") or datetime.min.replace(tzinfo=timezone.utc)
        return (-int(last_id), -created.timestamp())

    direct_cards.sort(key=direct_sort_key)
    rooms_out.extend(direct_cards)

    for card in rooms_out:
        card.pop("last_message_id", None)
        card.pop("created_at", None)

    return {
        "latest_event_id": await latest_event_id_for_user(session, actor),
        "total_unread": total_unread,
        "total_unread_mentions": total_unread_mentions,
        "rooms": rooms_out,
    }


async def list_peers(session: AsyncSession, actor: User) -> list[dict[str, Any]]:
    if not is_chat_eligible(actor) or not has_permission(actor.role, CHAT_DIRECT):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")

    result = await session.execute(
        select(User)
        .where(
            User.id != actor.id,
            User.status == UserStatus.active,
            User.role.in_(tuple(INTERNAL_ROLES)),
        )
        .order_by(User.display_name.asc(), User.id.asc())
    )
    peers = [u for u in result.scalars().all() if has_permission(u.role, CHAT_READ)]

    out: list[dict[str, Any]] = []
    for peer in peers:
        key = direct_key(actor.id, peer.id)
        room_id = await session.scalar(
            select(ChatRoom.id).where(
                ChatRoom.kind == ChatRoomKind.direct,
                ChatRoom.is_active.is_(True),
                ChatRoom.direct_key == key,
            )
        )
        out.append(
            {
                "id": peer.id,
                "display_name": peer.display_name,
                "username": peer.username,
                "role": peer.role,
                "role_label": ROLE_LABELS_RU.get(peer.role, peer.role.value),
                "room_id": room_id,
            }
        )
    return out


async def get_or_create_direct(
    session: AsyncSession, actor: User, peer_user_id: int
) -> tuple[ChatRoom, bool]:
    """Возвращает (room, created)."""
    if not is_chat_eligible(actor) or not has_permission(actor.role, CHAT_DIRECT):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")
    if peer_user_id == actor.id:
        raise ChatError("CHAT_SELF_DIRECT", "Нельзя создать диалог с собой")

    peer = await session.scalar(select(User).where(User.id == peer_user_id))
    if peer is None or not is_chat_eligible(peer, need_write=True):
        raise ChatError("CHAT_PEER_FORBIDDEN", "Собеседник недоступен для чата")

    key = direct_key(actor.id, peer.id)
    existing = await session.scalar(
        select(ChatRoom)
        .where(ChatRoom.direct_key == key)
        .options(selectinload(ChatRoom.members).selectinload(ChatRoomMember.user))
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        _validate_existing_direct(existing, actor_id=actor.id, peer_id=peer.id)
        return existing, False

    dialect = session.get_bind().dialect.name
    insert_factory = (
        sqlite_insert if dialect == "sqlite" else postgresql_insert
        if dialect == "postgresql" else None
    )
    if insert_factory is not None:
        insert_stmt = (
            insert_factory(ChatRoom)
            .values(
                kind=ChatRoomKind.direct,
                slug=None,
                title=None,
                direct_key=key,
                is_active=True,
                sort_order=0,
            )
            .on_conflict_do_nothing(index_elements=[ChatRoom.direct_key])
            .returning(ChatRoom.id)
        )
        room_id = await session.scalar(insert_stmt)
        if room_id is None:
            existing = await session.scalar(
                select(ChatRoom)
                .where(ChatRoom.direct_key == key)
                .options(
                    selectinload(ChatRoom.members).selectinload(ChatRoomMember.user)
                )
                .execution_options(populate_existing=True)
            )
            if existing is None:
                raise ChatError(
                    "CHAT_DIRECT_UNAVAILABLE",
                    "Не удалось получить созданный диалог",
                )
            _validate_existing_direct(existing, actor_id=actor.id, peer_id=peer.id)
            return existing, False
        room = await session.scalar(select(ChatRoom).where(ChatRoom.id == room_id))
        assert room is not None
    else:
        room = ChatRoom(
            kind=ChatRoomKind.direct,
            slug=None,
            title=None,
            direct_key=key,
            is_active=True,
            sort_order=0,
        )
        session.add(room)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(ChatRoom)
                .where(ChatRoom.direct_key == key)
                .options(
                    selectinload(ChatRoom.members).selectinload(ChatRoomMember.user)
                )
                .execution_options(populate_existing=True)
            )
            if existing is None:
                raise
            _validate_existing_direct(existing, actor_id=actor.id, peer_id=peer.id)
            return existing, False

    session.add(ChatRoomMember(room_id=room.id, user_id=actor.id))
    session.add(ChatRoomMember(room_id=room.id, user_id=peer.id))
    await write_audit(
        session,
        action="chat.direct.created",
        actor_user_id=actor.id,
        target_type="chat_room",
        target_id=str(room.id),
        payload={
            "room_id": room.id,
            "kind": room.kind.value,
            "peer_user_id": peer.id,
        },
    )
    await session.commit()
    room = await load_room(session, room.id)
    assert room is not None
    return room, True


def _validate_existing_direct(
    room: ChatRoom, *, actor_id: int, peer_id: int
) -> None:
    if not room.is_active:
        raise ChatError("CHAT_ROOM_INACTIVE", "Комната отключена")
    if {member.user_id for member in room.members} != {actor_id, peer_id}:
        raise ChatError(
            "CHAT_DIRECT_UNAVAILABLE",
            "Состав участников диалога повреждён",
        )


def room_to_direct_out(room: ChatRoom, actor: User) -> dict[str, Any]:
    peer = None
    title = room.title
    for member in room.members:
        if member.user_id != actor.id:
            peer = {
                "id": member.user.id,
                "display_name": member.user.display_name,
                "username": member.user.username,
                "role": member.user.role,
            }
            title = member.user.display_name
            break
    return {
        "id": room.id,
        "kind": room.kind,
        "slug": room.slug,
        "title": title or "Диалог",
        "peer": peer,
        "unread_count": 0,
        "unread_mentions": 0,
        "last_message": None,
    }


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def list_messages(
    session: AsyncSession,
    actor: User,
    room_id: int,
    *,
    before_id: Optional[int] = None,
    around_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    room = await require_room(session, actor, room_id)
    if before_id is not None and around_id is not None:
        raise ChatError(
            "CHAT_BAD_CONTENT",
            "Параметры before_id и around_id взаимоисключающие",
        )
    limit = max(1, min(int(limit), 100))

    if around_id is not None:
        pivot = await session.scalar(
            select(ChatMessage.id).where(
                ChatMessage.id == around_id,
                ChatMessage.room_id == room.id,
            )
        )
        if pivot is None:
            raise ChatError("CHAT_MESSAGE_NOT_FOUND", "Сообщение не найдено")

        before_limit = limit // 2
        after_limit = limit - before_limit - 1
        older = list(
            (
                await session.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.room_id == room.id,
                        ChatMessage.id <= around_id,
                    )
                    .options(*MESSAGE_LOAD)
                    .order_by(ChatMessage.id.desc())
                    .limit(before_limit + 1)
                )
            )
            .scalars()
            .all()
        )
        newer = list(
            (
                await session.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.room_id == room.id,
                        ChatMessage.id > around_id,
                    )
                    .options(*MESSAGE_LOAD)
                    .order_by(ChatMessage.id.asc())
                    .limit(max(after_limit, 0))
                )
            )
            .scalars()
            .all()
        )
        older.reverse()
        messages = older + newer
    else:
        stmt: Select[Any] = (
            select(ChatMessage)
            .where(ChatMessage.room_id == room.id)
            .options(*MESSAGE_LOAD)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        if before_id is not None:
            stmt = stmt.where(ChatMessage.id < before_id)
        messages = list((await session.execute(stmt)).scalars().all())
        messages.reverse()

    return [message_to_dict(m, actor=actor) for m in messages]


async def create_message(
    session: AsyncSession,
    actor: User,
    room_id: int,
    *,
    content_raw: Any,
    reply_to_id: Optional[int] = None,
    staged_files: Optional[Sequence[StagedFile]] = None,
) -> dict[str, Any]:
    """Создаёт сообщение: текст и/или уже прочитанные во временный каталог файлы."""
    staged = list(staged_files or [])
    final_paths: list[str] = []
    message_id: Optional[int] = None
    settings = get_settings()
    try:
        # Повторная проверка доступа уже после staging (короткая write-транзакция).
        room = await require_room(session, actor, room_id, need_write=True)

        mentionable = await mentionable_users(session, actor, room)
        mention_map = {u.id: u for u in mentionable}
        content, body, mention_ids = normalize_content(
            content_raw,
            mention_users=mention_map,
            max_chars=settings.chat_message_max_chars,
        )
        plain = body.strip()
        if not plain and not staged:
            raise ChatError("CHAT_EMPTY_MESSAGE", "Пустое сообщение")

        reply_to: Optional[ChatMessage] = None
        if reply_to_id is not None:
            reply_to = await load_message(session, reply_to_id)
            if reply_to is None or reply_to.room_id != room.id:
                raise ChatError(
                    "CHAT_MESSAGE_NOT_FOUND",
                    "Сообщение для ответа не найдено в этой комнате",
                )

        message = ChatMessage(
            room_id=room.id,
            author_id=actor.id,
            author_name=actor.display_name,
            body=plain or None,
            content=content,
            reply_to_id=reply_to.id if reply_to is not None else None,
        )
        session.add(message)
        await session.flush()
        message_id = message.id

        files_total_bytes = 0
        for item in staged:
            stored_path = commit_staged_file(room.id, message.id, item)
            final_paths.append(stored_path)
            files_total_bytes += item.size_bytes
            session.add(
                ChatAttachment(
                    message_id=message.id,
                    stored_path=stored_path,
                    original_name=item.original_name,
                    content_type=item.content_type,
                    size_bytes=item.size_bytes,
                    uploaded_by_id=actor.id,
                )
            )

        for uid in mention_ids:
            if uid == actor.id:
                continue
            target = mention_map[uid]
            session.add(
                ChatMention(
                    message_id=message.id,
                    user_id=target.id,
                    user_name=target.display_name,
                    telegram_status=ChatTelegramStatus.pending,
                    telegram_attempts=0,
                )
            )

        await session.flush()
        loaded = await load_message(session, message.id)
        assert loaded is not None
        message_dict = message_to_dict(loaded, actor=actor)
        event_message = dict(message_dict)
        event_message["author"] = {
            "id": message_dict["author"]["id"],
            "display_name": message_dict["author"]["display_name"],
        }
        event_message.pop("can_delete", None)

        await append_event(
            session,
            type="message.created",
            room_id=room.id,
            payload={"message": _jsonable_message(event_message)},
        )
        for uid in mention_ids:
            if uid == actor.id:
                continue
            mention_row = await session.scalar(
                select(ChatMention).where(
                    ChatMention.message_id == message.id,
                    ChatMention.user_id == uid,
                )
            )
            if mention_row is None:
                continue
            await append_event(
                session,
                type="mention.created",
                room_id=room.id,
                target_user_id=uid,
                payload={
                    "mention_id": mention_row.id,
                    "message_id": message.id,
                    "room_id": room.id,
                },
            )

        await write_audit(
            session,
            action="chat.message.created",
            actor_user_id=actor.id,
            target_type="chat_message",
            target_id=str(message.id),
            payload={
                "room_id": room.id,
                "kind": room.kind.value,
                "message_id": message.id,
                "files_count": len(staged),
                "files_total_bytes": files_total_bytes,
                "mentions_count": len([u for u in mention_ids if u != actor.id]),
                "reply_to_id": reply_to_id,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        delete_stored_files(final_paths)
        raise
    finally:
        cleanup_staged(staged)

    assert message_id is not None
    loaded = await load_message(session, message_id)
    assert loaded is not None
    return message_to_dict(loaded, actor=actor)


async def create_text_message(
    session: AsyncSession,
    actor: User,
    room_id: int,
    *,
    content_raw: Any,
    reply_to_id: Optional[int] = None,
    has_files: bool = False,
) -> dict[str, Any]:
    """Совместимость с этапом 2: только текст."""
    if has_files:
        raise ChatError("CHAT_BAD_CONTENT", "Передайте staged_files через create_message")
    return await create_message(
        session,
        actor,
        room_id,
        content_raw=content_raw,
        reply_to_id=reply_to_id,
        staged_files=[],
    )


def _jsonable_message(message_dict: dict[str, Any]) -> dict[str, Any]:
    """datetime → iso для JSON в chat_events.payload."""
    out = dict(message_dict)
    created = out.get("created_at")
    if isinstance(created, datetime):
        out["created_at"] = created.isoformat()
    return out


async def soft_delete_message(
    session: AsyncSession, actor: User, message_id: int
) -> bool:
    """True если удалили сейчас, False если уже было удалено (идемпотентно)."""
    message = await load_message(session, message_id)
    if message is None:
        raise ChatError("CHAT_MESSAGE_NOT_FOUND", "Сообщение не найдено")

    room = await require_room(session, actor, message.room_id)
    if message.deleted_at is not None:
        return False
    if not can_delete_message(actor, message):
        raise ChatError("CHAT_DELETE_FORBIDDEN", "Нельзя удалить это сообщение")

    stored_paths = [att.stored_path for att in list(message.attachments or [])]

    message.body = None
    message.content = []
    message.deleted_at = _utc_now()
    message.deleted_by_id = actor.id

    for att in list(message.attachments or []):
        await session.delete(att)

    mentions = list(
        (
            await session.execute(
                select(ChatMention).where(ChatMention.message_id == message.id)
            )
        )
        .scalars()
        .all()
    )
    for mention in mentions:
        if mention.telegram_status in (
            ChatTelegramStatus.pending,
            ChatTelegramStatus.retry,
        ):
            mention.telegram_status = ChatTelegramStatus.cancelled
            mention.telegram_locked_at = None
            mention.telegram_next_retry_at = None

    await append_event(
        session,
        type="message.deleted",
        room_id=room.id,
        payload={"message_id": message.id, "room_id": room.id},
    )
    await write_audit(
        session,
        action="chat.message.deleted",
        actor_user_id=actor.id,
        target_type="chat_message",
        target_id=str(message.id),
        payload={
            "room_id": room.id,
            "kind": room.kind.value,
            "message_id": message.id,
            "author_id": message.author_id,
        },
    )
    await session.commit()
    delete_stored_files(stored_paths)
    return True


async def resolve_attachment_download(
    session: AsyncSession, actor: User, attachment_id: int
) -> tuple[ChatAttachment, Path]:
    """Проверяет доступ к комнате и возвращает (attachment, absolute path)."""
    attachment = await session.scalar(
        select(ChatAttachment)
        .where(ChatAttachment.id == attachment_id)
        .options(selectinload(ChatAttachment.message))
    )
    if attachment is None:
        raise ChatError("CHAT_ATTACHMENT_NOT_FOUND", "Вложение не найдено")

    message = attachment.message
    if message is None or message.deleted_at is not None:
        raise ChatError("CHAT_ATTACHMENT_NOT_FOUND", "Вложение не найдено")

    await require_room(session, actor, message.room_id)

    path = ensure_under_chat_root(absolute_stored_path(attachment.stored_path))
    if not path.is_file():
        raise ChatError("CHAT_ATTACHMENT_NOT_FOUND", "Вложение не найдено")
    return attachment, path


# ---------------------------------------------------------------------------
# Read cursor / mentions
# ---------------------------------------------------------------------------


async def update_read_cursor(
    session: AsyncSession,
    actor: User,
    room_id: int,
    *,
    last_read_message_id: int,
) -> dict[str, Any]:
    room = await require_room(session, actor, room_id)
    msg = await session.scalar(
        select(ChatMessage).where(
            ChatMessage.id == last_read_message_id,
            ChatMessage.room_id == room.id,
        )
    )
    if msg is None:
        raise ChatError("CHAT_MESSAGE_NOT_FOUND", "Сообщение не найдено")

    read = await get_read_cursor(session, room_id=room.id, user_id=actor.id)
    prev = read.last_read_message_id if read else None
    dialect = session.get_bind().dialect.name
    insert_factory = (
        sqlite_insert if dialect == "sqlite" else postgresql_insert
        if dialect == "postgresql" else None
    )
    cursor_advanced = False
    if insert_factory is not None:
        stmt = insert_factory(ChatRead).values(
            room_id=room.id,
            user_id=actor.id,
            last_read_message_id=last_read_message_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ChatRead.room_id, ChatRead.user_id],
            set_={
                "last_read_message_id": last_read_message_id,
                "updated_at": func.now(),
            },
            where=or_(
                ChatRead.last_read_message_id.is_(None),
                ChatRead.last_read_message_id < last_read_message_id,
            ),
        ).returning(ChatRead.last_read_message_id)
        effective = await session.scalar(stmt)
        cursor_advanced = effective is not None
        if effective is None:
            current = await get_read_cursor(
                session, room_id=room.id, user_id=actor.id
            )
            effective = current.last_read_message_id if current else None
    else:
        # Fallback для иных СУБД: savepoint защищает гонку первой вставки.
        if read is None:
            candidate = ChatRead(
                room_id=room.id,
                user_id=actor.id,
                last_read_message_id=last_read_message_id,
            )
            try:
                async with session.begin_nested():
                    session.add(candidate)
                    await session.flush()
                effective = last_read_message_id
                cursor_advanced = True
            except IntegrityError:
                current = await get_read_cursor(
                    session, room_id=room.id, user_id=actor.id
                )
                effective = current.last_read_message_id if current else None
        elif prev is None or last_read_message_id > prev:
            read.last_read_message_id = last_read_message_id
            effective = last_read_message_id
            cursor_advanced = True
        else:
            effective = prev

    assert effective is not None
    now = _utc_now()
    mentions = list(
        (
            await session.execute(
                select(ChatMention)
                .join(ChatMessage, ChatMessage.id == ChatMention.message_id)
                .where(
                    ChatMention.user_id == actor.id,
                    ChatMention.read_at.is_(None),
                    ChatMessage.room_id == room.id,
                    ChatMessage.id <= effective,
                )
            )
        )
        .scalars()
        .all()
    )
    for mention in mentions:
        mention.read_at = now

    if cursor_advanced or mentions:
        await append_event(
            session,
            type="read.updated",
            room_id=room.id,
            target_user_id=actor.id,
            payload={
                "room_id": room.id,
                "last_read_message_id": effective,
            },
        )
        await write_audit(
            session,
            action="chat.read.updated",
            actor_user_id=actor.id,
            target_type="chat_room",
            target_id=str(room.id),
            payload={
                "room_id": room.id,
                "from": prev,
                "to": effective,
                "mentions_marked": len(mentions),
            },
        )
        await session.commit()

    unread = await unread_count_for_room(
        session, room_id=room.id, user_id=actor.id, last_read_id=effective
    )
    unread_m = await unread_mentions_for_room(
        session, room_id=room.id, user_id=actor.id
    )
    return {
        "room_id": room.id,
        "last_read_message_id": effective,
        "unread_count": unread,
        "unread_mentions": unread_m,
    }


async def list_mentions(
    session: AsyncSession,
    actor: User,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not is_chat_eligible(actor):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")
    limit = max(1, min(int(limit), 100))

    stmt = (
        select(ChatMention, ChatMessage, ChatRoom)
        .join(ChatMessage, ChatMessage.id == ChatMention.message_id)
        .join(ChatRoom, ChatRoom.id == ChatMessage.room_id)
        .where(
            ChatMention.user_id == actor.id,
            ChatMessage.deleted_at.is_(None),
        )
        .options(selectinload(ChatMessage.attachments))
        .order_by(ChatMention.id.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(ChatMention.read_at.is_(None))

    rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for mention, message, room in rows:
        # доступ мог пропасть (например, выгнали из direct) — пропускаем
        try:
            await assert_room_access(session, actor, room)
        except ChatError:
            continue
        title = room.title
        if room.kind == ChatRoomKind.direct:
            peer = await find_direct_peer(session, room, actor.id)
            title = peer.display_name if peer is not None else "Диалог"
        out.append(
            {
                "id": mention.id,
                "room_id": room.id,
                "room_title": title,
                "message_id": message.id,
                "author_name": message.author_name,
                "preview": preview_text(
                    message.body,
                    has_attachments=bool(message.attachments),
                    is_deleted=False,
                ),
                "created_at": mention.created_at,
                "read_at": mention.read_at,
            }
        )
    return out


async def mark_mention_read(
    session: AsyncSession, actor: User, mention_id: int
) -> dict[str, Any]:
    if not is_chat_eligible(actor):
        raise ChatError("CHAT_FORBIDDEN", "Нет доступа к чату")

    mention = await session.scalar(
        select(ChatMention)
        .where(ChatMention.id == mention_id)
        .options(
            selectinload(ChatMention.message).selectinload(ChatMessage.room),
        )
    )
    if mention is None or mention.user_id != actor.id:
        raise ChatError("CHAT_MENTION_NOT_FOUND", "Уведомление не найдено")

    message = mention.message
    room = await require_room(session, actor, message.room_id)

    if mention.read_at is None:
        mention.read_at = _utc_now()
        await write_audit(
            session,
            action="chat.mention.read",
            actor_user_id=actor.id,
            target_type="chat_mention",
            target_id=str(mention.id),
            payload={
                "room_id": room.id,
                "message_id": message.id,
                "mention_id": mention.id,
            },
        )
        await session.commit()

    return {
        "id": mention.id,
        "room_id": room.id,
        "message_id": message.id,
        "read_at": mention.read_at,
    }
