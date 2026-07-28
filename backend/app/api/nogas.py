from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.permissions import (
    NOGAS_ALL,
    NOGAS_MANAGE,
    NOGAS_PERSONAL,
    NOGAS_READ,
    has_permission,
)
from app.db import get_session
from app.db.models import City, Noga, NogaFile, NogaFileKind, User
from app.schemas import NogaCreateIn, NogaDetailOut, NogaFileOut, NogaOut, NogaUpdateIn
from app.services import cities as cities_service
from app.services import nogas as nogas_service
from app.services import trubki as trubki_service
from app.services.audit import write_audit

router = APIRouter(prefix="/api/nogas", tags=["nogas"])

PERSONAL_FIELDS = ("address", "phones", "telegrams")


async def load_noga(session: AsyncSession, noga_id: int, *, with_files: bool = False) -> Noga:
    noga = await nogas_service.load(session, noga_id, with_files=with_files)
    if noga is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Нога не найдена"},
        )
    return noga


def require_personal(actor: User) -> None:
    if not has_permission(actor.role, NOGAS_PERSONAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Нет доступа к личным данным ноги"},
        )


def scope_owner(actor: User) -> Optional[int]:
    """None — актор работает со всеми ногами, иначе видит в списке только свои."""
    return None if has_permission(actor.role, NOGAS_ALL) else actor.id


def can_manage(actor: User, noga: Noga) -> bool:
    return has_permission(actor.role, NOGAS_ALL) or noga.created_by_id == actor.id


def require_own(actor: User, noga: Noga) -> None:
    """Читать ногу может любой с nogas:read, а править — только её автор."""
    if not can_manage(actor, noga):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Ногу завёл другой пользователь — её можно только смотреть",
            },
        )


def conflict(name: str, city_name: Optional[str]) -> HTTPException:
    where = f"в городе {city_name}" if city_name else "среди ног без города"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "CONFLICT", "message": f"Нога «{name}» уже есть {where}"},
    )


@router.get("", response_model=list[NogaOut])
async def list_nogas(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_READ))],
    city_id: Optional[int] = Query(default=None),
    include_test: bool = Query(default=True),
    only_active: bool = Query(default=False),
    scope: str = Query(default="own", pattern="^(own|all)$"),
) -> list[NogaOut]:
    """scope=own — только свои ноги (для админа это и есть весь его участок)."""
    if scope == "all" and not has_permission(actor.role, NOGAS_ALL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Нет доступа к чужим ногам"},
        )
    owner_id = None if scope == "all" else scope_owner(actor)
    nogas = await nogas_service.load_all(
        session,
        city_id=city_id,
        include_test=include_test,
        only_active=only_active,
        owner_id=owner_id,
    )
    return [nogas_service.to_out(n, can_manage=can_manage(actor, n)) for n in nogas]


@router.get("/{noga_id}", response_model=NogaDetailOut)
async def get_noga(
    noga_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_READ))],
) -> NogaDetailOut:
    # Карточку чужой ноги читать можно: админу нужны контакты ноги соседа,
    # если та пропала со связи. Править — нельзя, отсюда can_manage.
    personal = has_permission(actor.role, NOGAS_PERSONAL)
    noga = await load_noga(session, noga_id, with_files=personal)
    return nogas_service.to_detail_out(
        noga, include_personal=personal, can_manage=can_manage(actor, noga)
    )


@router.post("", response_model=NogaDetailOut, status_code=status.HTTP_201_CREATED)
async def create_noga(
    body: NogaCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> NogaDetailOut:
    city: City | None = None
    if body.city_id is not None:
        city = await session.get(City, body.city_id)
        if city is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Город не найден"},
            )
    elif body.city_name:
        city = await cities_service.get_or_create(session, body.city_name, actor)

    name = nogas_service.normalize(body.name)
    if await nogas_service.find_clash(
        session, name=name, city_id=city.id if city else None
    ):
        raise conflict(name, city.name if city else None)

    noga = Noga(
        name=name,
        city_id=city.id if city else None,
        initial_city_name=city.name if city else None,
        last_city_name=city.name if city else None,
        is_test=body.is_test,
        is_active=True,
        phones=[],
        telegrams=[],
        created_by_id=actor.id,
    )
    session.add(noga)
    await session.flush()
    await write_audit(
        session,
        action="noga.created",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga.id),
        payload={
            "name": noga.name,
            "city": city.name if city else None,
            "is_test": noga.is_test,
        },
    )
    await session.commit()
    personal = has_permission(actor.role, NOGAS_PERSONAL)
    return nogas_service.to_detail_out(
        await load_noga(session, noga.id, with_files=personal),
        include_personal=personal,
        can_manage=True,
    )


@router.patch("/{noga_id}", response_model=NogaDetailOut)
async def update_noga(
    noga_id: int,
    body: NogaUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> NogaDetailOut:
    provided = body.model_fields_set
    personal = has_permission(actor.role, NOGAS_PERSONAL)
    if any(field in provided for field in PERSONAL_FIELDS):
        require_personal(actor)

    noga = await load_noga(session, noga_id, with_files=personal)
    require_own(actor, noga)

    # Всё, что требует SELECT'ов, считаем до мутаций: autoflush иначе упрётся
    # в UNIQUE и отдаст 500 вместо понятного 409.
    target_city_id = noga.city_id
    new_city: City | None = None
    if body.city_name:
        new_city = await cities_service.get_or_create(session, body.city_name, actor)
        target_city_id = new_city.id
    elif "city_id" in provided and body.city_id != noga.city_id:
        if body.city_id is not None:
            new_city = await session.get(City, body.city_id)
            if new_city is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "NOT_FOUND", "message": "Город не найден"},
                )
        target_city_id = body.city_id

    target_name = nogas_service.normalize(body.name) if body.name is not None else noga.name
    if target_city_id == noga.city_id:
        target_city_name = noga.city.name if noga.city else None
    else:
        target_city_name = new_city.name if new_city else None

    if (target_city_id, target_name) != (noga.city_id, noga.name):
        if await nogas_service.find_clash(
            session, name=target_name, city_id=target_city_id, exclude_id=noga.id
        ):
            raise conflict(target_name, target_city_name)

    changes: dict = {}
    if target_city_id != noga.city_id:
        changes["city"] = {
            "from": noga.city.name if noga.city else None,
            "to": new_city.name if new_city else None,
        }
        noga.city_id = target_city_id
        if new_city is not None:
            nogas_service.remember_city(noga, new_city.name)
        elif noga.city is not None:
            # Открепление: если снимков ещё нет, хотя бы запомним, откуда сняли.
            nogas_service.remember_city(noga, noga.city.name)
    if target_name != noga.name:
        changes["name"] = {"from": noga.name, "to": target_name}
        noga.name = target_name
    if body.is_test is not None and body.is_test != noga.is_test:
        changes["is_test"] = {"from": noga.is_test, "to": body.is_test}
        noga.is_test = body.is_test
    if body.is_active is not None and body.is_active != noga.is_active:
        changes["is_active"] = {"from": noga.is_active, "to": body.is_active}
        noga.is_active = body.is_active

    # Сами значения личных данных в аудит не пишем — только факт правки.
    if "address" in provided:
        address = " ".join(body.address.split()) if body.address else None
        if address != noga.address:
            changes["address"] = {"changed": True}
            noga.address = address
    if "phones" in provided:
        phones = nogas_service.normalize_contacts(body.phones or [])
        if phones != list(noga.phones or []):
            changes["phones"] = {"count": len(phones)}
            noga.phones = phones
    if "telegrams" in provided:
        telegrams = nogas_service.normalize_contacts(body.telegrams or [])
        if telegrams != list(noga.telegrams or []):
            changes["telegrams"] = {"count": len(telegrams)}
            noga.telegrams = telegrams

    if changes:
        await write_audit(
            session,
            action="noga.updated",
            actor_user_id=actor.id,
            target_type="noga",
            target_id=str(noga.id),
            payload=changes,
        )

    await session.commit()
    return nogas_service.to_detail_out(
        await load_noga(session, noga_id, with_files=personal),
        include_personal=personal,
        can_manage=True,
    )


@router.delete("/{noga_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_noga(
    noga_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> None:
    # files грузим всегда: relationship объявлен lazy="raise", а каскад ORM
    # без загруженной коллекции упадёт при удалении.
    noga = await load_noga(session, noga_id, with_files=True)
    require_own(actor, noga)

    trubki_count = await trubki_service.count_for(session, noga_id=noga.id)
    if trubki_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NOGA_HAS_TRUBKI",
                "message": (
                    f"На ноге висят трубки: {trubki_count}. "
                    "Сначала удалите их или переведите на другую ногу"
                ),
                "trubki": trubki_count,
            },
        )

    await write_audit(
        session,
        action="noga.deleted",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga.id),
        payload={
            "name": noga.name,
            "city": noga.city.name if noga.city else None,
            "is_test": noga.is_test,
            "files": len(noga.files),
        },
    )
    await session.delete(noga)
    await session.commit()
    nogas_service.delete_noga_dir(noga_id)


@router.post(
    "/{noga_id}/files",
    response_model=NogaFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_noga_file(
    noga_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
    kind: Annotated[NogaFileKind, Form()],
    file: Annotated[UploadFile, File()],
) -> NogaFileOut:
    require_personal(actor)
    noga = await load_noga(session, noga_id)
    require_own(actor, noga)

    try:
        stored_path, size, ext = await nogas_service.save_upload(
            noga.id, kind, file.filename or "", file
        )
    except nogas_service.UploadError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_REQUEST", "message": err.message},
        ) from err

    item = NogaFile(
        noga_id=noga.id,
        kind=kind,
        stored_path=stored_path,
        original_name=(file.filename or "файл")[:255],
        content_type=nogas_service.resolve_content_type(ext, file.content_type),
        size_bytes=size,
        uploaded_by_id=actor.id,
    )
    session.add(item)
    await session.flush()
    await write_audit(
        session,
        action="noga.file_uploaded",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga.id),
        payload={"kind": kind.value, "size_bytes": size},
    )
    await session.commit()

    # created_at приходит из server_default — без refresh оно не подгружено,
    # а ленивое чтение в async-сессии упало бы MissingGreenlet.
    await session.refresh(item)
    return NogaFileOut(
        id=item.id,
        kind=item.kind,
        original_name=item.original_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
        uploaded_by_name=actor.display_name,
    )


async def get_file_or_404(session: AsyncSession, noga_id: int, file_id: int) -> NogaFile:
    item = await session.get(NogaFile, file_id)
    if item is None or item.noga_id != noga_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Файл не найден"},
        )
    return item


@router.get("/{noga_id}/files/{file_id}")
async def download_noga_file(
    noga_id: int,
    file_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_READ))],
) -> FileResponse:
    require_personal(actor)
    item = await get_file_or_404(session, noga_id, file_id)
    path = nogas_service.absolute_path(item.stored_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Файл потерялся на диске"},
        )
    return FileResponse(
        path,
        media_type=item.content_type,
        filename=item.original_name,
        content_disposition_type="inline",
    )


@router.delete("/{noga_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_noga_file(
    noga_id: int,
    file_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permission(NOGAS_MANAGE))],
) -> None:
    require_personal(actor)
    require_own(actor, await load_noga(session, noga_id))
    item = await get_file_or_404(session, noga_id, file_id)
    stored_path = item.stored_path
    await write_audit(
        session,
        action="noga.file_deleted",
        actor_user_id=actor.id,
        target_type="noga",
        target_id=str(noga_id),
        payload={"kind": item.kind.value},
    )
    await session.delete(item)
    await session.commit()
    nogas_service.delete_stored(stored_path)
