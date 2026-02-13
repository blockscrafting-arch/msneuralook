# Telegram Parser & Publisher

Автоматическая система: мониторинг канала-источника (с опциональной фильтрацией по словам-маркерам) → извлечение текста из PDF → саммари через OpenAI → **уведомление всем редакторам** (из админки бота) с кнопками Опубликовать / Запланировать / Редактировать / Отклонить → публикация во все целевые каналы.

**Надёжность:** посты из канала попадают в очередь (outbox) и не теряются при сбоях n8n/сети; при ошибке доставки редакторам или публикации выполняются автоматические повторные попытки. В n8n у ноды «Notify Editor Bot» задан таймаут 300 с, чтобы запрос к боту не обрывался раньше времени. В саммари символы ** и * убираются перед отправкой (без конвертации в разметку). Длинный текст разбивается на части; PDF уходит в обсуждение канала (комментарием к посту) через внутренний API userbot — для этого userbot должен быть участником целевого канала. Публикации выполняются по очереди (одна за раз); поддерживается отложенная публикация по расписанию. Подробнее — в `PROJECT.md`.

## Требования

- Docker и Docker Compose
- Сервер с доступом в интернет (VPS)
- Учётные данные: Telegram API, бот, OpenAI, каналы (см. ниже)

## Быстрый старт

1. Клонируйте или скопируйте проект на сервер.
2. Скопируйте `.env.example` в `.env` и заполните переменные (см. раздел «Переменные окружения»).
3. Один раз сгенерируйте сессию Telegram для userbot:  
   `python scripts/generate_session.py` (локально, с указанными в .env API ID/Hash).  
   Вставьте выданную строку в `TELEGRAM_SESSION_STRING` в `.env`.
4. Запуск (из каталога проекта):  
   `cd ~/parser`  
   `docker compose up -d`
5. В n8n (через nginx: http://IP или https://n8n.neurascope.pro) импортируйте workflow из `n8n/workflows/pdf_processing.json`, настройте ноды (см. `n8n/workflows/README.md`). В workflow уже учтены: очистка null-байтов из текста, экранирование SQL, ON CONFLICT при повторе запроса.
6. Укажите в n8n URL webhook (например `https://n8n.neurascope.pro/webhook/pdf-post`) и этот же URL пропишите в `.env` как `N8N_WEBHOOK_URL`.

## Переменные окружения

Все секреты и настройки задаются в `.env` (файл не коммитится в git).

| Переменная | Описание |
|------------|----------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | БД для n8n и editor_bot |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | От my.telegram.org (аккаунт @riskerlb) |
| `TELEGRAM_SESSION_STRING` | Строка сессии (скрипт `scripts/generate_session.py`) |
| `SOURCE_CHANNEL` | Канал-источник (username или ID, например `@channel` или `-1001234567890`) |
| `N8N_WEBHOOK_URL` | Полный URL webhook n8n (например `https://n8n.neurascope.pro/webhook/pdf-post`) |
| `BOT_TOKEN` | Токен бота @Neuralookerbot |
| `EDITOR_CHAT_ID` | Telegram user ID главного редактора (должен быть в списке редакторов в админке; посты приходят **всем** из списка «Редакторы») |
| `TARGET_CHANNEL_ID` | Fallback целевого канала, если в админке «Целевые каналы» пусто (например `-1001234567890`) |
| `EDITOR_BOT_WEBHOOK_TOKEN` | Секрет для POST от n8n к editor-bot (заголовок Authorization: Bearer). Если задан — запросы без токена отклоняются |
| `USERBOT_API_URL` | URL внутреннего API userbot для привязки PDF к посту в обсуждении (в Docker: `http://userbot:8081`) |
| `USERBOT_API_TOKEN` | Секрет для вызова API userbot (один и тот же для userbot и editor-bot) |
| `DATABASE_URL` | В Docker можно не задавать — собирается из POSTGRES_* |
| `OPENAI_API_KEY` | Задаётся в n8n в credential OpenAI (или в .env для n8n) |
| `TELEGRAM_PROXY` или `HTTP_PROXY` | Опционально. Прокси для запросов к Telegram (editor-bot, userbot); при замедлении/блокировках в РФ задайте тот же прокси, что и для n8n (например `http://proxy:3128`). Если задан только `HTTP_PROXY`, он используется и для n8n, и для TG. |

## Как менять промпт OpenAI

- В n8n откройте workflow «PDF Processing…», ноду **OpenAI**.
- Измените текст системного/пользовательского сообщения (промпт).
- Сохраните workflow. Изменения применяются без перезапуска контейнеров.

## Как сменить канал-источник или целевые каналы

**Через админку бота (рекомендуется):** от пользователя с `EDITOR_CHAT_ID` отправьте `/admin` → «Каналы-источники» или «Целевые каналы». Целевых каналов может быть несколько; публикация идёт во все активные. Слова-маркеры задаются в «Слова-маркеры» (если пусто — в обработку попадают все посты).

**Через .env:** измените `SOURCE_CHANNEL` и/или `TARGET_CHANNEL_ID` (fallback), затем `docker compose up -d`.

## Как перезапустить сервисы

Все команды — из каталога проекта (`cd ~/parser`).

- Все: `docker compose restart`
- Только userbot: `docker compose restart userbot`
- Только editor-bot: `docker compose restart editor-bot`
- Только n8n: `docker compose restart n8n`

**Пересборка без кеша** (после смены зависимостей или при сбоях сборки):  
`docker compose build --no-cache && docker compose up -d`

## Логи

- Все сервисы: `docker compose logs -f`
- Userbot: `docker compose logs -f userbot`
- Editor-bot: `docker compose logs -f editor-bot`
- n8n: `docker compose logs -f n8n`

## Бэкап БД

Ежедневный бэкап: `./scripts/backup_db.sh` (из корня проекта). Восстановление: см. [docs/backup_restore.md](docs/backup_restore.md) (cron, restore от пользователя postgres, dry-run).

## SSL (HTTPS для n8n)

1. Убедитесь, что домен n8n.neurascope.pro указывает на IP сервера.
2. Получите сертификат (см. `scripts/init-letsencrypt.sh` или документацию certbot).
3. Подключите конфиг с SSL: см. `nginx/conf.d/n8n.ssl.conf.example`.
4. Перезагрузите nginx: `docker compose exec nginx nginx -s reload`.

## VK

Публикация во ВКонтакте подготовлена (модуль в коде), но отключена до разблокировки аккаунта VK. В `.env`: `VK_ENABLED=false`, при необходимости позже задать `VK_TOKEN` и `VK_GROUP_ID`.

## Структура проекта

- `userbot/` — мониторинг канала, скачивание PDF, отправка в n8n
- `editor_bot/` — приём постов от n8n, рассылка **всем редакторам**, подготовка саммари (удаление ** и *, экранирование HTML), публикация в TG (текст чанками, PDF в обсуждение или ответ), очередь публикаций и отложенная публикация
- `n8n/workflows/` — workflow для обработки PDF и OpenAI
- `init_db/` — схема БД и миграции (001–007: админка, keywords, target_channels, отложенная публикация, outbox userbot, ретраи доставки редакторам)
- `nginx/` — reverse proxy для n8n
- `scripts/` — генерация сессии Telegram, бэкап БД, init SSL

## Тесты

- Userbot: `cd userbot && PYTHONPATH=. pytest tests/ -v`
- Editor-bot: `cd editor_bot && PYTHONPATH=. pytest tests/ -v`
