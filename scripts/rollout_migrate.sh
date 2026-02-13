#!/bin/sh
# Шаг 2 плана внедрения: применить миграцию админки (source_channels, admins, editors).
# Запуск из корня проекта. Требуется: docker compose и запущенный контейнер postgres.

set -e
cd "$(dirname "$0")/.."
POSTGRES_USER="${POSTGRES_USER:-parser_user}"
POSTGRES_DB="${POSTGRES_DB:-parser_db}"
MIGRATION="init_db/migrate_001_admin.sql"
if [ ! -f "$MIGRATION" ]; then
  echo "Файл $MIGRATION не найден." >&2
  exit 1
fi
if command -v docker >/dev/null 2>&1; then
  ( docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$MIGRATION" ) 2>/dev/null || \
  ( docker-compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$MIGRATION" )
else
  echo "Требуется docker compose." >&2
  exit 1
fi
echo "Миграция применена: $MIGRATION"
