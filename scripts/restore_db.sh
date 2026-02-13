#!/bin/sh
# Restore PostgreSQL from backup. Run on server from project root.
# Восстановление выполняется от пользователя postgres (требуется для DROP объектов, созданных в init.sql).
# Usage: BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql [RESTORE_CONFIRM=1] ./scripts/restore_db.sh
# Dry-run: RESTORE_DRY_RUN=1 BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh
# Env: POSTGRES_DB (default parser_db).

set -e
DB="${POSTGRES_DB:-parser_db}"
RESTORE_USER=postgres

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
  echo "Usage: BACKUP_FILE=/path/to/parser_db_YYYYMMDD_HHMMSS.sql $0" >&2
  echo "File must exist." >&2
  exit 1
fi

if [ ! -s "$BACKUP_FILE" ]; then
  echo "Error: backup file is empty: $BACKUP_FILE" >&2
  exit 1
fi

if [ "$RESTORE_DRY_RUN" = "1" ]; then
  echo "Dry-run: would restore from $BACKUP_FILE to database $DB as user $RESTORE_USER"
  if docker compose version >/dev/null 2>&1; then
    echo "Command: docker compose exec -T postgres psql -U $RESTORE_USER -d $DB -X < $BACKUP_FILE"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "Command: docker-compose exec -T postgres psql -U $RESTORE_USER -d $DB -X < $BACKUP_FILE"
  else
    echo "Command: docker exec -i parser_postgres psql -U $RESTORE_USER -d $DB -X < $BACKUP_FILE"
  fi
  exit 0
fi

if [ "$RESTORE_CONFIRM" != "1" ]; then
  echo "WARNING: Stop services before restore: docker compose stop editor-bot userbot n8n"
  echo "Restore will run as user $RESTORE_USER. Continue? [y/N]"
  read -r ans
  case "$ans" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 2 ;;
  esac
fi

if docker compose version >/dev/null 2>&1; then
  docker compose exec -T postgres psql -U "$RESTORE_USER" -d "$DB" -X < "$BACKUP_FILE"
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose exec -T postgres psql -U "$RESTORE_USER" -d "$DB" -X < "$BACKUP_FILE"
elif command -v docker >/dev/null 2>&1; then
  docker exec -i parser_postgres psql -U "$RESTORE_USER" -d "$DB" -X < "$BACKUP_FILE"
else
  echo "Need docker-compose or docker" >&2
  exit 1
fi
echo "Restored from $BACKUP_FILE"
