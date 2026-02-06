#!/bin/sh
# Backup PostgreSQL. Run on server (e.g. via cron).
# Requires: docker or docker-compose in PATH. Run from project root.
# Env: POSTGRES_USER (default parser_user), POSTGRES_DB (default parser_db), BACKUP_DIR (default ./backups), KEEP_DAYS (default 7).

set -e
USER="${POSTGRES_USER:-parser_user}"
DB="${POSTGRES_DB:-parser_db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/parser_db_${DATE}.sql"

mkdir -p "$BACKUP_DIR"
if command -v docker-compose >/dev/null 2>&1; then
  docker-compose exec -T postgres pg_dump -U "$USER" "$DB" > "$FILE"
elif command -v docker >/dev/null 2>&1; then
  docker exec parser_postgres pg_dump -U "$USER" "$DB" > "$FILE"
else
  echo "Need docker-compose or docker" >&2
  exit 1
fi
echo "Backup: $FILE"

# Remove backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "parser_db_*.sql" -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true
