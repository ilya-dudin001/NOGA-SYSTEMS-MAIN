from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ChatRoom, ChatRoomKind, User, UserRole, UserStatus


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


async def bootstrap_chat_rooms(session: AsyncSession) -> None:
    """Ensure the fixed internal chat rooms exist for create_all-based installs."""
    rooms = (
        ("general", "Общий", 10),
        ("team", "Команда", 20),
    )
    for slug, title, sort_order in rooms:
        room = await session.scalar(select(ChatRoom).where(ChatRoom.slug == slug))
        if room is None:
            session.add(
                ChatRoom(
                    kind=ChatRoomKind.system,
                    slug=slug,
                    title=title,
                    is_active=True,
                    sort_order=sort_order,
                )
            )
            continue
        room.kind = ChatRoomKind.system
        room.title = title
        room.direct_key = None
        room.is_active = True
        room.sort_order = sort_order
    await session.commit()
