from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import OPERATIONS_ALL, OPERATIONS_OWN, has_permission
from app.db import get_session
from app.db.models import (
    City,
    Noga,
    Razgruz,
    Trubka,
    TrubkaFile,
    TrubkaFileKind,
    TrubkaStatus,
    User,
)
from app.schemas import (
    TrubkaCreateIn,
    TrubkaFileOut,
    TrubkaOut,
    TrubkaRecalculationIn,
    TrubkaUpdateIn,
    TrubkaUsdtIn,
)
from app.services import trubki as trubki_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/trubki", tags=["trubki"])


def can_manage(actor: User) -> bool:
    return has_permission(actor.role, OPERATIONS_ALL)


def api_error(http_status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


async def get_trubka_or_404(session: AsyncSession, trubka_id: int) -> Trubka:
    trubka = await trubki_service.load(session, trubka_id)
    if trubka is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Трубка не найдена")
    return trubka


async def require_city(session: AsyncSession, city_id: int) -> City:
    item = await session.scalar(select(City).where(City.id == city_id))
    if item is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Город не найден")
    return item


async def require_noga(session: AsyncSession, noga_id: int) -> Noga:
    item = await session.scalar(select(Noga).where(Noga.id == noga_id))
    if item is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Нога не найдена")
    return item


async def require_razgruz(session: AsyncSession, razgruz_id: int) -> Razgruz:
    item = await session.scalar(select(Razgruz).where(Razgruz.id == razgruz_id))
    if item is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Разгруз не найден")
    return item


async def audit_and_event(
    session: AsyncSession,
    trubka: Trubka,
    actor: User,
    *,
    event_action: str,
    audit_action: str,
    payload: Optional[dict] = None,
) -> None:
    data = payload or {}
    trubki_service.add_event(session, trubka, actor, event_action, data)
    await write_audit(
        session,
        action=audit_action,
        actor_user_id=actor.id,
        target_type="trubka",
        target_id=str(trubka.id),
        payload=data,
    )


@router.get("", response_model=list[TrubkaOut])
async def list_trubki(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_OWN))],
    status_filter: Annotated[Optional[TrubkaStatus], Query(alias="status")] = None,
    city_id: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
) -> list[TrubkaOut]:
    items = await trubki_service.load_all(
        session, status=status_filter, city_id=city_id, limit=limit
    )
    return [trubki_service.to_out(item, can_manage=can_manage(actor)) for item in items]


@router.get("/{trubka_id}", response_model=TrubkaOut)
async def get_trubka(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_OWN))],
) -> TrubkaOut:
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=can_manage(actor)
    )


@router.post("", response_model=TrubkaOut, status_code=status.HTTP_201_CREATED)
async def create_trubka(
    body: TrubkaCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    await require_city(session, body.city_id)
    await require_noga(session, body.noga_id)
    if body.razgruz_id is not None:
        await require_razgruz(session, body.razgruz_id)

    trubka = Trubka(
        status=body.status,
        city_id=body.city_id,
        noga_id=body.noga_id,
        razgruz_id=body.razgruz_id,
        amount=body.amount,
        amount_currency=body.amount_currency,
        customer_name=body.customer_name.strip() if body.customer_name else None,
        customer_address=body.customer_address.strip() if body.customer_address else None,
        delivery=body.delivery,
        created_by_id=actor.id,
    )
    session.add(trubka)
    await session.flush()
    payload = {
        "status": trubka.status.value,
        "city_id": trubka.city_id,
        "noga_id": trubka.noga_id,
        "amount": trubka.amount,
        "currency": trubka.amount_currency.value,
    }
    await audit_and_event(
        session,
        trubka,
        actor,
        event_action="created",
        audit_action="trubka.created",
        payload=payload,
    )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka.id), can_manage=True
    )


@router.patch("/{trubka_id}", response_model=TrubkaOut)
async def update_trubka(
    trubka_id: int,
    body: TrubkaUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    provided = body.model_fields_set

    # Все SELECT выполняются до первой мутации.
    if body.city_id is not None and body.city_id != trubka.city_id:
        await require_city(session, body.city_id)
    if body.noga_id is not None and body.noga_id != trubka.noga_id:
        await require_noga(session, body.noga_id)
    if "razgruz_id" in provided and body.razgruz_id is not None:
        await require_razgruz(session, body.razgruz_id)

    changes: dict = {}

    def shown(value):
        return value.value if hasattr(value, "value") else value

    def apply(field: str, value) -> None:
        current = getattr(trubka, field)
        if value != current:
            changes[field] = {"from": shown(current), "to": shown(value)}
            setattr(trubka, field, value)

    if body.status is not None:
        old_status = trubka.status
        apply("status", body.status)
        if old_status != trubka.status:
            await audit_and_event(
                session,
                trubka,
                actor,
                event_action="status_changed",
                audit_action="trubka.status_changed",
                payload={"from": old_status.value, "to": trubka.status.value},
            )
    if body.city_id is not None:
        apply("city_id", body.city_id)
    if body.noga_id is not None:
        apply("noga_id", body.noga_id)
    if "razgruz_id" in provided:
        apply("razgruz_id", body.razgruz_id)
    if body.amount is not None:
        apply("amount", body.amount)
    if body.amount_currency is not None:
        apply("amount_currency", body.amount_currency)
    if "delivery" in provided:
        apply("delivery", body.delivery)
    if "customer_name" in provided:
        value = body.customer_name.strip() if body.customer_name else None
        if value != trubka.customer_name:
            trubka.customer_name = value
            changes["customer_name"] = "изменено"
    if "customer_address" in provided:
        value = body.customer_address.strip() if body.customer_address else None
        if value != trubka.customer_address:
            trubka.customer_address = value
            changes["customer_address"] = "изменён"

    non_status_changes = {key: value for key, value in changes.items() if key != "status"}
    if non_status_changes:
        trubki_service.add_event(
            session,
            trubka,
            actor,
            "updated",
            {"fields": list(non_status_changes)},
        )
        await write_audit(
            session,
            action="trubka.updated",
            actor_user_id=actor.id,
            target_type="trubka",
            target_id=str(trubka.id),
            payload=non_status_changes,
        )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=True
    )


@router.post("/{trubka_id}/recalculation", response_model=TrubkaOut)
async def set_recalculation(
    trubka_id: int,
    body: TrubkaRecalculationIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    money_photo = next(
        (item for item in trubka.files if item.kind is TrubkaFileKind.money_photo), None
    )
    if money_photo is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "MONEY_PHOTO_REQUIRED",
            "Сначала загрузите фото денег",
        )

    old_status = trubka.status
    trubka.recalculation_amount = body.amount
    trubka.status = TrubkaStatus.razgruzhaetsya
    payload = {
        "amount": body.amount,
        "noga_payout": body.amount * 10 // 100,
        "remainder": body.amount - body.amount * 10 // 100,
    }
    await audit_and_event(
        session,
        trubka,
        actor,
        event_action="recalculation_set",
        audit_action="trubka.recalculation_set",
        payload=payload,
    )
    if old_status != trubka.status:
        await audit_and_event(
            session,
            trubka,
            actor,
            event_action="status_changed",
            audit_action="trubka.status_changed",
            payload={"from": old_status.value, "to": trubka.status.value},
        )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=True
    )


@router.post("/{trubka_id}/usdt", response_model=TrubkaOut)
async def set_usdt_received(
    trubka_id: int,
    body: TrubkaUsdtIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    old_status = trubka.status
    trubka.usdt_received = body.amount
    trubka.status = TrubkaStatus.vyplacheno
    await audit_and_event(
        session,
        trubka,
        actor,
        event_action="usdt_received_set",
        audit_action="trubka.usdt_received_set",
        payload={"amount": str(body.amount)},
    )
    if old_status != trubka.status:
        await audit_and_event(
            session,
            trubka,
            actor,
            event_action="status_changed",
            audit_action="trubka.status_changed",
            payload={"from": old_status.value, "to": trubka.status.value},
        )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=True
    )


@router.post("/{trubka_id}/report", response_model=TrubkaOut)
async def mark_report_sent(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> TrubkaOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    if trubka.usdt_received is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "USDT_REQUIRED",
            "Сначала укажите полученную сумму USDT",
        )
    receipt = next(
        (item for item in trubka.files if item.kind is TrubkaFileKind.receipt_photo), None
    )
    if receipt is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "RECEIPT_PHOTO_REQUIRED",
            "Сначала загрузите фото чека",
        )
    trubka.report_sent_at = datetime.now(timezone.utc)
    await audit_and_event(
        session,
        trubka,
        actor,
        event_action="report_sent",
        audit_action="trubka.report_sent",
        payload={"sent_at": trubka.report_sent_at.isoformat()},
    )
    await session.commit()
    return trubki_service.to_out(
        await get_trubka_or_404(session, trubka_id), can_manage=True
    )


@router.post(
    "/{trubka_id}/files",
    response_model=TrubkaFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_trubka_file(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
    kind: Annotated[TrubkaFileKind, Form()],
    file: Annotated[UploadFile, File()],
) -> TrubkaFileOut:
    trubka = await get_trubka_or_404(session, trubka_id)
    existing = await trubki_service.find_file(session, trubka_id, kind)
    old_path = existing.stored_path if existing else None
    try:
        stored_path, size, ext = await trubki_service.save_upload(
            trubka_id, file.filename or "", file
        )
    except trubki_service.UploadError as err:
        raise api_error(status.HTTP_400_BAD_REQUEST, "BAD_REQUEST", err.message) from err

    try:
        if existing is None:
            item = TrubkaFile(trubka_id=trubka_id, kind=kind)
            session.add(item)
        else:
            item = existing
        item.stored_path = stored_path
        item.original_name = (file.filename or "файл")[:255]
        item.content_type = trubki_service.resolve_content_type(ext, file.content_type)
        item.size_bytes = size
        item.uploaded_by_id = actor.id
        item.created_at = datetime.now(timezone.utc)
        await session.flush()
        action = (
            "money_photo_uploaded"
            if kind is TrubkaFileKind.money_photo
            else "receipt_photo_uploaded"
        )
        await audit_and_event(
            session,
            trubka,
            actor,
            event_action=action,
            audit_action=f"trubka.{action}",
            payload={"file_id": item.id, "size_bytes": size, "replaced": existing is not None},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        trubki_service.delete_stored(stored_path)
        raise
    if old_path:
        trubki_service.delete_stored(old_path)
    await session.refresh(item)
    return TrubkaFileOut(
        id=item.id,
        kind=item.kind,
        original_name=item.original_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
        uploaded_by_name=actor.display_name,
    )


async def get_file_or_404(
    session: AsyncSession, trubka_id: int, file_id: int
) -> TrubkaFile:
    item = await session.get(TrubkaFile, file_id)
    if item is None or item.trubka_id != trubka_id:
        raise api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Файл не найден")
    return item


@router.get("/{trubka_id}/files/{file_id}")
async def download_trubka_file(
    trubka_id: int,
    file_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_OWN))],
) -> FileResponse:
    del actor
    item = await get_file_or_404(session, trubka_id, file_id)
    path = trubki_service.absolute_path(item.stored_path)
    if not path.is_file():
        raise api_error(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Файл потерялся на диске"
        )
    return FileResponse(
        path,
        media_type=item.content_type,
        filename=item.original_name,
        content_disposition_type="inline",
    )


@router.delete("/{trubka_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trubka(
    trubka_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(OPERATIONS_ALL))],
) -> None:
    trubka = await get_trubka_or_404(session, trubka_id)
    await write_audit(
        session,
        action="trubka.deleted",
        actor_user_id=actor.id,
        target_type="trubka",
        target_id=str(trubka.id),
        payload={
            "status": trubka.status.value,
            "city_id": trubka.city_id,
            "noga_id": trubka.noga_id,
            "amount": trubka.amount,
            "currency": trubka.amount_currency.value,
        },
    )
    await session.delete(trubka)
    await session.commit()
    trubki_service.delete_trubka_dir(trubka_id)
