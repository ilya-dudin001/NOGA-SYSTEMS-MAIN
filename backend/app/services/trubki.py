from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import (
    Noga,
    Trubka,
    TrubkaEvent,
    TrubkaFile,
    TrubkaFileKind,
    TrubkaStatus,
    User,
)
from app.schemas import (
    TrubkaEventOut,
    TrubkaFileOut,
    TrubkaOut,
    TrubkiSummaryOut,
)
from app.services.nogas import (
    CHUNK_BYTES,
    EXTENSION_CONTENT_TYPES,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_BYTES,
    UploadError,
)

# «Чья нога» живёт в noga.created_by, поэтому тянем автора ноги вместе с ногой.
LOAD_OPTIONS = (
    selectinload(Trubka.city),
    selectinload(Trubka.noga).selectinload(Noga.created_by),
    selectinload(Trubka.razgruz),
    selectinload(Trubka.created_by),
    selectinload(Trubka.files).selectinload(TrubkaFile.uploaded_by),
    selectinload(Trubka.events),
)


async def load(session: AsyncSession, trubka_id: int) -> Optional[Trubka]:
    result = await session.execute(
        select(Trubka)
        .options(*LOAD_OPTIONS)
        .where(Trubka.id == trubka_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


def _list_filters(
    query,
    *,
    status: Optional[TrubkaStatus] = None,
    city_id: Optional[int] = None,
    include_reported: bool = False,
):
    """Общие WHERE для списка и счётчика. Без include_reported — только активные."""
    if status is not None:
        query = query.where(Trubka.status == status)
    if city_id is not None:
        query = query.where(Trubka.city_id == city_id)
    if not include_reported:
        query = query.where(Trubka.report_sent_at.is_(None))
    return query


async def load_all(
    session: AsyncSession,
    *,
    status: Optional[TrubkaStatus] = None,
    city_id: Optional[int] = None,
    include_reported: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Sequence[Trubka]:
    query = select(Trubka).options(*LOAD_OPTIONS)
    query = _list_filters(
        query,
        status=status,
        city_id=city_id,
        include_reported=include_reported,
    )
    query = query.order_by(Trubka.created_at.desc(), Trubka.id.desc())
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def count_all(
    session: AsyncSession,
    *,
    status: Optional[TrubkaStatus] = None,
    city_id: Optional[int] = None,
    include_reported: bool = False,
) -> int:
    query = select(func.count()).select_from(Trubka)
    query = _list_filters(
        query,
        status=status,
        city_id=city_id,
        include_reported=include_reported,
    )
    return await session.scalar(query) or 0


async def count_for(
    session: AsyncSession,
    *,
    city_id: Optional[int] = None,
    noga_id: Optional[int] = None,
    razgruz_id: Optional[int] = None,
) -> int:
    """Сколько трубок висит на городе, ноге или разгрузе — перед их удалением."""
    query = select(func.count()).select_from(Trubka)
    if city_id is not None:
        query = query.where(Trubka.city_id == city_id)
    if noga_id is not None:
        query = query.where(Trubka.noga_id == noga_id)
    if razgruz_id is not None:
        query = query.where(Trubka.razgruz_id == razgruz_id)
    return await session.scalar(query) or 0


async def summary(session: AsyncSession) -> TrubkiSummaryOut:
    """Счётчики активных трубок (отчёт ещё не отправлен) — для дашборда."""
    result = await session.execute(
        select(Trubka.status, func.count())
        .where(Trubka.report_sent_at.is_(None))
        .group_by(Trubka.status)
    )
    counts = {status: count for status, count in result.all()}
    return TrubkiSummaryOut(
        total=sum(counts.values()),
        zacep=counts.get(TrubkaStatus.zacep, 0),
        zabrali=counts.get(TrubkaStatus.zabrali, 0),
        vyplacheno=counts.get(TrubkaStatus.vyplacheno, 0),
        srez=counts.get(TrubkaStatus.srez, 0),
        razgruzhaetsya=counts.get(TrubkaStatus.razgruzhaetsya, 0),
    )


def to_out(trubka: Trubka, *, can_manage: bool = False) -> TrubkaOut:
    noga_owner = trubka.noga.created_by if trubka.noga else None
    payout = (
        trubka.recalculation_amount * 10 // 100
        if trubka.recalculation_amount is not None
        else None
    )
    return TrubkaOut(
        id=trubka.id,
        status=trubka.status,
        city_id=trubka.city_id,
        city_name=trubka.city.name,
        amount=trubka.amount,
        amount_currency=trubka.amount_currency,
        noga_id=trubka.noga_id,
        noga_name=trubka.noga.name,
        noga_owner_name=noga_owner.display_name if noga_owner else None,
        razgruz_id=trubka.razgruz_id,
        razgruz_name=trubka.razgruz.name if trubka.razgruz else None,
        customer_name=trubka.customer_name,
        customer_address=trubka.customer_address,
        delivery=trubka.delivery,
        recalculation_amount=trubka.recalculation_amount,
        noga_payout=payout,
        remainder=(
            trubka.recalculation_amount - payout
            if trubka.recalculation_amount is not None and payout is not None
            else None
        ),
        usdt_received=trubka.usdt_received,
        report_sent_at=trubka.report_sent_at,
        files=[file_to_out(item) for item in trubka.files],
        history=[
            TrubkaEventOut(
                id=item.id,
                actor_name=item.actor_name,
                action=item.action,
                payload=dict(item.payload or {}),
                created_at=item.created_at,
            )
            for item in trubka.events
        ],
        created_at=trubka.created_at,
        updated_at=trubka.updated_at,
        created_by_name=trubka.created_by.display_name if trubka.created_by else None,
        can_manage=can_manage,
    )


def file_to_out(item: TrubkaFile) -> TrubkaFileOut:
    return TrubkaFileOut(
        id=item.id,
        kind=item.kind,
        original_name=item.original_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
        uploaded_by_name=item.uploaded_by.display_name if item.uploaded_by else None,
    )


def add_event(
    session: AsyncSession,
    trubka: Trubka,
    actor: User,
    action: str,
    payload: Optional[dict] = None,
) -> TrubkaEvent:
    event = TrubkaEvent(
        trubka_id=trubka.id,
        actor_user_id=actor.id,
        actor_name=actor.display_name,
        action=action,
        payload=payload or {},
    )
    session.add(event)
    return event


def uploads_root() -> Path:
    return Path(get_settings().uploads_dir).resolve()


def absolute_path(stored_path: str) -> Path:
    return uploads_root() / stored_path


async def save_upload(trubka_id: int, filename: str, stream) -> tuple[str, int, str]:
    ext = Path(filename or "").suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        readable = ", ".join(sorted(item.lstrip(".") for item in IMAGE_EXTENSIONS))
        shown = ext or "без расширения"
        raise UploadError(f"Неподдерживаемый формат «{shown}». Разрешены: {readable}")

    relative = Path("trubki") / str(trubka_id) / f"{uuid.uuid4().hex}{ext}"
    target = uploads_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await stream.read(CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise UploadError("Файл больше 25 МБ — сожмите изображение")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise UploadError("Файл пустой")
    return relative.as_posix(), size, ext


def resolve_content_type(ext: str, declared: Optional[str]) -> str:
    if declared and declared != "application/octet-stream":
        return declared[:120]
    return EXTENSION_CONTENT_TYPES.get(ext, "application/octet-stream")


def delete_stored(stored_path: str) -> None:
    absolute_path(stored_path).unlink(missing_ok=True)


def delete_trubka_dir(trubka_id: int) -> None:
    shutil.rmtree(uploads_root() / "trubki" / str(trubka_id), ignore_errors=True)


async def find_file(
    session: AsyncSession, trubka_id: int, kind: TrubkaFileKind
) -> Optional[TrubkaFile]:
    return await session.scalar(
        select(TrubkaFile).where(
            TrubkaFile.trubka_id == trubka_id, TrubkaFile.kind == kind
        )
    )
