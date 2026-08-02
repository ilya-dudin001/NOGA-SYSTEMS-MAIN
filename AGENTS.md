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
| **Трубка** | Заказ: город, нога, сумма, заказчик и стадия работы | `Trubka`, `trubki` |
| **Тестовая нога** | `is_test=True`, помечается бейджем, в реальный оборот не идёт | |

Роль `noga` (доступ к боту) и нога из справочника — **разные сущности**. Нога из справочника
аккаунта не требует.

## Роли и права

| Роль | Код | Смысл |
|------|-----|-------|
| Owner | `owner` | Полный доступ, единственный кто удаляет пользователей |
| Правая рука | `right_hand` | Всё кроме управления owner'ами и удаления пользователей |
| Администратор | `admin` | Свой участок: заводит и правит **свои** города, ноги и разгрузы, читает чужие |
| Нога | `noga` | Только свои операции; без общего оборота |

Матрица (`backend/app/auth/permissions.py` — единственный источник правды):

| Право | owner | right_hand | admin | noga |
|-------|:-----:|:----------:|:-----:|:----:|
| `users:read` / `users:manage` | + / + | + / + | + / − | − / − |
| `users:delete` | + | − | − | − |
| `profile:rename` | + | + | + | − |
| `dashboard:global` | + | + | + | − |
| `operations:all` / `operations:own` | + / + | + / + | + / + | − / + |
| `operations:confirm` / `operations:payout` | + | + | + | − |
| `settings:manage` | + | − | − | − |
| `cities:read` / `cities:manage` | + / + | + / + | + / + | + / − |
| `cities:all` | + | + | − | − |
| `nogas:read` / `nogas:manage` | + / + | + / + | + / + | − / − |
| `nogas:all` | + | + | − | − |
| `nogas:personal` | + | + | + | − |
| `razgruz:read` / `razgruz:manage` | + / + | + / + | + / + | − / − |
| `razgruz:all` | + | + | − | − |
| `chat:read` / `chat:write` / `chat:direct` | + / + / + | + / + / + | + / + / + | − / − / − |
| `chat:delete_own` / `chat:delete_any` | + / + | + / − | + / − | − / − |
| `places:read` | + | + | + | + |

Чат доступен только owner / right_hand / admin. Роль `noga` не имеет `chat:*`.
Живой UI дополнительно требует `features.chat` (`CHAT_ENABLED` на сервере).

Справочник банкоматов (`places:read`) есть у **всех** ролей, включая `noga`.
Живой UI дополнительно требует `features.places` (`PLACES_ENABLED` на сервере).
Провайдер каркаса — 2ГИС (`DGIS_API_KEY`); без ключа бэкенд отдаёт детерминированные моки.

`cities:read` есть у всех ролей — он нужен для форм операций. Именно поэтому состав
ответа города режется по правам: без `razgruz:read` список `razgruzy` приходит пустым,
без `nogas:read` — пустой список `nogas` (счётчик `nogas_count` остаётся). Иначе роль
`noga` видела бы комиссии разгрузов.

`cities:all` / `nogas:all` / `razgruz:all` — право работать с **чужими** записями. Их нет
у админа, поэтому `*:manage` у него действует только на то, что он завёл сам
(`created_by_id`). Проверки — `can_manage_city` / `require_own_city` в `api/cities.py`,
`can_manage` / `require_own` в `api/nogas.py` и `api/razgruzy.py`; выдача городов и ног
фильтруется через `owner_id` в сервисах, а список разгрузов общий — справочник видят все.
Город, нога и разгруз в ответе несут `can_manage` — фронт по нему рисует иконки правки,
а не гадает по роли. У разгруза рядом есть `created_by_me`: у owner `can_manage` истинно
и для чужих, а подставлять в новый город надо только свои.

`nogas:personal` — отдельное право на паспорта, адрес и телефоны ног. У админа оно **есть**,
и на чужих ногах тоже: если нога соседнего админа пропала со связи, с ней надо связаться
напрямую. Править чужую ногу при этом нельзя. Без права `GET /api/nogas/{id}` отдаёт
`has_personal_access: false`, пустые `address`/`phones`/`telegrams`/`files`.

`profile:rename` — своё отображаемое имя через `PATCH /api/me`. Есть у всех, кроме ноги:
её имя ставит тот, кто её завёл. Роль и статус этим запросом не меняются — лишние поля в
теле игнорируются схемой `MeUpdateIn`.

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
nogas         name, city_id → cities (NULLABLE), is_test, is_active,
              initial_city_name, last_city_name,
              address, phones JSON, telegrams JSON            UNIQUE (name, city_id)
noga_files    noga_id → nogas ON DELETE CASCADE, kind, stored_path, original_name,
              content_type, size_bytes, uploaded_by_id
razgruzy      name UNIQUE, commission_percent, contact, is_active, created_by_id
city_razgruzy city_id → cities, razgruz_id → razgruzy        UNIQUE (city_id, razgruz_id)
trubki        status, city_id → cities, noga_id → nogas, razgruz_id → razgruzy (NULLABLE),
              amount, amount_currency, customer_name/customer_address/delivery (NULLABLE),
              recalculation_amount, usdt_received, report_sent_at, created_by_id, timestamps
trubka_files  trubka_id → trubki ON DELETE CASCADE, kind, stored_path, original_name,
              content_type, size_bytes, uploaded_by_id            UNIQUE (trubka_id, kind)
trubka_events trubka_id → trubki ON DELETE CASCADE, actor_user_id, actor_name,
              action, payload JSON, created_at
chat_rooms    kind system|direct, slug, title, direct_key, sort_order, is_active
chat_room_members room_id, user_id, last_read_message_id
chat_messages room_id, author_id/author_name, body, content JSON, reply_to_id, deleted_at
chat_attachments message_id → chat_messages ON DELETE CASCADE, stored_path, original_name, …
chat_events   type, room_id, target_user_id, payload JSON — durable SSE
chat_mentions message_id, user_id, telegram_status pending|sending|sent|retry|failed|cancelled
place_address_cache city_norm, street_norm, house_norm, lat, lon, provider, external_id,
              queried_at                                         UNIQUE (city_norm, street_norm, house_norm)
place_object_cache source, external_id, kind atm|terminal|poi, name, bank, address,
              lat, lon, street_key, geohash, fetched_at, payload JSON
                                                             UNIQUE (source, external_id)
audit_log     actor_user_id (nullable), action, target_type, target_id, payload JSON
auth_attempts telegram_id, success, reason
```

Контракт чата / SSE / nginx / rollout: [CHAT_SSE.md](CHAT_SSE.md), [DEPLOY.md](DEPLOY.md).
Файлы чата: `UPLOADS_DIR/chat/...`.

Enum'ы (`user_role`, `user_status`, `city_status`, `currency`, `noga_file_kind`,
`trubka_status`, `trubka_delivery`, `trubka_file_kind`, `place_kind`) объявлены `native_enum=False` —
хранятся строками.

- `city_status`: `working` (в работе), `paused` (стоп временно), `stopped` (стоп полностью).
  У города **нет** `is_active` — миграция 003 заменила флаг на статус.
- `currency`: `RUB USD UZS KGS KZT AZN BYN MDL PRB` (последний — приднестровский рубль,
  кода ISO у него нет). `min_amount` и `min_amount_currency` заполняются только парой:
  API отдаёт 400, если задано одно без другого.
- Город ↔ разгруз — многие-ко-многим через `city_razgruzy`.
- `nogas.city_id` может быть `NULL` — нога заведена, но не прикреплена к городу. Прикрепление
  и открепление идут через `noga_ids` в форме города либо `city_id` в PATCH ноги. Из-за
  UNIQUE (`name`, `city_id`) и того, что SQLite считает NULL'ы различными, тёзок среди
  неприкреплённых ног ловим отдельным запросом (`nogas_service.find_clash`).
- `initial_city_name` / `last_city_name` — история привязки **строками**, а не FK: город могут
  удалить, а история должна остаться. Первый город запоминается один раз навсегда, последний
  перезаписывается при каждом прикреплении (`nogas_service.remember_city`). При переименовании
  города снимки подтягиваются (`rename_city_snapshots`), при откреплении — не трогаются,
  поэтому у прикреплённой ноги `last_city_name` всегда равен текущему городу.
- `noga_file_kind`: `passport` (фото паспорта), `passport_selfie` (паспорт вместе с лицом),
  `face_video` (короткое видео). Файлов на каждый вид может быть несколько.
- `phones` и `telegrams` — JSON-массивы строк: их всегда **переприсваивают** новым списком,
  а не мутируют, иначе SQLAlchemy не заметит изменения.
- Ручные `trubka_status`: `zacep` (Зацеп), `zabrali` (Забрали), `vyplacheno`
  (Выплачено), `srez` (Срез). `razgruzhaetsya` (Разгружается) выставляется только
  автоматически после пересчёта и фото денег; сумма захода USDT автоматически ставит
  `vyplacheno`. Статус по умолчанию — `zacep`, поле проиндексировано.
- `trubka_delivery`: `zahod` (нога сама заходит на адрес) и `taxi` (заказчик отправляет
  посылку такси). Вместе с ФИО и адресом поле необязательное и заполняется позже.
- Город и нога у трубки обязательны, разгруз — нет (его выбирают позже). Сумма хранится
  парой `amount` + `amount_currency` из того же справочника валют, что и порог города.
- `recalculation_amount` — сумма пересчёта. Выплата ноге всегда 10%, остаток вычисляется
  в API и не хранится отдельно. `usdt_received` допускает дробную часть.
- `trubka_files`: ровно одно фото каждого вида (`money_photo`, `receipt_photo`), повторная
  загрузка заменяет файл. `trubka_events` — неизменяемая подробная история с именем актора,
  временем, действием и payload; она является основой будущей отчётности.
- Город, ногу и разгруз нельзя удалить, пока на них висит трубка: `DELETE` отдаёт 409 с
  `CITY_HAS_TRUBKI` / `NOGA_HAS_TRUBKI` / `RAZGRUZ_HAS_TRUBKI` (`trubki_service.count_for`).
  Обхода вроде `?detach_nogas=true` здесь нет — заказ без города или ноги бессмыслен.
- Счётчики заказов (`completed_orders` у разгруза, `recent_orders` у города) — заглушки
  на нуле и пустом списке: трубки в карточку города пока не подставляются.

## Backend

Стек: Python 3.12, FastAPI, aiogram 3.x, SQLAlchemy 2.0 async + aiosqlite, Alembic, PyJWT,
pydantic-settings. Зависимости — `backend/requirements.txt`.

```
backend/app/
  main.py            create_app() + lifespan: create_all → bootstrap_owners →
                     bootstrap_chat_rooms → polling бота + chat workers
  config.py          Settings (pydantic-settings, .env), get_settings() кэшируется lru_cache
  db/                Base, engine, SessionLocal (expire_on_commit=False), get_session, models, bootstrap
  auth/              initdata (HMAC), jwt, deps (get_current_user, require_permission), permissions
  api/               auth, me, users, cities, nogas, razgruzy, trubki, chat, dashboard,
                     places — все под /api
  services/          users, cities, nogas, razgruzy, trubki, chat, chat_broker,
                     chat_notifications, audit, geocode, places, places_dgis,
                     places_cache, places_normalize
  bot/               create_bot/create_dispatcher/run_polling, middlewares, handlers/{start,users_cmd}
alembic/versions/    001_initial … 009_city_coords, 010_places_cache
```

ChatBroker и rate limiter — in-memory. Production: ровно один uvicorn process
(`backend/deploy/noga-api.service`). Нельзя `--workers N`, пока broker не в Redis.

Файлы ног лежат не в БД, а на диске: `UPLOADS_DIR` (по умолчанию `./data/uploads`),
раскладка `nogas/{noga_id}/{uuid}{ext}`, в `noga_files.stored_path` — путь относительно
корня загрузок, чтобы каталог можно было переносить. Каталог создаётся в lifespan
(`nogas_service.ensure_uploads_dir`). Лимиты и списки расширений — в `services/nogas.py`
(картинки 25 МБ, видео 200 МБ; тело читается чанками, при превышении файл удаляется).
Фото этапов трубки лежат там же по пути `trubki/{trubka_id}/{uuid}{ext}` и используют
тот же лимит изображений 25 МБ. Вложения чата — `chat/{room_id|message}/{uuid}{ext}`,
лимит суммарно `CHAT_UPLOAD_MAX_TOTAL_MB` (по умолчанию 100 МБ).

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
| PATCH | `/api/me` | `profile:rename` (свой ник) |
| GET/POST | `/api/users`, PATCH `/api/users/{id}` | `users:read` / `users:manage` |
| DELETE | `/api/users/{id}` | `users:delete` (только owner) |
| GET/POST | `/api/cities`, GET/PATCH/DELETE `/api/cities/{id}` | `cities:read` / `cities:manage` |
| GET/POST | `/api/nogas`, GET/PATCH/DELETE `/api/nogas/{id}` | `nogas:read` / `nogas:manage` |
| POST/DELETE | `/api/nogas/{id}/files`, `/api/nogas/{id}/files/{file_id}` | `nogas:manage` + `nogas:personal` |
| GET | `/api/nogas/{id}/files/{file_id}` | `nogas:read` + `nogas:personal` |
| GET/POST | `/api/razgruzy`, PATCH/DELETE `/api/razgruzy/{id}` | `razgruz:read` / `razgruz:manage` |
| GET | `/api/trubki`, `/api/trubki/{id}` | `operations:own` |
| POST/PATCH/DELETE | `/api/trubki`, `/api/trubki/{id}` | `operations:all` |
| POST | `/api/trubki/{id}/recalculation`, `/usdt`, `/report`, `/files` | `operations:all` |
| GET | `/api/trubki/{id}/files/{file_id}` | `operations:own` |
| GET | `/api/dashboard/summary` | авторизация; оборот — нули, блоки `cities` и `trubki` живые |
| GET | `/api/chat/rooms`, `/api/chat/peers` | `chat:read` (+ `CHAT_ENABLED`) |
| POST | `/api/chat/direct` | `chat:direct` |
| GET/POST | `/api/chat/rooms/{id}/messages` | `chat:read` / `chat:write` |
| PATCH | `/api/chat/rooms/{id}/read` | `chat:read` |
| DELETE | `/api/chat/messages/{id}` | `chat:delete_own` или `chat:delete_any` |
| GET | `/api/chat/stream` | `chat:read`, durable SSE |
| GET | `/api/chat/attachments/{id}` | `chat:read` |
| GET/PATCH | `/api/chat/mentions`, `.../{id}/read` | `chat:read` |
| POST | `/api/places/nearby` | `places:read` (+ `PLACES_ENABLED`) |
| GET | `/api/health` | — |

`PATCH /api/me` принимает единственное поле `display_name` и чистит его через
`users_service.normalize_display_name`: лишние пробелы схлопываются, дальше проверка
регуляркой — кириллица, латиница и цифры, между ними пробел, дефис или подчёркивание,
длина 2–32. Пробел и разделители разрешены, иначе не сохранить уже заведённые имена вида
«Иван Петров». Нарушение — 400 `BAD_REQUEST` с текстом для пользователя; в аудит уходит
`user.renamed` со старым и новым значением. Те же правила продублированы на фронте
(`NICK_RE` в `screens/profile.js`), чтобы не гонять заведомо плохой ник на сервер.
Смена ника переживает следующий вход: `sync_profile_from_telegram` перетирает
`display_name` только если оно совпадает с именем из Telegram.

`GET /api/nogas` принимает `city_id`, `include_test` (по умолчанию true), `only_active` (false)
и `scope` (`own` по умолчанию). Админ в списке видит только свои ноги; `scope=all` ему
запрещён (403), зато карточка любой ноги по `GET /api/nogas/{id}` открыта — иначе не с кем
связаться, когда чужая нога пропала. Правка, удаление и файлы чужой ноги — 403.
`POST/PATCH /api/nogas` принимают город как `city_id` **или** `city_name` (создастся при
отсутствии); город необязателен, а `city_id: null` в PATCH открепляет ногу. `city_name`
приоритетнее `city_id`. Личные данные правятся тем же PATCH (`address`, `phones`,
`telegrams`) — значения в аудит не пишем, только факт правки и количество контактов.

Загрузка файла — `multipart/form-data` с полями `kind` и `file`. Отдача файла — обычный
`FileResponse` с `inline`, но под JWT: фронт тянет его `fetch`'ем в blob, потому что в
`<img src>` заголовок Authorization не подставить.

`GET /api/cities` отдаёт список без ног и принимает `scope`:

- `own` (по умолчанию) — свой участок. Для админа это города, которые он завёл, **плюс**
  чужие, где стоят его ноги (их он видит, но не правит). Для owner и right_hand — все города.
- `working` — общая витрина: города в статусе «в работе» от всех, одинаково для любой роли.
  Её открывает плашка «Города» на дашборде, из таббара открывается `own`.

`GET /api/cities/{id}` — детали с `nogas` (включая `created_by_name` и `can_manage`) и
`recent_orders`; состав ног в городе **общий**, ноги разных админов складываются, и
`nogas_count` считает всех. `POST/PATCH /api/cities` принимают `razgruz_ids` и `noga_ids` —
полный новый состав, а не дельту: ноги из списка получают `city_id` города, снятые
становятся неприкреплёнными. У актора без `nogas:all` пересборка состава касается только
его ног (`attach_to_city(owner_id=...)`), чужие остаются в городе; попытка передать чужой
`noga_id` — 403, а тёзка уже стоящей в городе чужой ноги — 409.

`DELETE /api/cities/{id}` с ногами внутри отдаёт 409 с `code: "CITY_HAS_NOGAS"` и списком
имён в `detail.nogas` — из него фронт собирает вопрос пользователю. Повторный запрос с
`?detach_nogas=true` снимает ноги с города (они остаются в системе, город уходит в историю)
и только потом удаляет город. Сами ноги не удаляются никогда.

`DELETE /api/razgruzy/{id}` устроен так же: пока разгруз висит хоть на одном городе, ответ
— 409 с `code: "RAZGRUZ_HAS_CITIES"` и именами в `detail.cities`, а `?detach_cities=true`
сначала снимает привязки, потом удаляет разгруз. Города остаются, но могут остаться без
разгрузов — фронт помечает такие красным. Разгрузы читают все с `razgruz:read`, а правит
и удаляет только автор (или роль с `razgruz:all`); при этом привязать к своему городу
можно любой разгруз из справочника, включая чужой.

Сброс порога запуска делается явными `null` в обоих полях сразу: PATCH различает
«не передано» и «передано null» через `model_fields_set`.

`GET /api/trubki` принимает `status`, `city_id` и `limit` (1–200), сортировка — новые
сверху (`created_at desc, id desc`). Список **общий**: чтение открыто всем с
`operations:own`, включая роль `noga`, деления по участкам у трубок нет. Заводить, править
и удалять может любой с `operations:all`, то есть все роли кроме `noga`; на своё/чужое
разделения тоже нет — заказ ведёт вся команда. `can_manage` в ответе поэтому равен просто
наличию права.

Ответ трубки собирает поля из связей: `city_name`, `noga_name`, `razgruz_name`, автор
трубки `created_by_name` и `noga_owner_name` — «чья нога», то есть автор **ноги**, а не
заказа (`trubki_service.LOAD_OPTIONS` тянет `Trubka.noga → Noga.created_by`). Неизвестные
`city_id` / `noga_id` / `razgruz_id` — 404 с обычным `NOT_FOUND`. В `PATCH` разгруз
снимается явным `razgruz_id: null` (та же проверка `model_fields_set`), а все SELECT'ы
идут до мутаций. ФИО и адрес заказчика в аудит **не пишем** — в `payload` уходит только
пометка «изменено» / «изменён», остальные поля с парами `from`/`to`.

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
  `NogaRazgruzy`, `NogaTrubki`, `NogaChat`, `NogaBankomaty`, `NogaCreateMenu`, `NogaStats`,
  `NogaProfile`.
  Исключение — `auth.js`: он ничего не экспортирует, только запускает `bootstrap()`.
- Стиль ES5-совместимый (`var`, `Array.prototype.forEach.call`), кроме `async/await` в запросах.
- Порядок подключения в `index.html` важен: `config → telegram → api → roles → dict →
  views → screens/* → auth.js` (`chat.js` до `profile.js`).
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
- Файлы: `NogaApi.uploadNogaFile` (FormData, Content-Type ставит браузер сам) и
  `NogaApi.nogaFileBlob` (blob под токеном). Каждый `URL.createObjectURL` надо отзывать —
  экран ног складывает ссылки в массив и чистит их при перерисовке списка (`releaseBlobs`).
- Токен хранится только в памяти (`api.js`), в localStorage не кладётся — перезагрузка
  означает повторную авторизацию через initData. 401 → `setUnauthorizedHandler` → экран gate.
- `apiBase`: дефолт из `config.js` (`http://127.0.0.1:8000`), в проде переопределён инлайн-скриптом
  в `index.html` (`https://noga-api.duckdns.org`), и всё это перебивает `?api=https://...`.

CSS: три файла — `tokens.css` (переменные), `app.css` (дашборд, таббар, FAB),
`screens.css` (splash, gate, формы, карточки, dev-панель). Именование БЭМ-подобное
(`user-card__badge--blocked`), состояния — `is-active` / `is-hidden` / `is-visible`.
Токены: фон `#0B0B0B`, золото `#D4AF37`, статусы amber/blue/green/red, `--radius*`, `--ease`.
Мобильный фрейм 390–430px, нижний таббар: 5 пунктов + FAB «+».

Таблицы (пока одна — трубки) устроены так: обёртка `.table-scroll` с
`overflow-x:auto`, сама `.trubki-table` — `width:max-content; min-width:100%`, ячейки
`white-space:nowrap` **без** `text-overflow`. Колонки берут ширину по содержимому: короткие
названия городов и имён влезают целиком, длинные уезжают под горизонтальный свайп. Фиксированной
раскладки с процентами колонок избегать — на 390px она резала значения многоточием.

Размеры текста берутся из шкалы в `tokens.css`: `--fs-hint` 12.5px (бейджи, чипы, подписи
плиток), `--fs-meta` 13.5px (вторые строки карточек, метаданные), `--fs-body` 15px (кнопки,
подписи чек-листов, пустые состояния), `--fs-strong` 16.5px (имена в карточках, поля ввода,
заголовки блоков), `--fs-title` 21px (заголовок экрана), `--fs-hero` 27px (приветствие).
**Новые размеры брать оттуда, а не проставлять пиксели вручную; 12.5px — нижняя граница,
мельче на телефоне не читается.** Крупные цифры (оборот, плитки статистики, счётчик
городов) заданы числом на месте, потому что они штучные. Экран рассчитан на быстрое
чтение: 44–46px у кнопок-иконок, плитки `.stats` в две колонки, интервалы между блоками
от 22px.

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
  `server_default` (`created_at`) нужен `refresh()`. В async-сессии обращение к неподгруженному
  полю без `await` падает не «пустым значением», а `MissingGreenlet`, поэтому после вставки
  либо `refresh()`, либо перечитывание объекта запросом.
- Ноги удаляем с загруженной коллекцией `files` (тот же `lazy="raise"`), а сам каталог с
  файлами убираем **после** `commit()`: упавшая транзакция не должна оставить БД со ссылками
  на удалённые файлы.
- HEIC/HEIF с iPhone приходят как `application/octet-stream`, поэтому тип определяем по
  расширению, а не по заголовку. Chrome такие картинки не рисует — в предпросмотре
  вешаем `onerror` и подменяем на подсказку «скачайте файл».

## Запуск и тесты

```bash
cd backend && .venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python tests/test_delete_user.py
python tests/test_nogas.py
python tests/test_cities.py
python tests/test_noga_personal.py
python tests/test_admin_scope.py
python tests/test_trubki.py
python tests/test_profile_rename.py
python tests/test_chat_foundation.py
python tests/test_chat.py
python tests/test_chat_sse.py
python tests/test_chat_notifications.py
python tests/check_chat_log_hygiene.py
python tests/test_places.py
```

Тесты — самостоятельные скрипты на `TestClient` (не pytest), каждый со своей БД в `data/`;
переменные окружения выставляются в начале файла до импорта `app`, с `get_settings.cache_clear()`.
Новый функционал покрывать в том же стиле.

Фронтенд можно прогонять в `jsdom` (Node): `node _jsdom_trubki.js`, `node _jsdom_chat.js`
(нужен пакет `jsdom`). Для chat SSE в jsdom полифилить `TextEncoder`/`TextDecoder` и
ReadableStream reader. Выбор файла — `Object.defineProperty(input, "files", { value: [file] })`.

Прод: VPS + Docker (`backend/docker-compose.yml`, `Dockerfile`, том `./data`) или systemd
(`backend/deploy/noga-api.service`, репозиторий в `/opt/noga`, сервис `noga-api` от юзера
`noga`); фронт — GitHub Pages, едет сам по пушу в `main`. `CORS_ORIGINS` должен содержать
origin фронта. Для чата — nginx example `backend/deploy/nginx-noga-api.conf.example`
(`proxy_buffering off` на stream, `client_max_body_size 110m`), один uvicorn process,
rollout с `CHAT_ENABLED=false` → migrate → nginx → enable — см. [DEPLOY.md](DEPLOY.md).

Выкатка бэкенда — `sudo bash /opt/noga/backend/deploy/deploy.sh` (pull → зависимости →
бэкап базы и `uploads/chat` → `alembic upgrade head` → рестарт → `/api/health`). Скрипты
и unit-файлы держим с LF (`.gitattributes`).

## Экраны Mini App

| Экран | id | Файл | Кому виден |
|-------|----|------|-----------|
| Дашборд | `viewHome` | `screens/dashboard.js` | всем |
| Пользователи | `viewUsers` | `screens/users.js` | `users:read` |
| Ноги | `viewNogas` | `screens/nogas.js` | `nogas:read` |
| Города | `viewCities` | `screens/cities.js` | `cities:read` |
| Разгрузы | `viewRazgruzy` | `screens/razgruzy.js` | `razgruz:read` |
| Трубки | `viewTrubki` | `screens/trubki.js` | `operations:own` (всем) |
| Трубка | `viewTrubka` | `screens/trubki.js` | `operations:own` (всем) |
| Профиль | `viewProfile` | `screens/profile.js` | всем |
| Статистика | `viewStats` | `screens/stats.js` | всем кроме `noga` |
| Чат (комнаты) | `viewChatRooms` | `screens/chat.js` | `features.chat` + `chat:read` |
| Чат (комната) | `viewChatRoom` | `screens/chat.js` | `features.chat` + `chat:read` |
| Банкоматы | `viewBankomaty` | `screens/bankomaty.js` | `features.places` + `places:read` |

Вход в чат — колокольчик на дашборде и пункт «Чат» в меню профиля. Таббар не меняется.
Глобальный SSE стартует после сессии (`NogaChat.syncAccess`); `release()` на 401.
Deep link: `?chat_room=&chat_message=` через `NogaTelegram.getChatDeepLink`.
Разметка — `em-*` из design-system; layout в `screens.css` только на `--em-*`.

Вход на экраны справочников — вкладка «Профиль», кнопка `razgruzyEntry` и плашка трубок
`trubkiEntry` на дашборде, а также плашка городов `citiesCard` (тап по ней открывает
витрину «В работе»). Сводки «в работе / стоп временно / стоп полностью» на плашке
обновляются из `summary.cities` (счётчики общие по системе, включая ноги всех
админов); после изменений на экране городов `refreshDashboard()` перезапрашивает сводку
без анимации счётчиков.

Таббар у всех ролей один (`NogaRoles.applyTabbar`, вызывается из `applySession`):
«Панель / Ноги / + / Города / Профиль». Вкладок «Операции» и «Поиск» в разметке нет.
«Ноги» и «Города» скрываются без `nogas:read` / `cities:read`, но ячейка сетки
остаётся пустой, чтобы «+» не съезжал с центра. Плашка городов на дашборде открывает
витрину (`mode: "working"`), вкладка таббара — свой участок (`mode: "own"`);
`NogaRoles.activateTab` подсвечивает нужную вкладку, а если её нет — «Профиль».

FAB «+» в центре таббара открывает вылетающее меню создания (`screens/create-menu.js`,
`NogaCreateMenu.bind()` из `auth.js`). Разметка — `#fabMenu` с затемнением `#fabBackdrop`
и списком `#fabMenuList` над таббаром по центру экрана; пункты появляются снизу вверх с задержкой
`transition-delay` по индексу, закрытие — тап по затемнению, по пункту или Esc.
Состав собирается заново на каждом открытии из прав: «Трубка» по `operations:all`,
«Город» по `cities:manage`, «Нога» по `nogas:manage`, «Разгруз» по `razgruz:manage`;
если не осталось ни одного пункта, FAB не реагирует. Каждый пункт зовёт `openCreate()`
своего экрана (`NogaTrubki` / `NogaCities` / `NogaNogas` / `NogaRazgruzy`) — метод
переключает экран и сразу открывает форму. **Новая сущность с созданием = ещё один
`openCreate()` на её экране и строчка в `items()`.**

Вкладка «Профиль» открывает `NogaProfile.show()`: карточка текущего пользователя и меню
разделов `#profileMenu`, каждый пункт — переход на существующий экран. В шапке карточки
аватар и бирка роли стоят в одном ряду (`.profile-card__identity`), ниже — ник и иконка
карандаша `#profileRenameBtn` (только с `profile:rename`). Telegram ID, username, статус
и даты спрятаны под кнопкой-дропдауном `#profileDetailsToggle` (шеврон поворачивается
через `is-open`, `#profileRows` по умолчанию `hidden`). Каждый заход на экран сворачивает
детали и закрывает форму ника.

Иконка правки ника разворачивает `#profileRenameForm` прямо в карточке: поле, подсказка
про допустимые символы и «Отмена / Сохранить». Сохранение шлёт `NogaApi.updateMe`, ответ
кладётся в `NogaRoles.setUser` и `NogaDashboard.applyUser`, поэтому ник в шапке панели
и инициалы в аватаре меняются сразу, без перезахода. Состав меню:

- **Пользователи** — по `users:manage`, то есть у owner и right_hand. У админа есть
  `users:read`, но править он ничего не может, и отдельной кнопки на дашборде больше нет —
  список пользователей ему недоступен.
- **Мои города** / **Мои ноги** / **Мои разгрузы** — по `cities:read` / `nogas:read` /
  `razgruz:read`. У ролей с `*:all` подпись без «Мои», потому что списки и так общие.
- **Трубки** — `NogaTrubki.show()`, общий список заказов; в меню есть у всех кроме `noga`.
- **Банкоматы** — `NogaBankomaty.show()`, поиск по городу/улице/дому; пункт есть у всех
  ролей при `features.places`.
- **Статистика** — `NogaStats.show()`, общесистемные цифры из `GET /api/dashboard/summary`:
  оборот (только с `dashboard:global`), трубки по стадиям из блока `trubki` и справочники
  из блока `cities`. Плитки — те же `.stat`, но с `.stat--static`, чтобы не притворялись
  кликабельными.

У роли `noga` в меню профиля остаются чат (если включён) и банкоматы (если включены);
остальные разделы скрыты.

Разделы профиля открываются как обычные экраны, вкладка при этом остаётся на «Профиле».
Слева в шапке (`.users-toolbar`) каждого из пяти разделов лежит стрелка `.btn-back` с
`data-back="viewXxx"` — по клику зовёт `NogaProfile.show()`. В разметке она есть всегда,
но по умолчанию `hidden`: показывает её `showBack(item.view)` при переходе из меню
профиля, а `NogaProfile.hideBack()` из `bindNav` гасит все стрелки при любом другом
заходе (таббар, кнопки дашборда) — оттуда возвращаться в профиль незачем. Новый раздел
в меню профиля = пункт с полем `view` плюс такая же кнопка в его шапке.

Экран городов начинается с переключателя `#citiesModes` («Мои города» / «В работе»;
у ролей с `cities:all` первая вкладка называется «Все города»). Аварии города собирает
`cityProblems(city)` — он смотрит только на города **в работе**: нет ни одной ноги
(«!! ВНИМАНИЕ !! …») и нет ни одного разгруза («!! ГОРОД БЕЗ РАЗГРУЗА !!»). Каждая
превращается в баннер `.alert-banner` на карточке и в деталях, а сама карточка получает
класс `city-card--alert`. Сам статус не меняется — сервер такие города не
запрещает. Про разгрузы молчим у ролей без `razgruz:read`: им список `razgruzy` приходит
пустым, и предупреждение было бы ложным. Перед тем как поставить «В работе» городу без ног
(переключателем или из формы), фронт спрашивает подтверждение.

На карточке города: порог запуска, число ног, чипы разгрузов с комиссиями, переключатель
трёх статусов (сегментированный) и три кнопки-иконки (`.btn-icon`, инлайн-SVG в `ICONS`
внутри `cities.js`): шеврон «Подробнее» (поворачивается на 180° в состоянии `is-open`),
карандаш «Изменить», корзина «Удалить» (`btn-icon--danger`). Иконок статуса play/pause/stop
на карточке нет — статус виден только в переключателе. Подписи кнопок только в `title` и
`aria-label`. Правка и удаление показываются по `city.can_manage`: у чужого города остаётся
один «Подробнее», а под названием подписано «Ведёт …».
Кнопок «+ Добавить» на экранах городов и ног нет — создание только через меню FAB.
Удаление города с ногами сначала спрашивает подтверждение с именами ног (список берётся
из `GET /api/cities/{id}`, больше пяти имён сворачиваются в «и ещё N»), и лишь потом
уходит `DELETE ?detach_nogas=true`; ответ 409 `CITY_HAS_NOGAS` — запасная ветка на случай,
когда ногу прикрепили, пока пользователь думал. «Подробнее» подгружает
`GET /api/cities/{id}`: ноги с автором и датой, разгрузы с комиссией, автором и счётчиком
успешных заказов, блок последних заказов (пока заглушка). Каждая нога в деталях
раскрывается в карточку (`NogaNogas.renderCard` рисует её в `.detail-list__panel`) —
только для чтения, зато с личными данными: это путь к контактам чужой ноги. В форме города
два чек-листа: разгрузы и ноги; в чек-листе ног только свои, а чужие посчитаны строкой
«Ещё N ног(и) в городе завели другие». У ног в подписи видно, где нога сейчас
(«без города» / «сейчас в Самаре»). В **новом** городе свои активные разгрузы отмечаются
сразу (`ownRazgruzIds` по флагу `created_by_me`) с подсказкой, что лишние можно снять;
при редактировании берётся фактический состав города.

На экране разгрузов кнопки правки показываются по `razgruz.can_manage`, у чужого разгруза
остаётся только карточка. Удаление привязанного разгруза идёт в два шага без лишних
диалогов: если `cities_count` больше нуля, первый `DELETE` уходит сразу (сервер его всё
равно не выполнит), из 409 берутся имена городов, и уже с ними задаётся вопрос; согласие
шлёт `DELETE ?detach_cities=true`. У свободного разгруза остаётся обычное «Удалить …?».
После удаления перечитывается список и сводка дашборда.

`NogaRazgruzy.show({ mine: true })` (вход из профиля) оставляет в списке только свои
разгрузы — фильтр по `created_by_me` на фронте, потому что справочник общий и сервер
его не режет. У ролей с `razgruz:all` фильтр не применяется: им «свои» и есть все.
Заголовок `#razgruzyTitle` и текст пустого списка переключаются вместе с фильтром,
а вход с дашборда (`razgruzyEntry`) по-прежнему показывает справочник целиком.

Экран ног показывает только свои ноги (сервер режет список по `scope=own`). Карточка: имя,
город (или «Без города»), бейдж типа и те же три кнопки-иконки, что у города, — шеврон
«Подробнее», карандаш «Изменить», корзина «Удалить» (`ICONS` и `makeIconBtn` продублированы
в `nogas.js`). Правка и удаление скрыты, если `noga.can_manage` равен false. Переключатели
«Сделать тестовой» и «Выключить» живут не на карточке, а во вкладке «Основное»: на списке
должно читаться только имя, город и статус. Одна форма и на создание,
и на редактирование (`openForm(noga)`), город выбирается селектом, где есть «Без города»
и «+ Новый город». «Подробнее» открывает `GET /api/nogas/{id}` с двумя вкладками:

- **Основное** — город, тип, статус, автор, дата, ниже — кнопки смены типа и статуса
  (их нет в режиме только для чтения: `renderMainTab(noga, host, forceReadonly)` вызывается
  с `true` из `renderCard`). Ниже города — серые строки истории
  (`detail-list__item--history`): город при добавлении и последний. Совпадающие значения
  сворачиваются в одну строку, а равные текущему городу не показываются вовсе
  (`cityHistory` в `nogas.js`). У неприкреплённой ноги та же история дублируется
  подписью на карточке списка.
- **Личные данные** (только с `nogas:personal`) — адрес, клонируемые поля телефонов и
  Telegram (`buildRepeatable`), три блока файлов из `NogaDict.NOGA_FILE_KINDS` с загрузкой,
  предпросмотром, скачиванием и удалением.

Раскрытым держится один блок деталей (`openContainer`), правки личных данных и файлов
перерисовывают только его (`reloadDetail`), а не весь список.

Трубки живут в трёх местах, и все три рисует один `screens/trubki.js`:

- **Плашка на дашборде** (`#trubkiCard`, вместо прежней «Статистики на сегодня») — восемь
  последних заказов таблицей «Статус / Город / Сумма / Нога / Чья нога», счётчик всего
  в углу и кнопка «Все трубки». Наполняет `renderDashboard()` из `applySummary`.
- **Экран списка** (`viewTrubki`) — та же таблица целиком плюс полоса фильтров по статусу
  (`.tabs--scroll`) и двухшаговая форма создания.
- **Страница трубки** (`viewTrubka`) — номер `EM-000125`, статус, город и нога; блок
  пересчёта с моментальными вычислениями выплаты ноге 10% и остатка; фото денег; затем
  сумма захода USDT и фото чека; кнопки этапов «Пересчёт» → «Отправить отчёт».
  Необязательные ФИО, адрес и способ передачи скрыты под дропдауном «Данные клиента».
  Ниже — краткая история с раскрытием актора и полной даты каждого действия.

Строка таблицы кликабельна целиком (`openDetail(id)`). Все новые детали и форма используют
компоненты `em-*` и токены из `design-system/`; ручной выбор берётся из
`NogaDict.TRUBKA_MANUAL_STATUSES`, автоматический статус есть только в общем справочнике.

Создание состоит из двух экранов внутри формы: статус (по умолчанию «Зацеп») + город,
затем сумма + нога выбранного города. После POST сразу открывается страница трубки.
Пересчёт можно подтвердить только вместе с фото денег; отчёт — только после суммы USDT
и фото чека. Фронт считает 10% немедленно для обратной связи, сервер повторяет вычисление.

## Состояние на сейчас

Готово: авторизация, роли и права, пользователи (API + бот + экран), ноги (включая личные
данные, паспорта и видео), города, разгрузы (API + экраны), трубки (API + дашборд, список,
детали с картой, форма), **внутренний чат** (REST, durable SSE, Telegram mentions outbox,
Mini App: комнаты, direct, лента, composer, deep link), **справочник банкоматов** (каркас:
`POST /api/places/nearby`, SQLite-кэш, экран в профиле, 2ГИС / моки), меню создания на FAB,
аудит, сводка по городам на дашборде, профиль с меню разделов и экран статистики.

Не сделано: кошельки, оборот. «Общий оборот сегодня» на дашборде и `usd_equivalent`
по-прежнему нули. `completed_orders` у разгруза всегда 0, `recent_orders` у города —
пустой список. Трубки не делятся по участкам. Команд бота для городов, ног, разгрузов,
трубок и чата нет — только Mini App. Chat broker пока in-memory (один process).

Известные мелкие дыры: `index.html` ссылается на `assets/img/logo.png`, которого в репозитории
нет (лежит `bot_logo.png`); смена роли в экране пользователей через `window.prompt`
внутри Telegram WebView ненадёжна.

Новые справочники делать по образцу городов и разгрузов: таблица + миграция в
`alembic/versions/`, права `сущность:read` / `сущность:manage`, сервис с загрузкой и
сериализацией в `services/`, роутер в `api/`, экран в `assets/js/screens/`, регистрация id
экрана в `views.js`, справочные значения в `dict.js`. Имена таблиц и полей — транслитом от
доменного термина (как `nogas`, `razgruzy`), английские синонимы не изобретать.
Чат — исключение с отдельным контрактом [CHAT_SSE.md](CHAT_SSE.md).