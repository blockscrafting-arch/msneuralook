#!/bin/sh
# Проверка после внедрения: наличие таблиц админки в БД.
# Запуск из корня проекта.

set -e
cd "$(dirname "$0")/.."
POSTGRES_USER="${POSTGRES_USER:-parser_user}"
POSTGRES_DB="${POSTGRES_DB:-parser_db}"
CHECK='SELECT count(*) FROM information_schema.tables WHERE table_schema = '\''public'\'' AND table_name IN ('\''source_channels'\'', '\''admins'\'', '\''editors'\'');'
OUT=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c "$CHECK" 2>/dev/null || \
  docker-compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c "$CHECK")
COUNT=$(echo "$OUT" | tr -d '\r')
if [ "$COUNT" = "3" ]; then
  echo "OK: таблицы source_channels, admins, editors найдены."
else
  echo "Ошибка: ожидалось 3 таблицы, найдено: $COUNT" >&2
  exit 1
fi
