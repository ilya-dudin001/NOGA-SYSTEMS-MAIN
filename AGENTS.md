# NOGA Systems — контекст для агентов

## Назначение

NOGA Systems (EM 3.5 — Operations) — закрытая система учёта операций:

- **Telegram-бот** (aiogram) — точка входа, команды, allowlist
- **Telegram Mini App** — веб-интерфейс (фронтенд в корне репозитория)
- **Backend API** (FastAPI) — авторизация, пользователи, данные
- **БД** — SQLite (aiosqlite), позже легко перейти на PostgreSQL

Демо фронтенда: https://ilya-dudin001.github.io/NOGA-SYSTEMS-MAIN/

Репозиторий: `ilya-dudin001/NOGA-SYSTEMS-MAIN` (публичный — секреты только в `.env` на сервере).

## Роли

Из референса `reference/a_dark_moody_ui_concept_poster_app_design_mockup.png`:

| Роль | Код | Доступ |
|------|-----|--------|
| Owner | `owner` | Полный доступ: пользователи, настройки, все операции |
| Правая рука | `right_hand` | Операции, города/ноги/кошельки; не меняет owner и не удаляет пользователей |
| Администратор | `admin` | Подтверждения и выплаты; список пользователей — только чтение |
| Нога | `noga` | Только свои операции; без общего оборота |

Доступ **по приглашению**: в системе только пользователи из таблицы `users` (allowlist по `telegram_id`). Первый Owner создаётся из `OWNER_TELEGRAM_IDS` при старте.

## Авторизация

1. Mini App передаёт `Telegram.WebApp.initData`
2. Backend проверяет HMAC-SHA256 (секрет = токен бота) и TTL `auth_date`
3. Ищет `telegram_id` в `users` со статусом `active`
4. Выдаёт JWT; роль всегда с сервера, клиенту не доверяем

Dev-вход (`POST /api/auth/dev`) только при `DEV_AUTH_ENABLED=true`.

## Дизайн

- Токены в `assets/css/tokens.css`: фон `#0B0B0B`, золото `#D4AF37`, статусы amber/blue/green/red
- Мобильный фрейм 390–430px, нижний таббар 5 пунктов + FAB «+»
- Референсы: `reference/dev-dashboard.png`, постер в `reference/`
- `index.html` — дашборд после авторизации (раньше демо с захардкоженными данными)

## Стек

- Python 3.12, aiogram 3.x, FastAPI, uvicorn
- SQLAlchemy 2.0 async + aiosqlite, Alembic, PyJWT, pydantic-settings
- Бот: long polling (webhook опционально позже)
- Деплой API: VPS + SQLite; фронт: GitHub Pages

## Структура

```
/
  index.html          # Mini App shell
  assets/             # css, js, img
  reference/          # дизайн-мокапы
  backend/            # FastAPI + aiogram
  AGENTS.md
  README.md
```

## Управление пользователями

- Команды бота: `/adduser`, `/setrole`, `/block`, `/unblock`, `/users`, `/deleteuser`
- Экран «Пользователи» в Mini App (Owner / right_hand с правом `users:manage`)
- Удаление (`users:delete`) — только Owner; общая логика в `delete_user_account()`
  (`backend/app/services/users.py`), её используют и API, и бот
- Диалоги в Mini App — через `NogaTelegram.confirmAction/notify`, а не `window.confirm/alert`

## Ноги и города

- Таблица `nogas`: `name`, `city_id`, `is_test`, `is_active`; UNIQUE (`name`, `city_id`)
- Таблица `cities`: `name` (UNIQUE), `is_active`
- Нога из справочника — не то же самое, что пользователь с ролью `noga` (аккаунт не нужен)
- Права: `nogas:manage` / `cities:manage` — owner, right_hand; `nogas:read` — + admin;
  `cities:read` — все роли (нужно для форм операций)
- API: `/api/nogas` (GET с фильтрами `city_id`, `include_test`, `only_active`; POST, PATCH, DELETE),
  `/api/cities` (GET, POST, PATCH)
- При создании ноги город передаётся как `city_id` **или** `city_name`
  (создаётся при отсутствии; сравнение без учёта регистра идёт в Python,
  потому что `lower()` в SQLite не знает кириллицы)
- В `PATCH /api/nogas/{id}` дубликат проверяется **до** мутации объекта,
  иначе autoflush перед SELECT упирается в UNIQUE и отдаёт 500 вместо 409
- `Noga.city` объявлена `lazy="raise"`: грузите через `selectinload`,
  а после смены города — с `populate_existing=True`, иначе вернётся старый город
- Фронтенд: `assets/js/views.js` переключает `viewHome` / `viewUsers` / `viewNogas`,
  экран ног — `assets/js/screens/nogas.js`

## Что ещё не сделано

Операции, кошельки, фото, уведомления — следующие этапы. `GET /api/dashboard/summary` пока возвращает нули со скоупом по роли. Отдельного экрана управления городами нет: города создаются из формы добавления ноги. Команд бота для ног тоже пока нет — только Mini App.
