from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import User, UserRole, UserStatus


async def bootstrap_owners(session: AsyncSession, settings: Settings) -> None:
    """Upsert Owner accounts from OWNER_TELEGRAM_IDS env."""
    for tid in settings.owner_ids:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()
        if user is None:
            session.add(
                User(
                    telegram_id=tid,
                    display_name="Owner",
                    role=UserRole.owner,
                    status=UserStatus.active,
                )
            )
        else:
            user.role = UserRole.owner
            if user.status != UserStatus.active:
                user.status = UserStatus.active
            if not user.display_name:
                user.display_name = "Owner"
    await session.commit()
