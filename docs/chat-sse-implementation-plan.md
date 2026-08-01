Поэтапная реализация чата REST + SSE

Этап 0. Зафиксировать исходное состояние





Проверить актуальный git diff и не затрагивать существующие пользовательские изменения, включая текущие правки темы и frontend-файлов.



Запустить имеющиеся backend smoke-тесты и _jsdom_trubki.js; если локальный jsdom не установлен (в репозитории нет package.json), зафиксировать это как prerequisite, а не как регрессию.



Использовать [CHAT_SSE.md](CHAT_SSE.md) как источник контрактов; чат до rollout держать выключенным через production CHAT_ENABLED=false.



Шлюз: текущая функциональность проходит baseline либо известные исходные сбои явно отделены.

Этап 1. Схема, настройки и права





В [backend/app/db/models.py](backend/app/db/models.py) добавить enum и все семь chat-моделей сразу, связи lazy="raise", FK, unique и индексы; не менять модели справочника ног.



Создать единую миграцию [backend/alembic/versions/007_chat.py](backend/alembic/versions/007_chat.py) с таблицами, индексами и seed комнат general/team; продублировать idempotent seed в [backend/app/db/bootstrap.py](backend/app/db/bootstrap.py) для create_all.



В [backend/app/config.py](backend/app/config.py) и [backend/.env.example](backend/.env.example) добавить лимиты, heartbeat, retention, retry, rate limit и feature flag; в [backend/app/db/__init__.py](backend/app/db/__init__.py) настроить SQLite busy timeout.



В [backend/app/auth/permissions.py](backend/app/auth/permissions.py) добавить chat:* только owner/right_hand/admin; в [backend/app/schemas.py](backend/app/schemas.py) и сериализации пользователя добавить features.chat.



Расширить [backend/app/services/users.py](backend/app/services/users.py) явной очисткой chat FK при удалении пользователя, не превращая targeted events в broadcast.



Шлюз: migration upgrade/downgrade на отдельной БД, bootstrap идемпотентен, permissions/features корректны для четырёх ролей, все старые backend-тесты проходят.

Этап 2. Домен и основной REST без realtime





В новых [backend/app/services/chat.py](backend/app/services/chat.py) и chat-схемах реализовать единые проверки system/direct access, нормализацию direct_key, content parts, reply, pagination, unread и серверный can_delete.



В [backend/app/api/chat.py](backend/app/api/chat.py) реализовать rooms, peers, idempotent direct, history before_id/around_id, multipart text-only send, soft-delete, read cursor и mention read/list; регистрировать роутер в [backend/app/main.py](backend/app/main.py).



При каждой мутации в той же транзакции создавать chat_events и безопасный audit без текста и имён файлов; publish пока не выполнять.



Начать [backend/tests/test_chat.py](backend/tests/test_chat.py): role/access matrix, system rooms, direct uniqueness/race, text/reply/mentions, pagination, unread, delete matrix, role/block/delete-user behavior.



Шлюз: полный REST-сценарий работает без frontend, роль noga получает 403 на каждый chat endpoint, rollback не создаёт event/audit наполовину.

Этап 3. Безопасные вложения





В chat service реализовать staging во временный каталог до короткой SQLite write-транзакции, повторную проверку доступа, перенос в UPLOADS_DIR/chat/{room}/{message}/{uuid} и cleanup при любой ошибке.



Дополнить multipart send финальными ограничениями: до 10 файлов и до 100 МБ суммарно по фактически прочитанным чанкам; добавить защищённый download endpoint с attachment, nosniff, no-store.



Soft-delete удаляет metadata транзакционно, а физические файлы после commit; ошибка удаления только логируется.



Расширить test_chat.py: file-only, mixed message, границы через подменяемый лимит, traversal, rollback cleanup, access к download и отмена вложений при delete.



Шлюз: превышение лимита не оставляет временных/конечных файлов, чужой пользователь не скачивает direct attachment, старые тесты файлов ног проходят.

Этап 4. Durable SSE и lifecycle





Создать [backend/app/services/chat_broker.py](backend/app/services/chat_broker.py): bounded queue, subscribe-before-replay, dedupe, overflow sentinel и гарантированный unsubscribe.



В chat API добавить GET /api/chat/stream через StreamingResponse: Bearer header, optional room filter, Last-Event-ID, heartbeat, DB catch-up, retention gap/stream.reset, targeted filtering и revalidation короткими SessionLocal без долгоживущей AsyncSession.



После успешного REST commit публиковать только event id; при разрыве broker доставка восстанавливается из chat_events.



В lifespan [backend/app/main.py](backend/app/main.py) создать broker и cleanup worker, корректно отменять задачи при shutdown; добавить in-memory rate limit и structured logs.



Расширить tests: live/replay order, race replay+queue, dedupe, heartbeat, overflow, disconnect cleanup, reset, block/role change и отсутствие события после rollback; низкоуровневые generator-сценарии тестировать напрямую, если TestClient буферизует бесконечный stream.



Шлюз: curl -N получает heartbeat и committed сообщения, restart/reconnect восполняет пропуск, активный stream не удерживает DB-сессию.

Этап 5. Упоминания и Telegram outbox





В [backend/app/services/chat_notifications.py](backend/app/services/chat_notifications.py) реализовать persistent claim/retry на chat_mentions, stale-lock recovery, terminal Telegram errors и отсутствие сетевого вызова внутри DB-транзакции.



Запускать один Bot, если включён polling либо chat notifications; notification worker подключить к lifespan с graceful shutdown.



Отправлять только автора/название комнаты и WebApp-кнопку, без текста и имён файлов; deep link содержит room/message, но не JWT.



Проверить отмену pending/retry при удалении сообщения и повторную валидацию статуса/роли/room access перед отправкой.



Расширить tests mock-ботом: success, network retry, retry_after, terminal failure, stale sending, deleted message и независимость сохранения сообщения от Telegram.



Шлюз: временный сбой Telegram не влияет на POST сообщения и приводит к последующей ровно однократной доставке.

Этап 6. Frontend transport и каркас экранов





В [assets/js/api.js](assets/js/api.js) добавить chat REST, XHR multipart с progress и openChatStream() на fetch + ReadableStream; parser должен выдерживать разрыв frame между chunks, comments, multiline data, AbortController и backoff.



В [index.html](index.html), [assets/js/views.js](assets/js/views.js) и новом [assets/js/screens/chat.js](assets/js/screens/chat.js) добавить viewChatRooms/viewChatRoom и сохранить текущий порядок scripts, включая существующий theme script.



В [assets/js/auth.js](assets/js/auth.js), [assets/js/screens/dashboard.js](assets/js/screens/dashboard.js) и [assets/js/screens/profile.js](assets/js/screens/profile.js) подключить feature+permission gate, bell unread, пункт профиля, старт/остановку глобального SSE; таббар не менять.



В [assets/css/screens.css](assets/css/screens.css) добавить мобильный shell чата только через существующие tokens; в [assets/css/app.css](assets/css/app.css) расширить badge колокольчика для числового unread.



Начать [_jsdom_chat.js](_jsdom_chat.js): feature gate, role exclusion, rooms response, SSE chunks, Last-Event-ID, reconnect и unauthorized cleanup.



Шлюз: можно открыть список/пустую комнату, роль без права не запускает stream, parser проходит изолированные jsdom cases.

Этап 7. Полный UX комнат и сообщений





Реализовать системные/direct карточки, peers picker и idempotent создание direct; затем history pagination с сохранением scroll, dedupe и кнопку новых сообщений.



Добавить composer: text parts, reply preview/context via around_id, structured mention picker из chat peers, выбранные файлы, суммарный лимит, progress/cancel и безопасные уведомления через NogaTelegram.



Реализовать soft-delete UI по серверному can_delete, unread/read только у видимого низа, mention badges, deep link room/message через [assets/js/telegram.js](assets/js/telegram.js) и release() для XHR/blob/listeners.



Все данные вставлять через textContent; загруженные файлы не рендерить inline.



Завершить _jsdom_chat.js: direct, history, reply, mention, upload limits/progress, delete, unread, deep link, XSS и resource cleanup.



Шлюз: два пользователя проходят полный сценарий send/reply/mention/file/delete/reconnect, третий не видит direct, мобильная вёрстка не ломает существующие экраны.

Этап 8. Интеграционная проверка и rollout





Обновить [README.md](README.md), [DEPLOY.md](DEPLOY.md) и [AGENTS.md](AGENTS.md): API/экраны, env, nginx proxy_buffering off, client_max_body_size 110m, single-worker restriction, backup и rollback.



Запустить все существующие backend smoke-тесты, новый test_chat.py, _jsdom_trubki.js, _jsdom_chat.js, lints и ручные REST/SSE проверки.



Проверить observability без утечки body/filenames/JWT, свободное место, event retention и pending Telegram queue.



Rollout: backup БД и data/uploads/chat → backend/migration с production flag off → nginx → smoke → frontend → включение flag → проверки трёх внутренних ролей и отказ роли noga → restart/replay test → наблюдение 24–72 часа за DB/disk/outbox.



При проблеме сначала выключить feature flag; downgrade migration только после отдельного backup, поскольку он удаляет историю.



Финальный шлюз: выполнены все критерии приёмки из [CHAT_SSE.md](CHAT_SSE.md), существующие функции приложения не регрессировали.

