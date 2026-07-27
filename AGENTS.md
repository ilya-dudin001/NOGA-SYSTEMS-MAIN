# NOGA Systems — контекст для агентов

## Назначение

NOGA Systems (EM 3.5 — Operations) — закрытая система учёта операций для рабочей команды:

- **Telegram-бот** (aiogram) — точка входа, команды, allowlist
- **Telegram Mini App** — веб-интерфейс (фронтенд в корне репозитория)
- **Backend API** (FastAPI) — авторизация, пользователи, справочники, данные
- **БД** — SQLite (aiosqlite), позже легко перейти на PostgreSQL

Предмет учёта: **какие ноги есть в каком городе**, через какие **разгрузы** они работают,
от каких сумм, с какой комиссией, контакты — и операции поверх этих справочников.

Демо фронтенда: https://ilya-dudin001.github.io/NOGA-SYSTEMS-MAIN/
Репозиторий: `ilya-dudin001/NOGA-SYSTEMS-MAIN` (публичный — секреты только в `.env` на сервере).

## Терминология — обязательно

**Слово «курьер» в проекте запрещено.** Ни в коде, ни в UI, ни в комментариях, ни в коммитах,
ни в ответах пользователю. Всегда: «нога», «ноги», «нет ног», «ноге», `noga`, `nogas`.
Это не стилистика, а требование заказчика.

| Термин | Значение | Код |
|--------|----------|-----|
| **Нога** | Исполнитель, привязанный к городу. Не обязан иметь Telegram-аккаунт в системе | `Noga`, `nogas` |
| **Город** | Ноги, разгрузы, порог запуска и статус работы | `City`, `cities` |
| **Разгруз** | Сервис международных переводов: комиссия, контакт, привязка к городам | `Razgruz`, `razgruzy` |
| **Операция / заказ** | Единица учёта поверх ног/городов/разгрузов | ещё не реализовано |
| **Тестовая нога** | `is_test=True`, помечается бейджем, в реальный оборот не идёт | |

Роль `noga` (доступ к боту) и нога из справочника — **разные сущности**. Нога из справочника
аккаунта не требует.

## Роли и права

| Роль | Код | Смысл |
|------|-----|-------|
| Owner | `owner` | Полный доступ, единственный кто удаляет пользователей |
| Правая рука | `right_hand` | Всё кроме управления owner'ами и удаления пользователей |
| Администратор | `admin` | Подтверждения и выплаты; справочники — только чтение |
| Нога | `noga` | Только свои операции; без общего оборота |

Матрица (`backend/app/auth/permissions.py` — единственный источник правды):

| Право | owner | right_hand | admin | noga |
|-------|:-----:|:----------:|:-----:|:----:|
| `users:read` / `users:manage` | + / + | + / + | + / − | − / − |
| `users:delete` | + | − | − | − |
| `dashboard:global` | + | + | + | − |
| `operations:all` / `operations:own` | + / + | + / + | + / + | − / + |
| `operations:confirm` / `operations:payout` | + | + | + | − |
| `settings:manage` | + | − | − | − |
| `cities:read` / `cities:manage` | + / + | + / + | + / − | + / − |
| `nogas:read` / `nogas:manage` | + / + | + / + | + / − | − / − |
| `razgruz:read` / `razgruz:manage` | + / + | + / + | + / − | − / − |

`cities:read` есть у всех ролей — он нужен для форм операций. Именно поэтому состав
ответа города режется по правам: без `razgruz:read` список `razgruzy` приходит пустым,
без `nogas:read` — пустой список `nogas` (счётчик `nogas_count` остаётся). Иначе роль
`noga` видела бы комиссии разгрузов.

`can_assign_role` / `can_modify_user`: owner может всё; right_hand — всё, кроме действий над owner.

## Авторизация

1. Mini App передаёт `Telegram.WebApp.initData` в `POST /api/auth/telegram`
2. `validate_init_data()` проверяет HMAC-SHA256 (`secret = HMAC("WebAppData", bot_token)`) и TTL `auth_date`
3. Ищем `telegram_id` в `users`; нет записи → `NOT_ALLOWED`, `status=blocked` → `BLOCKED`
4. Выдаём JWT (`sub` = `users.id`, TTL `JWT_EXPIRE_HOURS`, по умолчанию 12 ч)
5. Каждый запрос `get_current_user` перечитывает пользователя из БД и проверяет статус,
   поэтому **роль и права никогда не берутся из токена** — удаление или блокировка
   действуют мгновенно, ранее выданный JWT сразу перестаёт работать

Все попытки пишутся в `auth_attempts`, значимые действия — в `audit_log` (`write_audit`).
Dev-вход `POST /api/auth/dev` работает только при `DEV_AUTH_ENABLED=true` (иначе 404).

## Данные

```
users         telegram_id UNIQUE, display_name, role, status, created_by_id, last_seen_at
cities        name UNIQUE, status, min_amount, min_amount_currency, created_by_id
nogas         name, city_id → cities, is_test, is_active     UNIQUE (name, city_id)
razgruzy      name UNIQUE, commission_percent, contact, is_active, created_by_id
city_razgruzy city_id → cities, razgruz_id → razgruzy        UNIQUE (city_id, razgruz_id)
audit_log     actor_user_id (nullable), action, target_type, target_id, payload JSON
auth_attempts telegram_id, success, reason
```

Enum'ы (`user_role`, `user_status`, `city_status`, `currency`) объявлены
`native_enum=False` — хранятся строками.

- `city_status`: `working` (в работе), `paused` (стоп временно), `stopped` (стоп полностью).
  У города **нет** `is_active` — миграция 003 заменила флаг на статус.
- `currency`: `RUB USD UZS KGS KZT AZN BYN MDL PRB` (последний — приднестровский рубль,
  кода ISO у него нет). `min_amount` и `min_amount_currency` заполняются только парой:
  API отдаёт 400, если задано одно без другого.
- Город ↔ разгруз — многие-ко-многим через `city_razgruzy`.
- Счётчики заказов (`completed_orders` у разгруза, `recent_orders` у города) — заглушки
  на нуле и пустом списке, пока нет таблицы операций.

## Backend

Стек: Python 3.12, FastAPI, aiogram 3.x, SQLAlchemy 2.0 async + aiosqlite, Alembic, PyJWT,
pydantic-settings. Зависимости — `backend/requirements.txt`.

```
backend/app/
  main.py            create_app() + lifespan: create_all → bootstrap_owners → polling бота задачей
  config.py          Settings (pydantic-settings, .env), get_settings() кэшируется lru_cache
  db/                Base, engine, SessionLocal (expire_on_commit=False), get_session, models, bootstrap
  auth/              initdata (HMAC), jwt, deps (get_current_user, require_permission), permissions
  api/               auth, me, users, cities, nogas, razgruzy, dashboard — все под /api
  services/          users, cities (загрузка/сериализация/связи), razgruzy, audit
  bot/               create_bot/create_dispatcher/run_polling, middlewares, handlers/{start,users_cmd}
alembic/versions/    001_initial, 002_cities_nogas, 003_city_status_razgruzy
```

Конвенции:

- Ошибки — всегда `HTTPException(detail={"code": ..., "message": ...})`; фронт читает
  `detail.code` / `detail.message` (`assets/js/api.js`). Сообщения пользователю — по-русски.
- Бизнес-логика, общая для API и бота, живёт в `services/` и кидает `UserActionError(code, message)`
  (пример: `delete_user_account` — её используют и `DELETE /api/users/{id}`, и `/deleteuser`).
- Любое изменяющее действие сопровождается `write_audit(...)` до `commit()`.
- Права проверяются зависимостью `require_permission("...")`, не вручную в теле хендлера.
- Бот: `DbSessionMiddleware` даёт `session` на апдейт, `UserResolveMiddleware` — `db_user` и
  `is_allowed`; хендлер начинается с проверки `is_allowed` и `has_permission`.

## API

| Метод | Путь | Право |
|-------|------|-------|
| POST | `/api/auth/telegram`, `/api/auth/dev` | — |
| GET | `/api/me` | авторизация |
| GET/POST | `/api/users`, PATCH `/api/users/{id}` | `users:read` / `users:manage` |
| DELETE | `/api/users/{id}` | `users:delete` (только owner) |
| GET/POST | `/api/cities`, GET/PATCH/DELETE `/api/cities/{id}` | `cities:read` / `cities:manage` |
| GET/POST | `/api/nogas`, PATCH/DELETE `/api/nogas/{id}` | `nogas:read` / `nogas:manage` |
| GET/POST | `/api/razgruzy`, PATCH/DELETE `/api/razgruzy/{id}` | `razgruz:read` / `razgruz:manage` |
| GET | `/api/dashboard/summary` | авторизация; операции — нули, блок `cities` живой |
| GET | `/api/health` | — |

`GET /api/nogas` принимает `city_id`, `include_test` (по умолчанию true), `only_active` (false).
`POST /api/nogas` принимает город как `city_id` **или** `city_name` (создастся при отсутствии).

`GET /api/cities` отдаёт список без ног, `GET /api/cities/{id}` — детали с `nogas`
(включая `created_by_name`) и `recent_orders`. `POST/PATCH /api/cities` принимают
`razgruz_ids` — полный новый список связей, а не дельту. Удаление города блокируется
(409), пока в нём есть ноги; удаление разгруза — пока он привязан хоть к одному городу.

Сброс порога запуска делается явными `null` в обоих полях сразу: PATCH различает
«не передано» и «передано null» через `model_fields_set`.

## Бот

Long polling запускается фоновой задачей внутри lifespan API (`BOT_POLLING_ENABLED`); падение
polling логируется, но API продолжает работать. Команды: `/start` (кнопка WebApp + menu button),
`/whoami`, `/users`, `/adduser <id> <role>`, `/setrole`, `/block`, `/unblock`,
`/deleteuser <id>` (инлайн-подтверждение, только owner). Роли парсятся по алиасам, включая
русские («админ», «нога», «правая_рука»). Команд для ног и городов пока нет — только Mini App.

## Фронтенд

**Только статика: ванильный JS, без React/Vue/Svelte и подобных фреймворков.** Небольшие
библиотеки допустимы, сборки нет — файлы отдаются как есть (GitHub Pages).

Конвенции, которым нужно следовать:

- Каждый файл — IIFE `(function (global) { "use strict"; ... })(window)`, экспорт одним
  объектом в `window`: `NOGA_CONFIG`, `NogaTelegram`, `NogaApi`, `NogaRoles`, `NogaDict`,
  `NogaViews`, `NogaDashboard`, `NogaNoAccess`, `NogaUsers`, `NogaNogas`, `NogaCities`,
  `NogaRazgruzy`. Исключение — `auth.js`: он ничего не экспортирует, только запускает
  `bootstrap()`.
- Стиль ES5-совместимый (`var`, `Array.prototype.forEach.call`), кроме `async/await` в запросах.
- Порядок подключения в `index.html` важен: `config → telegram → api → roles → dict →
  views → screens/* → auth.js` (auth.js стартует приложение по `DOMContentLoaded`).
- Общие справочники (статусы городов, валюты, форматирование чисел, дат и процентов) —
  в `assets/js/dict.js` (`NogaDict`). Новые списки значений класть туда, а не дублировать
  по экранам; `NogaDashboard.format` тоже делегирует в `NogaDict.formatNumber`.
- Экраны — `<div class="view" id="viewXxx">` внутри `#appMain`; переключение только через
  `NogaViews.show("viewXxx")` (список id захардкожен в `views.js` — новый экран туда добавлять).
- Данные в DOM — через `textContent`, не через конкатенацию в `innerHTML` (шаблон структуры
  можно собирать `innerHTML`, значения подставлять отдельно). Так уже сделано в карточках.
- Диалоги — `NogaTelegram.confirmAction/notify`, **не** `window.confirm/alert`: внутри
  Telegram WebView нативные диалоги браузера игнорируются.
- Видимость по правам — `NogaRoles.can("perm")`; сервер всё равно проверяет повторно.
- Токен хранится только в памяти (`api.js`), в localStorage не кладётся — перезагрузка
  означает повторную авторизацию через initData. 401 → `setUnauthorizedHandler` → экран gate.
- `apiBase`: дефолт из `config.js` (`http://127.0.0.1:8000`), в проде переопределён инлайн-скриптом
  в `index.html` (`https://noga-api.duckdns.org`), и всё это перебивает `?api=https://...`.

CSS: три файла — `tokens.css` (переменные), `app.css` (дашборд, таббар, FAB),
`screens.css` (splash, gate, формы, карточки, dev-панель). Именование БЭМ-подобное
(`user-card__badge--blocked`), состояния — `is-active` / `is-hidden` / `is-visible`.
Токены: фон `#0B0B0B`, золото `#D4AF37`, статусы amber/blue/green/red, `--radius*`, `--ease`.
Мобильный фрейм 390–430px, нижний таббар: 5 пунктов + FAB «+».

## Грабли (проверено на практике)

- Все связи объявлены `lazy="raise"` — грузить только через `selectinload`, а после
  изменения перечитывать с `execution_options(populate_existing=True)`, иначе вернутся
  старые данные (см. `load_noga` в `api/nogas.py`, `cities_service.load`).
- Перед `session.delete()` объекта со связью «многие-ко-многим» её коллекция должна быть
  **загружена**: ORM снимает строки `city_razgruzy` сам, а с `lazy="raise"` вместо этого
  прилетит исключение. Поэтому `razgruzy_service.load(..., with_cities=True)` перед удалением.
  Полагаться на `ON DELETE CASCADE` нельзя: в SQLite внешние ключи по умолчанию выключены.
- В `PATCH` для ног, городов и разгрузов все SELECT'ы (проверка дубликата, существования
  разгрузов) идут **до** мутации объекта: иначе autoflush перед SELECT упирается в UNIQUE
  и отдаёт 500 вместо 409.
- Регистронезависимое сравнение городов делается в Python (`services/cities.find_by_name`),
  потому что `lower()` в SQLite не знает кириллицы.
- `delete_user_account` обнуляет `created_by_id` и `audit_log.actor_user_id` перед удалением:
  на PostgreSQL FK иначе не дадут удалить, на SQLite остались бы «мёртвые» id.
- Схема создаётся дважды: `Base.metadata.create_all` в lifespan **и** миграции Alembic.
  Новую таблицу нужно добавлять и в модели, и в `alembic/versions/`, иначе прод разъедется с dev.
- `expire_on_commit=False` — после `commit()` объекты остаются пригодны, но для полей с
  `server_default` (`created_at`) нужен `refresh()`.

## Запуск и тесты

```bash
cd backend && .venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python tests/test_delete_user.py
python tests/test_nogas.py
python tests/test_cities.py
```

Тесты — самостоятельные скрипты на `TestClient` (не pytest), каждый со своей БД в `data/`;
переменные окружения выставляются в начале файла до импорта `app`, с `get_settings.cache_clear()`.
Новый функционал покрывать в том же стиле.

Фронтенд можно прогонять в `jsdom` (Node): загрузить `index.html`, выполнить скрипты в
порядке из `index.html`, подменить `window.fetch` фейковым API и кликать по кнопкам.
В jsdom нужно доопределить `matchMedia` и `Element.prototype.scrollIntoView` — в браузере
и Telegram WebView они есть.

Прод: VPS + Docker (`backend/docker-compose.yml`, `Dockerfile`, том `./data`) или systemd
(`backend/deploy/noga-api.service`, репозиторий в `/opt/noga`, сервис `noga-api` от юзера
`noga`); фронт — GitHub Pages, едет сам по пушу в `main`. `CORS_ORIGINS` должен содержать
origin фронта.

Выкатка бэкенда — `sudo bash /opt/noga/backend/deploy/deploy.sh` (pull → зависимости →
бэкап базы → `alembic upgrade head` → рестарт → `/api/health`, с автоподъёмом сервиса при
ошибке). Подробности, разовый `alembic stamp` для баз из `create_all` и откат — в
[DEPLOY.md](DEPLOY.md). Скрипты и unit-файлы держим с LF (`.gitattributes`), иначе bash на
сервере спотыкается о `\r`.

## Экраны Mini App

| Экран | id | Файл | Кому виден |
|-------|----|------|-----------|
| Дашборд | `viewHome` | `screens/dashboard.js` | всем |
| Пользователи | `viewUsers` | `screens/users.js` | `users:read` |
| Ноги | `viewNogas` | `screens/nogas.js` | `nogas:read` |
| Города | `viewCities` | `screens/cities.js` | `cities:read` |
| Разгрузы | `viewRazgruzy` | `screens/razgruzy.js` | `razgruz:read` |

Вход на экраны — кнопки на дашборде (`usersEntry`, `nogasEntry`, `razgruzyEntry`) и
плашка городов `citiesCard` со сводкой «в работе / стоп временно / стоп полностью».
Плашка обновляется из `summary.cities`; после изменений на экране городов
`refreshDashboard()` перезапрашивает сводку без анимации счётчиков.

На карточке города: порог запуска, число ног, чипы разгрузов с комиссиями, переключатель
трёх статусов, кнопки «Подробнее» / «Изменить» / «Удалить». «Подробнее» подгружает
`GET /api/cities/{id}`: ноги с автором и датой, разгрузы с комиссией, автором и счётчиком
успешных заказов, блок последних заказов (пока заглушка).

## Состояние на сейчас

Готово: авторизация, роли и права, пользователи (API + бот + экран), ноги, города,
разгрузы (API + экраны), аудит, сводка по городам на дашборде.

Не сделано: **операции/заказы**, кошельки, фото, уведомления. Из-за отсутствия таблицы
операций в дашборде нули по обороту, `completed_orders` у разгруза всегда 0, а
`recent_orders` у города — пустой список; когда появятся операции, заполнять именно эти
поля. Команд бота для городов, ног и разгрузов нет — только Mini App. Вкладки таббара
«Операции», «Поиск» и кнопка FAB ни к чему не привязаны.

Известные мелкие дыры: `index.html` ссылается на `assets/img/logo.png`, которого в репозитории
нет (лежит `bot_logo.png`) — три битые картинки в splash/gate/topbar; папки `reference/` с
мокапами в рабочей копии тоже нет; смена роли в экране пользователей сделана через
`window.prompt`, что внутри Telegram WebView ненадёжно.

Новые справочники делать по образцу городов и разгрузов: таблица + миграция в
`alembic/versions/`, права `сущность:read` / `сущность:manage`, сервис с загрузкой и
сериализацией в `services/`, роутер в `api/`, экран в `assets/js/screens/`, регистрация id
экрана в `views.js`, справочные значения в `dict.js`. Имена таблиц и полей — транслитом от
доменного термина (как `nogas`, `razgruzy`), английские синонимы не изобретать.
