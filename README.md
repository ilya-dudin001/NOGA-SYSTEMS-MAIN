# NOGA Systems

Telegram-бот + Mini App для учёта операций. Доступ по allowlist (`telegram_id`) с ролями Owner / Правая рука / Администратор / Нога.

- Фронтенд (GitHub Pages): https://ilya-dudin001.github.io/NOGA-SYSTEMS-MAIN/
- Backend: `backend/` (FastAPI + aiogram + SQLite)

Подробный контекст для разработки: [AGENTS.md](AGENTS.md).

## Быстрый старт (локально)

### 1. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # или: cp .env.example .env
```

Заполните `.env`:

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от @BotFather |
| `JWT_SECRET` | Длинная случайная строка |
| `OWNER_TELEGRAM_IDS` | Ваш Telegram ID (узнать у @userinfobot) |
| `WEBAPP_URL` | URL Mini App |
| `CORS_ORIGINS` | Origin фронта через запятую |
| `DEV_AUTH_ENABLED` | `true` для входа из браузера без Telegram |
| `DEV_AUTH_SECRET` | Секрет для `POST /api/auth/dev` |

Запуск:

```bash
mkdir data
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Проверка: `GET http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.

Бот стартует вместе с API (long polling). Напишите боту `/start` с аккаунта из `OWNER_TELEGRAM_IDS`.

### 2. Frontend

Откройте `index.html` через любой static server (или GitHub Pages).

По умолчанию API: `http://127.0.0.1:8000`. Переопределение:

```
index.html?api=https://your-vps.example.com
```

или до загрузки скриптов:

```html
<script>window.__NOGA_CONFIG__ = { apiBase: "https://your-vps.example.com" };</script>
```

В браузере без Telegram появится форма Dev-входа (нужны `DEV_AUTH_ENABLED=true` и пользователь в БД).

### 3. BotFather

1. Создайте бота, скопируйте токен в `.env`.
2. `/setmenubutton` или кнопка из `/start` → URL = `WEBAPP_URL`.
3. Для продакшена Mini App должен быть на **HTTPS**.

## Docker (VPS)

```bash
cd backend
cp .env.example .env   # заполнить
mkdir -p data
docker compose up -d --build
```

Или systemd: unit с `WorkingDirectory=/opt/noga/backend` и  
`ExecStart=/opt/noga/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Перед CORS укажите `https://ilya-dudin001.github.io` в `CORS_ORIGINS`.  
На фронте выставьте `apiBase` на публичный URL API (HTTPS).

## Команды бота

| Команда | Кто | Описание |
|---------|-----|----------|
| `/start` | allowlist | Кнопка WebApp |
| `/whoami` | allowlist | Профиль |
| `/users` | manage/read | Список |
| `/adduser <id> <role>` | manage | Добавить |
| `/setrole <id> <role>` | manage | Сменить роль |
| `/block` / `/unblock` | manage | Блок |

Роли: `owner`, `right_hand`, `admin`, `noga`.

## API (кратко)

- `POST /api/auth/telegram` — `{ "initData": "..." }` → JWT + профиль
- `POST /api/auth/dev` — только при `DEV_AUTH_ENABLED`
- `GET /api/me` — профиль и `permissions`
- `GET|POST /api/users`, `PATCH|DELETE /api/users/{id}`
- `GET /api/dashboard/summary` — пока нули, со скоупом по роли

Миграции Alembic: `alembic upgrade head` (из `backend/`). При старте также вызывается `create_all` + bootstrap Owner.

## Чеклист приёмки

1. **Owner** (`OWNER_TELEGRAM_IDS`): `/start` → кнопка → кабинет с именем и ролью Owner; экран «Пользователи» (Профиль / кнопка).
2. **Нога**: Owner добавляет через `/adduser <id> noga` или UI → у ноги свой кабинет, карточка общего оборота скрыта, нет управления пользователями.
3. **Посторонний**: `/start` и Mini App → «Доступ закрыт» / `NOT_ALLOWED`.
4. Dev: браузер + `DEV_AUTH_ENABLED` → вход по ID Owner работает.

## Структура

```
/
  index.html
  assets/css|js|img
  reference/
  backend/app/          # FastAPI + bot
  backend/alembic/
  AGENTS.md
  README.md
```
