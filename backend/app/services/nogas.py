from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import City, Noga, NogaFile, NogaFileKind
from app.schemas import NogaDetailOut, NogaFileOut, NogaOut

LOAD_OPTIONS = (
    selectinload(Noga.city),
    selectinload(Noga.created_by),
)

# Расширения важнее content-type: iOS шлёт HEIC как application/octet-stream.
IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".jfif",
        ".webp",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".avif",
    }
)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".3gp", ".mkv", ".avi"})

EXTENSION_CONTENT_TYPES = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".jfif": "image/jpeg",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".3gp": "video/3gpp",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class UploadError(Exception):
    """Файл не прошёл проверку: тип, размер или пустое тело."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def normalize(name: str) -> str:
    return " ".join(name.split())


def normalize_contacts(values: Sequence[str]) -> list[str]:
    """Чистит пробелы, выкидывает пустые строки и повторы, сохраняя порядок."""
    result: list[str] = []
    for value in values:
        item = " ".join(str(value).split())
        if item and item not in result:
            result.append(item[:64])
    return result


async def load(session: AsyncSession, noga_id: int, *, with_files: bool = False) -> Optional[Noga]:
    options = list(LOAD_OPTIONS)
    if with_files:
        options.append(selectinload(Noga.files).selectinload(NogaFile.uploaded_by))
    result = await session.execute(
        select(Noga)
        .options(*options)
        .where(Noga.id == noga_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def load_all(
    session: AsyncSession,
    *,
    city_id: Optional[int] = None,
    include_test: bool = True,
    only_active: bool = False,
    owner_id: Optional[int] = None,
) -> Sequence[Noga]:
    """owner_id ограничивает выдачу своими ногами: у админа скоуп — то, что он завёл."""
    query = select(Noga).options(*LOAD_OPTIONS)
    if owner_id is not None:
        query = query.where(Noga.created_by_id == owner_id)
    if city_id is not None:
        query = query.where(Noga.city_id == city_id)
    if not include_test:
        query = query.where(Noga.is_test.is_(False))
    if only_active:
        query = query.where(Noga.is_active.is_(True))
    result = await session.execute(query.order_by(Noga.name.asc()))
    return result.scalars().all()


async def find_clash(
    session: AsyncSession,
    *,
    name: str,
    city_id: Optional[int],
    exclude_id: Optional[int] = None,
) -> Optional[Noga]:
    """Тёзка в том же городе. Для ног без города сравниваем среди неприкреплённых."""
    query = select(Noga).where(Noga.name == name)
    query = query.where(Noga.city_id.is_(None) if city_id is None else Noga.city_id == city_id)
    if exclude_id is not None:
        query = query.where(Noga.id != exclude_id)
    result = await session.execute(query)
    return result.scalars().first()


def remember_city(noga: Noga, city_name: str) -> None:
    """Запоминает город прикрепления: первый — навсегда, последний — перезаписывается."""
    if not noga.initial_city_name:
        noga.initial_city_name = city_name
    noga.last_city_name = city_name


async def attach_to_city(
    session: AsyncSession, city: City, noga_ids: Sequence[int], *, owner_id: Optional[int] = None
) -> tuple[list[int], list[int]]:
    """Приводит состав города к списку: возвращает (прикреплённые, откреплённые).

    owner_id — скоуп актора: чужие ноги в городе остаются на месте, даже если их
    нет в списке. Иначе админ, правя свой город, снёс бы ноги соседа.
    """
    wanted = set(noga_ids)
    conditions = [Noga.city_id == city.id]
    if wanted:
        conditions.append(Noga.id.in_(wanted))
    query = select(Noga).where(or_(*conditions))
    if owner_id is not None:
        query = query.where(Noga.created_by_id == owner_id)
    result = await session.execute(query)

    attached: list[int] = []
    detached: list[int] = []
    for noga in result.scalars().all():
        in_city = noga.city_id == city.id
        if noga.id in wanted and not in_city:
            noga.city_id = city.id
            remember_city(noga, city.name)
            attached.append(noga.id)
        elif in_city and noga.id not in wanted:
            noga.city_id = None
            detached.append(noga.id)
    return sorted(attached), sorted(detached)


async def names_in_city(session: AsyncSession, city_id: int) -> list[str]:
    result = await session.execute(
        select(Noga.name).where(Noga.city_id == city_id).order_by(Noga.name.asc())
    )
    return list(result.scalars().all())


async def detach_from_city(session: AsyncSession, city: City) -> list[str]:
    """Снимает все ноги с города перед его удалением. Возвращает имена ног."""
    result = await session.execute(
        select(Noga).where(Noga.city_id == city.id).order_by(Noga.name.asc())
    )
    names: list[str] = []
    for noga in result.scalars().all():
        # Ноги, заведённые до появления снимков, получают их здесь: иначе
        # после удаления города от истории не останется ничего.
        remember_city(noga, city.name)
        noga.city_id = None
        names.append(noga.name)
    return names


async def rename_city_snapshots(session: AsyncSession, old_name: str, new_name: str) -> None:
    """Город переименовали — подтягиваем снимки в истории ног."""
    await session.execute(
        update(Noga)
        .where(Noga.initial_city_name == old_name)
        .values(initial_city_name=new_name)
    )
    await session.execute(
        update(Noga).where(Noga.last_city_name == old_name).values(last_city_name=new_name)
    )


def to_out(noga: Noga, *, can_manage: bool = False) -> NogaOut:
    return NogaOut(
        id=noga.id,
        name=noga.name,
        city_id=noga.city_id,
        city_name=noga.city.name if noga.city else None,
        initial_city_name=noga.initial_city_name,
        last_city_name=noga.last_city_name,
        is_test=noga.is_test,
        is_active=noga.is_active,
        created_at=noga.created_at,
        created_by_name=noga.created_by.display_name if noga.created_by else None,
        can_manage=can_manage,
    )


def file_to_out(item: NogaFile) -> NogaFileOut:
    return NogaFileOut(
        id=item.id,
        kind=item.kind,
        original_name=item.original_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
        uploaded_by_name=item.uploaded_by.display_name if item.uploaded_by else None,
    )


def to_detail_out(
    noga: Noga, *, include_personal: bool, can_manage: bool = False
) -> NogaDetailOut:
    base = to_out(noga, can_manage=can_manage)
    if not include_personal:
        return NogaDetailOut(**base.model_dump(), has_personal_access=False)
    return NogaDetailOut(
        **base.model_dump(),
        address=noga.address,
        phones=list(noga.phones or []),
        telegrams=list(noga.telegrams or []),
        files=[file_to_out(f) for f in noga.files],
        has_personal_access=True,
    )


# ---------- файлы на диске ----------


def uploads_root() -> Path:
    return Path(get_settings().uploads_dir).resolve()


def absolute_path(stored_path: str) -> Path:
    return uploads_root() / stored_path


def kind_limit(kind: NogaFileKind) -> int:
    return MAX_VIDEO_BYTES if kind is NogaFileKind.face_video else MAX_IMAGE_BYTES


def check_extension(kind: NogaFileKind, filename: str) -> str:
    """Проверяет расширение и возвращает его в нижнем регистре."""
    ext = Path(filename or "").suffix.lower()
    allowed = VIDEO_EXTENSIONS if kind is NogaFileKind.face_video else IMAGE_EXTENSIONS
    if ext not in allowed:
        readable = ", ".join(sorted(e.lstrip(".") for e in allowed))
        shown = ext or "без расширения"
        raise UploadError(f"Неподдерживаемый формат «{shown}». Разрешены: {readable}")
    return ext


def resolve_content_type(ext: str, declared: Optional[str]) -> str:
    if declared and declared != "application/octet-stream":
        return declared[:120]
    return EXTENSION_CONTENT_TYPES.get(ext, "application/octet-stream")


async def save_upload(
    noga_id: int, kind: NogaFileKind, filename: str, stream
) -> tuple[str, int, str]:
    """Пишет файл на диск чанками. Возвращает (относительный путь, размер, расширение)."""
    ext = check_extension(kind, filename)
    limit = kind_limit(kind)

    relative = Path("nogas") / str(noga_id) / f"{uuid.uuid4().hex}{ext}"
    target = uploads_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await stream.read(CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise UploadError(
                        f"Файл больше {limit // (1024 * 1024)} МБ — сожмите или обрежьте"
                    )
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    if size == 0:
        target.unlink(missing_ok=True)
        raise UploadError("Файл пустой")

    return relative.as_posix(), size, ext


def delete_stored(stored_path: str) -> None:
    absolute_path(stored_path).unlink(missing_ok=True)


def delete_noga_dir(noga_id: int) -> None:
    shutil.rmtree(uploads_root() / "nogas" / str(noga_id), ignore_errors=True)


def ensure_uploads_dir() -> None:
    uploads_root().mkdir(parents=True, exist_ok=True)
