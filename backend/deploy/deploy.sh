#!/usr/bin/env bash
# Деплой backend'а NOGA на VPS: git pull → зависимости → бэкап → миграции → рестарт.
# Запуск на сервере:  sudo bash /opt/noga/backend/deploy/deploy.sh
set -euo pipefail

# Тело обёрнуто в { }, потому что git merge может переписать этот же файл на ходу:
# так bash дочитывает скрипт целиком до начала выполнения.
{

REPO_DIR="${REPO_DIR:-/opt/noga}"
SERVICE="${SERVICE:-noga-api}"
BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-noga}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
KEEP_BACKUPS="${KEEP_BACKUPS:-10}"

BACKEND_DIR="$REPO_DIR/backend"
PY="$BACKEND_DIR/.venv/bin/python"
DB_FILE="$BACKEND_DIR/data/noga.db"
BACKUP_DIR="$BACKEND_DIR/data/backups"
SERVICE_STOPPED=0

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$1" >&2; exit 1; }

# Если что-то упало после остановки сервиса — поднимаем его обратно,
# иначе бот останется лежать до ручного вмешательства.
on_exit() {
  local code=$?
  if [ "$code" != 0 ] && [ "$SERVICE_STOPPED" = 1 ]; then
    printf '\n\033[1;31m!! Деплой упал. Поднимаю %s обратно\033[0m\n' "$SERVICE" >&2
    systemctl start "$SERVICE" || true
    printf 'Проверьте лог: journalctl -u %s -n 50 --no-pager\n' "$SERVICE" >&2
    printf 'Откат описан в DEPLOY.md, раздел «Если сломалось».\n' >&2
  fi
}
trap on_exit EXIT

[ -d "$BACKEND_DIR" ] || fail "Нет каталога $BACKEND_DIR — проверьте REPO_DIR"
[ -x "$PY" ] || fail "Нет venv: $PY. Создайте его (см. DEPLOY.md)"
[ -f "$BACKEND_DIR/.env" ] || fail "Нет $BACKEND_DIR/.env — без него сервис не поднимется"

cd "$REPO_DIR"

say "Проверяю рабочую копию"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$CURRENT_BRANCH" = "$BRANCH" ] || fail "Сейчас ветка '$CURRENT_BRANCH', а деплоим '$BRANCH'.
Вернитесь на неё: git checkout $BRANCH"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --short --untracked-files=no
  fail "На сервере есть незакоммиченные правки. Уберите их (git checkout -- <файл>) и повторите"
fi

BEFORE="$(git rev-parse HEAD)"

say "Забираю $BRANCH из origin"
git fetch origin "$BRANCH"
if [ "$BEFORE" = "$(git rev-parse "origin/$BRANCH")" ]; then
  echo "Новых коммитов нет, передеплой текущего: $(git log -1 --format='%h %s')"
else
  git log --oneline "HEAD..origin/$BRANCH"
  git merge --ff-only "origin/$BRANCH"
fi
AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" != "$AFTER" ] && git diff --name-only "$BEFORE" "$AFTER" | grep -q '^backend/requirements.txt$'; then
  say "requirements.txt изменился — обновляю зависимости"
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r "$BACKEND_DIR/requirements.txt"
else
  echo "Зависимости не менялись"
fi

# Миграции гоняем на остановленном сервисе: SQLite не любит схемных правок под нагрузкой,
# да и копия файла при работающем боте может получиться несогласованной.
say "Останавливаю $SERVICE"
systemctl stop "$SERVICE"
SERVICE_STOPPED=1

if [ -f "$DB_FILE" ]; then
  say "Бэкап базы"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/noga-$(date +%Y%m%d-%H%M%S).db"
  cp "$DB_FILE" "$BACKUP_FILE"
  echo "$BACKUP_FILE"
  # оставляем только KEEP_BACKUPS последних
  ls -1t "$BACKUP_DIR"/noga-*.db 2>/dev/null | tail -n "+$((KEEP_BACKUPS + 1))" | xargs -r rm -- || true

  if ! "$PY" -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); sys.exit(0 if c.execute("SELECT 1 FROM sqlite_master WHERE type=? AND name=?", ("table","alembic_version")).fetchone() else 1)' "$DB_FILE"; then
    fail "В базе нет таблицы alembic_version (схему создал create_all).
Один раз отметьте текущую ревизию и повторите деплой — DEPLOY.md, раздел «Разовый stamp»."
  fi
else
  echo "Файла $DB_FILE нет — бэкап пропущен (первый запуск или свой DATABASE_URL в .env)"
fi

say "Миграции"
cd "$BACKEND_DIR"
"$PY" -m alembic upgrade head
cd "$REPO_DIR"

if [ "$(id -u)" = "0" ] && id "$APP_USER" >/dev/null 2>&1; then
  chown -R "$APP_USER:" "$REPO_DIR" || true
fi

say "Запускаю $SERVICE"
systemctl start "$SERVICE"
SERVICE_STOPPED=0

say "Проверяю здоровье"
for _ in $(seq 1 15); do
  if HEALTH="$("$PY" -c 'import sys,urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=3).read().decode())' "$HEALTH_URL" 2>/dev/null)"; then
    echo "$HEALTH_URL → $HEALTH"
    say "Готово: $(git log -1 --format='%h %s')"
    exit 0
  fi
  sleep 1
done

printf '\n\033[1;31m!! Сервис не ответил на %s\033[0m\n' "$HEALTH_URL" >&2
journalctl -u "$SERVICE" -n 50 --no-pager >&2
exit 1

}
