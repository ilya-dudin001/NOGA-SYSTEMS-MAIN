from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
        )
    )
