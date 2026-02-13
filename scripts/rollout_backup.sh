#!/bin/sh
# Шаг 1 плана внедрения: бэкап БД перед миграцией.
# Запуск из корня проекта. Требуется: docker compose и запущенный контейнер postgres.

set -e
cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
export POSTGRES_USER="${POSTGRES_USER:-parser_user}"
export POSTGRES_DB="${POSTGRES_DB:-parser_db}"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/parser_db_pre_admin_${DATE}.sql"
if command -v docker >/dev/null 2>&1; then
  docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$FILE" 2>/dev/null || \
  docker-compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$FILE"
else
  echo "Требуется docker compose. Установите Docker." >&2
  exit 1
fi
echo "Бэкап сохранён: $FILE"
