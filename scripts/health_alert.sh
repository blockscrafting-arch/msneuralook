#!/bin/sh
# Проверка контейнеров parser. При падении сервиса отправляет сообщение в Telegram.
# Использование: в .env или окружении задать TELEGRAM_ALERT_BOT_TOKEN и TELEGRAM_ALERT_CHAT_ID (например 551570137).
# Cron: */5 * * * * cd /home/goutach/parser && . ./.env 2>/dev/null; export TELEGRAM_ALERT_BOT_TOKEN TELEGRAM_ALERT_CHAT_ID; ./scripts/health_alert.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

send_telegram() {
    if [ -z "$TELEGRAM_ALERT_BOT_TOKEN" ] || [ -z "$TELEGRAM_ALERT_CHAT_ID" ]; then
        return 0
    fi
    curl -sSf --max-time 10 "https://api.telegram.org/bot${TELEGRAM_ALERT_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_ALERT_CHAT_ID}" \
        --data-urlencode "text=$1" >/dev/null || true
}

# Проверка: все ли нужные сервисы в состоянии Up
ps_out=$(docker compose ps 2>&1) || true
if ! echo "$ps_out" | grep -q "parser_"; then
    send_telegram "⚠️ Parser: docker compose не запущен или каталог не тот"
    exit 1
fi

bad=""
for svc in postgres editor_bot userbot n8n; do
    if ! echo "$ps_out" | grep "parser_${svc}" | grep -q "Up"; then
        bad="${bad} ${svc}"
    fi
done

if [ -n "$bad" ]; then
    send_telegram "⚠️ Parser: не в работе:$bad"
    exit 1
fi

exit 0
