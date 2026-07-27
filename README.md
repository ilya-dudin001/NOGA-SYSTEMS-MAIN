# NOGA Systems

Telegram-бот + Mini App для учёта операций. Доступ по allowlist (`telegram_id`) с ролями Owner / Правая рука / Администратор / Нога.

- Фронтенд (GitHub Pages): https://ilya-dudin001.github.io/NOGA-SYSTEMS-MAIN/
- Backend: `backend/` (FastAPI + aiogram + SQLite)

Подробный контекст для разработки: [AGENTS.md](AGENTS.md).
Обновление боевого сервера: [DEPLOY.md](DEPLOY.md).

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

## Деплой на VPS

Фронтенд уезжает на GitHub Pages сам после пуша в `main`. Backend обновляется на сервере:

```bash
ssh user@ваш-сервер
sudo bash /opt/noga/backend/deploy/deploy.sh
```

Скрипт делает `git pull`, при необходимости переустанавливает зависимости, снимает бэкап
базы, накатывает миграции и перезапускает `noga-api` с проверкой `/api/health`.

Первичная установка, ручной деплой по шагам, откат, Docker-вариант и диагностика —
в [DEPLOY.md](DEPLOY.md). Готовый systemd-unit: `backend/deploy/noga-api.service`.

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
| `/deleteuser <id>` | owner | Удалить (с подтверждением) |

Роли: `owner`, `right_hand`, `admin`, `noga`.

Удаление доступно только Owner — и в боте, и в Mini App (кнопка «Удалить» на карточке
пользователя). Себя удалить нельзя. После удаления выданный ранее JWT перестаёт
работать сразу же: `/api/me` вернёт 401.

## API (кратко)

- `POST /api/auth/telegram` — `{ "initData": "..." }` → JWT + профиль
- `POST /api/auth/dev` — только при `DEV_AUTH_ENABLED`
- `GET /api/me` — профиль и `permissions`
- `GET|POST /api/users`, `PATCH|DELETE /api/users/{id}`
- `GET|POST /api/cities`, `GET|PATCH|DELETE /api/cities/{id}`
- `GET|POST /api/nogas`, `PATCH|DELETE /api/nogas/{id}`
- `GET|POST /api/razgruzy`, `PATCH|DELETE /api/razgruzy/{id}`
- `GET /api/dashboard/summary` — по операциям нули, блок `cities` живой

Миграции Alembic: `alembic upgrade head` (из `backend/`). При старте также вызывается `create_all` + bootstrap Owner.

Миграция `003_city_status_razgruzy` заменяет у города флаг `is_active` на статус:
выключенные города переезжают в «На стопе (полностью)», остальные — в «В работе».

Если рабочая база была создана через `create_all` и таблицы `alembic_version` в ней нет,
перед обновлением отметьте текущую ревизию, иначе Alembic начнёт с самого начала и
упрётся в уже существующие таблицы:

```bash
alembic stamp 002_cities_nogas
alembic upgrade head
```

## Управление ногами

Нога — исполнитель, привязанный к городу. У ноги есть имя, город и признак
**Тест / Не тест** (тестовые ноги помечаются бейджем и в будущем не пойдут в
реальный оборот). Отдельно от этого есть роль `noga` — это доступ к боту, а
ноги из справочника аккаунтов не требуют.

Экран открывается кнопкой «Ноги» на дашборде (рядом с «Пользователями»).
Управляют Owner и Правая рука; Администратор видит список, но не меняет его.

Города — отдельный справочник. В форме добавления ноги можно выбрать
существующий город или пункт «+ Новый город» — он создастся вместе с ногой.
Совпадение имени ищется без учёта регистра, поэтому «тула» не создаст дубликат
для «Тула». Пара имя + город уникальна: одинаковых ног в одном городе не будет.

Ногу можно переключить между тест/рабочая, выключить (`is_active`) или удалить.

## Управление городами

Экран «Города» открывается плашкой на дашборде — она же показывает сводку: сколько
городов в работе, на временном и на полном стопе, а также общее число ног и разгрузов.

У города есть:

- **Статус**: «В работе», «На стопе (временно)», «На стопе (полностью)». Переключается
  прямо на карточке, без захода в форму.
- **Порог запуска** — произвольная сумма и валюта: рубли, доллары, узбекские сумы,
  киргизские сомы, казахские тенге, азербайджанские манаты, белорусские рубли,
  молдавские леи, приднестровские рубли. Сумма и валюта задаются только вместе.
- **Ноги** — подтягиваются из справочника ног по привязке к городу: имя, тест/рабочая,
  кто добавил и когда.
- **Разгрузы** — несколько на город, один разгруз может обслуживать несколько городов.
  По каждому видно комиссию, контакт, кто добавил, дату и сколько заказов через него
  успешно разгружено.
- **Последние 5 заказов** — раздел готов, но пока пуст: операций в системе ещё нет.

Город можно добавить, изменить, удалить и переключить его статус. Удаление блокируется,
пока в городе остались ноги — сначала перенесите или удалите их. Управляют Owner и
Правая рука, Администратор видит список без права правки.

## Разгрузы

Отдельный экран «Разгрузы»: название, комиссия в процентах, контакт, включён/выключен.
Разгруз нельзя удалить, пока он привязан хотя бы к одному городу. Роль «Нога» разгрузы
не видит вообще — ни на своём экране, ни в составе города.

## Тесты

Из `backend/` с активированным venv:

```bash
python tests/test_delete_user.py
python tests/test_nogas.py
python tests/test_cities.py
```

Каждый скрипт использует свою БД (`data/test_delete.db`, `data/test_nogas.db`,
`data/test_cities.db`) и не трогает рабочую.

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
