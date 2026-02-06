# Telegram Parser & Publisher

Автоматическая система: мониторинг канала-источника → извлечение текста из PDF → саммари через OpenAI → утверждение редактором → публикация в целевой канал.

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
4. Запуск:  
   `docker-compose up -d`
5. В n8n (через nginx: http://IP или https://n8n.neurascope.pro) импортируйте workflow из `n8n/workflows/pdf_processing.json`, настройте ноды (см. `n8n/workflows/README.md`).
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
| `EDITOR_CHAT_ID` | Telegram user ID редактора, число (кому приходят посты на утверждение) |
| `TARGET_CHANNEL_ID` | ID целевого канала для публикации (например `-1001234567890`) |
| `EDITOR_BOT_WEBHOOK_TOKEN` | Секрет для POST от n8n к editor-bot (заголовок Authorization: Bearer). Если задан — запросы без токена отклоняются |
| `DATABASE_URL` | В Docker можно не задавать — собирается из POSTGRES_* |
| `OPENAI_API_KEY` | Задаётся в n8n в credential OpenAI (или в .env для n8n) |

## Как менять промпт OpenAI

- В n8n откройте workflow «PDF Processing…», ноду **OpenAI**.
- Измените текст системного/пользовательского сообщения (промпт).
- Сохраните workflow. Изменения применяются без перезапуска контейнеров.

## Как сменить канал-источник или целевой канал

1. Остановите сервисы: `docker-compose stop userbot editor-bot`.
2. В `.env` измените `SOURCE_CHANNEL` (источник) и/или `TARGET_CHANNEL_ID` (целевой канал).
3. Запустите снова: `docker-compose up -d`.

## Как перезапустить сервисы

- Все: `docker-compose restart`
- Только userbot: `docker-compose restart userbot`
- Только editor-bot: `docker-compose restart editor-bot`
- Только n8n: `docker-compose restart n8n`

## Логи

- Все сервисы: `docker-compose logs -f`
- Userbot: `docker-compose logs -f userbot`
- Editor-bot: `docker-compose logs -f editor-bot`
- n8n: `docker-compose logs -f n8n`

## Бэкап БД

Скрипт `scripts/backup_db.sh` (настроить переменные POSTGRES_* и BACKUP_DIR). Пример одной команды:

```bash
docker-compose exec -T postgres pg_dump -U parser_user parser_db > backup_$(date +%Y%m%d).sql
```

## SSL (HTTPS для n8n)

1. Убедитесь, что домен n8n.neurascope.pro указывает на IP сервера.
2. Получите сертификат (см. `scripts/init-letsencrypt.sh` или документацию certbot).
3. Подключите конфиг с SSL: см. `nginx/conf.d/n8n.ssl.conf.example`.
4. Перезагрузите nginx: `docker-compose exec nginx nginx -s reload`.

## VK

Публикация во ВКонтакте подготовлена (модуль в коде), но отключена до разблокировки аккаунта VK. В `.env`: `VK_ENABLED=false`, при необходимости позже задать `VK_TOKEN` и `VK_GROUP_ID`.

## Структура проекта

- `userbot/` — мониторинг канала, скачивание PDF, отправка в n8n
- `editor_bot/` — приём постов от n8n, кнопки редактору, публикация в TG
- `n8n/workflows/` — workflow для обработки PDF и OpenAI
- `init_db/` — схема БД
- `nginx/` — reverse proxy для n8n
- `scripts/` — генерация сессии Telegram, бэкап БД, init SSL

## Тесты

- Userbot: `cd userbot && PYTHONPATH=. pytest tests/ -v`
- Editor-bot: `cd editor_bot && PYTHONPATH=. pytest tests/ -v`
