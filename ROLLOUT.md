# Внедрение админки в прод

Пошаговый чеклист по плану внедрения. Выполнять на сервере (или локально при наличии .env).

## 1. Подготовка и бэкап БД

- Убедиться, что контейнеры подняты: `docker compose ps` (postgres, editor-bot, userbot, n8n).
- Сделать бэкап БД:
  - **Linux/macOS:** из корня проекта выполнить:
    ```bash
    chmod +x scripts/rollout_backup.sh && ./scripts/rollout_backup.sh
    ```
    Либо существующий скрипт:
    ```bash
    BACKUP_DIR=./backups ./scripts/backup_db.sh
    ```
  - **Вручную:** `docker compose exec -T postgres pg_dump -U parser_user parser_db > backups/parser_db_$(date +%Y%m%d_%H%M%S).sql`
- Проверить, что файл бэкапа создан в `backups/`.

## 2. Миграция БД

- Применить миграцию админки:
  - **Linux/macOS:** `chmod +x scripts/rollout_migrate.sh && ./scripts/rollout_migrate.sh`
  - **Вручную:** из корня проекта:
    ```bash
    docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_001_admin.sql
    ```
- Проверить таблицы: `docker compose exec -T postgres psql -U parser_user -d parser_db -c "\dt source_channels admins editors"` — должны быть перечислены три таблицы.

## 3. Настройка окружения (прод)

- В `.env` на сервере проверить/добавить:
  - `DATABASE_URL=postgresql://parser_user:PASSWORD@postgres:5432/parser_db` — используется editor-bot и userbot (в docker-compose передаётся из POSTGRES_*).
  - `EDITOR_CHAT_ID` — заполнен для bootstrap главного админа/редактора.
  - `TARGET_CHANNEL_ID` — по желанию для bootstrap целевого канала (можно задать позже в админке).
  - `SOURCE_CHANNEL` — опционально для userbot (fallback, если в БД ещё нет каналов).
- Для userbot в docker-compose уже передаётся `DATABASE_URL`; дополнительно в .env ничего не нужно, если заданы POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.

## 4. Перезапуск сервисов

- Из корня проекта:
  ```bash
  docker compose up -d --build editor-bot userbot
  ```
- Убедиться, что контейнеры запущены: `docker compose ps`. В логах editor-bot не должно быть ошибок подключения к БД и вебхука.

## 5. Первичная валидация

- Проверка таблиц (опционально): `chmod +x scripts/rollout_validate_db.sh && ./scripts/rollout_validate_db.sh` — должно вывести «OK: таблицы source_channels, admins, editors найдены».
- В Telegram от пользователя с `EDITOR_CHAT_ID`: отправить боту `/admin`.
- В админке: добавить канал-источник (ID или @username), задать целевой канал, при необходимости добавить редактора.
- Убедиться, что userbot подхватывает новый канал (в течение ~30 с после добавления).

## 6. Контроль после запуска

- В БД: `SELECT * FROM audit_log WHERE action LIKE 'admin_%' ORDER BY created_at DESC LIMIT 10;`
- Проверить, что новые посты из канала-источника приходят в бота с кнопками утверждения.
