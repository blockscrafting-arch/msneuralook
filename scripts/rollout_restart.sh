#!/bin/sh
# Шаг 4 плана внедрения: перезапуск editor-bot и userbot после миграции и обновления .env.
# Запуск из корня проекта.

set -e
cd "$(dirname "$0")/.."
echo "Перезапуск editor-bot и userbot..."
docker compose up -d --build editor-bot userbot 2>/dev/null || docker-compose up -d --build editor-bot userbot
echo "Готово. Проверьте: docker compose ps"
