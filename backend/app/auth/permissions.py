from __future__ import annotations

from app.db.models import UserRole

# Permission strings used by API and frontend
USERS_MANAGE = "users:manage"
USERS_READ = "users:read"
USERS_DELETE = "users:delete"
# Своё отображаемое имя. Есть у всех, кроме ноги: ей имя ставит тот, кто её завёл.
PROFILE_RENAME = "profile:rename"
DASHBOARD_GLOBAL = "dashboard:global"
OPERATIONS_ALL = "operations:all"
OPERATIONS_OWN = "operations:own"
OPERATIONS_CONFIRM = "operations:confirm"
OPERATIONS_PAYOUT = "operations:payout"
SETTINGS_MANAGE = "settings:manage"
CITIES_MANAGE = "cities:manage"
CITIES_READ = "cities:read"
# «Чужие» скоупы: без них роль правит только то, что завела сама (админ).
CITIES_ALL = "cities:all"
NOGAS_ALL = "nogas:all"
NOGAS_MANAGE = "nogas:manage"
NOGAS_READ = "nogas:read"
# Паспорта, адрес и телефоны ног. Есть и у админа: если нога другого админа
# пропала со связи, с ней надо уметь связаться напрямую.
NOGAS_PERSONAL = "nogas:personal"
RAZGRUZ_MANAGE = "razgruz:manage"
RAZGRUZ_READ = "razgruz:read"
RAZGRUZ_ALL = "razgruz:all"
CHAT_READ = "chat:read"
CHAT_WRITE = "chat:write"
CHAT_DIRECT = "chat:direct"
CHAT_DELETE_OWN = "chat:delete_own"
CHAT_DELETE_ANY = "chat:delete_any"

ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.owner: frozenset(
        {
            USERS_MANAGE,
            USERS_READ,
            USERS_DELETE,
            PROFILE_RENAME,
            DASHBOARD_GLOBAL,
            OPERATIONS_ALL,
            OPERATIONS_OWN,
            OPERATIONS_CONFIRM,
            OPERATIONS_PAYOUT,
            SETTINGS_MANAGE,
            CITIES_MANAGE,
            CITIES_READ,
            CITIES_ALL,
            NOGAS_MANAGE,
            NOGAS_READ,
            NOGAS_ALL,
            NOGAS_PERSONAL,
            RAZGRUZ_MANAGE,
            RAZGRUZ_READ,
            RAZGRUZ_ALL,
            CHAT_READ,
            CHAT_WRITE,
            CHAT_DIRECT,
            CHAT_DELETE_OWN,
            CHAT_DELETE_ANY,
        }
    ),
    UserRole.right_hand: frozenset(
        {
            USERS_MANAGE,
            USERS_READ,
            PROFILE_RENAME,
            DASHBOARD_GLOBAL,
            OPERATIONS_ALL,
            OPERATIONS_OWN,
            OPERATIONS_CONFIRM,
            OPERATIONS_PAYOUT,
            CITIES_MANAGE,
            CITIES_READ,
            CITIES_ALL,
            NOGAS_MANAGE,
            NOGAS_READ,
            NOGAS_ALL,
            NOGAS_PERSONAL,
            RAZGRUZ_MANAGE,
            RAZGRUZ_READ,
            RAZGRUZ_ALL,
            CHAT_READ,
            CHAT_WRITE,
            CHAT_DIRECT,
            CHAT_DELETE_OWN,
        }
    ),
    # Админ ведёт свой участок: заводит и правит только собственные города, ноги и
    # разгрузы (нет *:all), но читает справочники и личные данные любых ног.
    UserRole.admin: frozenset(
        {
            USERS_READ,
            PROFILE_RENAME,
            DASHBOARD_GLOBAL,
            OPERATIONS_ALL,
            OPERATIONS_OWN,
            OPERATIONS_CONFIRM,
            OPERATIONS_PAYOUT,
            CITIES_MANAGE,
            CITIES_READ,
            NOGAS_MANAGE,
            NOGAS_READ,
            NOGAS_PERSONAL,
            RAZGRUZ_READ,
            RAZGRUZ_MANAGE,
            CHAT_READ,
            CHAT_WRITE,
            CHAT_DIRECT,
            CHAT_DELETE_OWN,
        }
    ),
    UserRole.noga: frozenset(
        {
            OPERATIONS_OWN,
            CITIES_READ,
        }
    ),
}

ROLE_LABELS_RU: dict[UserRole, str] = {
    UserRole.owner: "Owner",
    UserRole.right_hand: "Правая рука",
    UserRole.admin: "Администратор",
    UserRole.noga: "Нога",
}


def permissions_for(role: UserRole) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def can_assign_role(actor_role: UserRole, target_role: UserRole) -> bool:
    """Owner can assign any role. Right hand cannot assign/manage owner."""
    if actor_role == UserRole.owner:
        return True
    if actor_role == UserRole.right_hand:
        return target_role != UserRole.owner
    return False


def can_modify_user(actor_role: UserRole, target_role: UserRole) -> bool:
    if actor_role == UserRole.owner:
        return True
    if actor_role == UserRole.right_hand:
        return target_role != UserRole.owner
    return False
