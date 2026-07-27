# Деплой NOGA Systems

Фронтенд и backend едут по разным дорогам:

- **Mini App (фронтенд)** — GitHub Pages. Обновляется сам после `git push` в `main`,
  на VPS для него ничего делать не нужно.
- **API + Telegram-бот** — VPS. Обновляются вручную: `git pull` на сервере, миграции, рестарт.

Ниже — про VPS. Предполагается раскладка из `backend/deploy/noga-api.service`:

```
/opt/noga/                  # git-репозиторий
  backend/
    .env                    # секреты, в git не лежит и pull его не трогает
    .venv/                  # виртуальное окружение, в git не лежит
    data/noga.db            # база, в git не лежит
    data/uploads/           # паспорта и видео ног, в git не лежат
    data/backups/           # бэкапы базы, кладёт скрипт деплоя
systemd-сервис: noga-api    # запускает uvicorn от пользователя noga
```

Скрипт деплоя бэкапит только `noga.db`. Файлы ног в `data/uploads/` он не трогает и не
копирует — если они важны, заведите отдельный бэкап каталога (`rsync`, `tar`).

## Быстрый путь

```bash
ssh user@ваш-сервер
sudo bash /opt/noga/backend/deploy/deploy.sh
```

Скрипт делает всё сам: проверяет, что вы на `main` и нет незакоммиченных правок, забирает
свежие коммиты, переустанавливает зависимости (только если менялся `requirements.txt`),
останавливает сервис, снимает бэкап базы, накатывает миграции, запускает сервис обратно
и дёргает `/api/health`. Если что-то падает на середине, сервис поднимается обратно
автоматически, а в консоль печатаются последние 50 строк лога.

Пути можно переопределить переменными: `REPO_DIR`, `SERVICE`, `BRANCH`, `APP_USER`,
`HEALTH_URL`, `KEEP_BACKUPS`. Например, чтобы выкатить не `main`:

```bash
sudo BRANCH=feature/nogas bash /opt/noga/backend/deploy/deploy.sh
```

Самого скрипта на сервере ещё нет, пока вы не забрали этот коммит, — первый раз
сделайте `cd /opt/noga && sudo git pull --ff-only` вручную или пройдите шаги ниже.

## Тот же деплой руками

Если хочется контролировать каждый шаг:

```bash
ssh user@ваш-сервер
cd /opt/noga

# 1. Что прилетит
git fetch origin main
git log --oneline HEAD..origin/main

# 2. Забрать
git status            # должно быть чисто
git merge --ff-only origin/main

# 3. Зависимости — только если менялся backend/requirements.txt
sudo backend/.venv/bin/pip install -r backend/requirements.txt

# 4. Остановить, забэкапить, мигрировать
sudo systemctl stop noga-api
sudo mkdir -p backend/data/backups
sudo cp backend/data/noga.db backend/data/backups/noga-$(date +%F-%H%M%S).db
cd backend && sudo .venv/bin/python -m alembic upgrade head && cd ..

# 5. Поднять и проверить
sudo systemctl start noga-api
systemctl status noga-api --no-pager
curl -s http://127.0.0.1:8000/api/health     # {"status":"ok"}
```

Если тянули репозиторий из-под `root`, верните владельца, иначе сервис под пользователем
`noga` не сможет писать в рабочие каталоги:

```bash
sudo chown -R noga:noga /opt/noga
```

Порядок «сначала мигрировать, потом стартовать» важен: при запуске приложение зовёт
`Base.metadata.create_all` и само создаёт недостающие таблицы. Если поднять новый код до
Alembic, он наплодит `razgruzy` и `city_razgruzy` мимо истории миграций, а `alembic upgrade head`
потом упрётся в «table razgruzy already exists». Что делать, если так уже вышло, — ниже.

## Разовый stamp перед первой миграцией

Схему в проекте создают двумя путями: Alembic и `create_all` при старте приложения.
Если база выросла из `create_all`, таблицы `alembic_version` в ней нет, и `alembic upgrade head`
пойдёт с самой первой ревизии и упрётся в уже существующие таблицы. Один раз нужно
объяснить Alembic, где он находится.

Посмотрите, что в базе:

```bash
cd /opt/noga/backend
sudo .venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/noga.db')
t = sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\"))
print('таблицы:', t)
if 'cities' in t:
    print('колонки cities:', [r[1] for r in c.execute('PRAGMA table_info(cities)')])
if 'nogas' in t:
    print('колонки nogas:', [r[1] for r in c.execute('PRAGMA table_info(nogas)')])
"
```

Дальше по ситуации (проверяйте сверху вниз, берите первое подходящее):

| Что в базе | Команда |
|------------|---------|
| есть `alembic_version` | ничего, stamp не нужен |
| нет таблицы `cities` | `sudo .venv/bin/python -m alembic stamp 001_initial` |
| в `cities` колонка `is_active` | `sudo .venv/bin/python -m alembic stamp 002_cities_nogas` |
| в `cities` колонка `status`, в `nogas` нет `address` | `sudo .venv/bin/python -m alembic stamp 003_city_status_razgruzy` |
| в `nogas` есть `address`, но нет `initial_city_name` | `sudo .venv/bin/python -m alembic stamp 004_noga_personal` |
| в `nogas` есть `initial_city_name` | `sudo .venv/bin/python -m alembic stamp 005_noga_city_history` |

Ревизию указываем точную, а не `head`: `stamp head` отметит базу как полностью
свежую и все недостающие миграции будут пропущены.

После stamp запускайте обычный деплой — `alembic upgrade head` доедет до конца сам.

## Если сервис успел стартовать до миграции

Симптом: `alembic upgrade head` падает на `table razgruzy already exists`, а в `cities`
по-прежнему колонка `is_active`. Значит таблицы создал `create_all` при старте нового кода.
Уроните эти две таблицы (они пустые: экран городов с такой схемой всё равно не работал)
и повторите миграцию — бэкап к этому моменту уже снят:

```bash
sudo systemctl stop noga-api
cd /opt/noga/backend
sudo .venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/noga.db')
print('разгрузов в базе:', c.execute('SELECT count(*) FROM razgruzy').fetchone()[0])
c.execute('DROP TABLE IF EXISTS city_razgruzy')
c.execute('DROP TABLE IF EXISTS razgruzy')
c.commit()
"
sudo .venv/bin/python -m alembic upgrade head
sudo systemctl start noga-api
```

Если счётчик разгрузов не ноль — их успели завести через API; выпишите строки перед
удалением и заведите заново после миграции.

То же бывает и с `004_noga_personal`: симптом — `table noga_files already exists`.
Здесь чинить проще, потому что колонки в `nogas` миграция успевает добавить до падения,
а `noga_files` создаётся точно такой же. Проверьте и просто отметьте ревизию:

```bash
cd /opt/noga/backend
sudo .venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/noga.db')
print('колонки nogas:', [r[1] for r in c.execute('PRAGMA table_info(nogas)')])
print('файлов ног:', c.execute('SELECT count(*) FROM noga_files').fetchone()[0])
"
# если в списке есть address, phones, telegrams — схема уже нужная:
sudo .venv/bin/python -m alembic stamp 004_noga_personal
sudo systemctl restart noga-api
```

С `005_noga_city_history` такой ловушки нет: новые колонки в существующую таблицу
`create_all` не добавляет. Но если сервис стартовал на новом коде без миграции, экран ног
отвалится с `no such column: nogas.initial_city_name` — лечится обычным `alembic upgrade head`.

## Если сломалось: откат

```bash
cd /opt/noga
git log --oneline -5                    # найти предыдущий рабочий коммит
sudo systemctl stop noga-api
git checkout <хеш-коммита>

# база откатывается отдельно, если миграция уже прошла:
cd backend
sudo .venv/bin/python -m alembic downgrade -1
# либо вернуть файл из бэкапа:
cp data/backups/noga-2026-07-27-2310.db data/noga.db

sudo systemctl start noga-api
```

Вернуться на актуальную ветку потом: `git checkout main`.

## Диагностика

```bash
systemctl status noga-api --no-pager      # запущен ли, когда стартовал, код выхода
journalctl -u noga-api -f                 # живой лог (Ctrl+C — выйти)
journalctl -u noga-api -n 100 --no-pager  # последние 100 строк
journalctl -u noga-api --since "10 min ago"

curl -s http://127.0.0.1:8000/api/health  # локально
ss -tlnp | grep 8000                      # кто слушает порт
sudo systemctl restart noga-api           # просто перезапустить
```

Частые причины, почему после деплоя не работает:

- **Бот молчит, API отвечает.** Polling падает отдельно от API и пишет в лог
  `Bot polling stopped with error`. Смотрите `journalctl`, обычно это неверный `BOT_TOKEN`
  или второй запущенный экземпляр бота (Telegram отдаёт `Conflict: terminated by other getUpdates`).
- **Mini App показывает «API недоступен».** Проверьте `CORS_ORIGINS` в `.env` — там должен
  быть `https://ilya-dudin001.github.io`, — и что `apiBase` в `index.html` смотрит на реальный
  домен по HTTPS.
- **`no such column`** в логе — не накатили миграции.
- **`Permission denied` на `data/noga.db`** — файлы принадлежат `root` после pull из-под root,
  лечится `chown -R noga:noga /opt/noga`.

## Новые переменные окружения

`git pull` не трогает `.env` (он в `.gitignore`). Если в релизе появилась новая переменная,
её нужно дописать руками, сверяясь с `backend/.env.example`:

```bash
diff <(sed 's/=.*//' /opt/noga/backend/.env.example | sort) \
     <(sed 's/=.*//' /opt/noga/backend/.env | grep -v '^#' | sort)
sudo nano /opt/noga/backend/.env
sudo systemctl restart noga-api
```

## Вариант с Docker

Если сервис поднят через `docker compose`, а не systemd:

Порядок тот же: собрать образ, погасить контейнер, мигрировать отдельным запуском и только
потом поднимать — иначе `create_all` опередит Alembic.

```bash
cd /opt/noga/backend
git -C /opt/noga pull --ff-only
docker compose build
docker compose down
mkdir -p data/backups && cp data/noga.db data/backups/noga-$(date +%F-%H%M%S).db
docker compose run --rm api python -m alembic upgrade head
docker compose up -d
docker compose logs -f --tail=50 api
```

## Первичная установка (если сервер ещё пустой)

```bash
sudo apt update && sudo apt install -y git python3-venv curl
sudo adduser --system --group --home /opt/noga noga
sudo git clone https://github.com/ilya-dudin001/NOGA-SYSTEMS-MAIN.git /opt/noga
cd /opt/noga/backend

sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

sudo cp .env.example .env
sudo nano .env                 # BOT_TOKEN, JWT_SECRET, OWNER_TELEGRAM_IDS, CORS_ORIGINS
sudo mkdir -p data/backups

# схему создаём Alembic'ом ДО первого старта, иначе её создаст create_all
# и в базе не будет alembic_version — дальше придётся делать stamp
sudo .venv/bin/python -m alembic upgrade head
sudo chown -R noga:noga /opt/noga

sudo cp deploy/noga-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now noga-api
curl -s http://127.0.0.1:8000/api/health
```

Mini App обязан работать по HTTPS, поэтому перед API нужен reverse proxy с сертификатом
(nginx + certbot), проксирующий домен на `127.0.0.1:8000`. Этот домен и подставляется в
`apiBase` в `index.html`.
