# Telegram Parser & Publisher — всё о проекте

Единый документ: контекст, запуск, деплой, настройка n8n, админка, операции.

---

## 1. Суть проекта

Автоматическая система:

1. **Мониторит** канал-источник Telegram (через userbot @riskerlb); посты можно фильтровать по словам-маркерам (если маркеры заданы в админке).
2. **Обрабатывает** новые посты с PDF или только текст: извлекает текст, генерирует саммари через OpenAI. В n8n: очистка null-байтов из текста, экранирование SQL, ON CONFLICT при дубликате (source_channel + message_id).
3. **Отправляет** саммари **всем редакторам** (список из админки бота) в @Neuralookerbot: текст с форматированием (**жирный**, *курсив* → HTML), при необходимости — частями; PDF отдельным сообщением-ответом. Кнопки: Опубликовать / Запланировать / Редактировать / Отклонить.
4. **Публикует** утверждённые посты во **все** целевые каналы: текст — частями до лимита Telegram (4096); PDF — в связанное обсуждение канала (комментарием к посту) или ответом в канал при недоступности. Привязка PDF к посту в обсуждении выполняется через внутренний API userbot (Telethon: GetDiscussionMessage); **userbot должен быть участником целевого канала**. Публикации идут по очереди (одна за раз); поддерживается отложенная публикация (планировщик раз в 30 с).

**Домен n8n:** n8n.neurascope.pro  
**Сервер:** VPS 90.156.134.38

---

## 2. Стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11 (userbot, editor-bot) |
| Мониторинг канала | Telethon + opentele (userbot) |
| Бот редактора | aiogram 3.x |
| Оркестрация, PDF, OpenAI | n8n |
| БД | PostgreSQL 15 (посты, конфиг, audit_log) |
| Инфраструктура | Docker Compose, Nginx, Let's Encrypt |
| Логирование | structlog |
| Тесты | pytest + pytest-asyncio |

---

## 3. Общие правила разработки

- **Модульность:** handlers, services, database, utils — легко править и масштабировать.
- **Версии:** git, коммиты по этапам для отката.
- **Документация:** docstrings (Google style) у модулей и публичных функций.
- **Безопасность:** секреты только в `.env`, не коммитить `.env`; проверка входных данных.
- **Логирование:** ошибки в structlog, критичные действия — в audit_log в БД.
- **Тесты:** критичные потоки (approve/edit/reject, webhook, публикация).

---

## 4. Требования и быстрый старт

**Нужно:** Docker и Docker Compose, VPS, учётные данные (Telegram API, бот, OpenAI, каналы).

1. Клонировать/скопировать проект на сервер.
2. `cp .env.example .env` и заполнить переменные (см. раздел 5).
3. Один раз сгенерировать сессию Telegram: `python scripts/generate_session.py` (локально), вставить вывод в `TELEGRAM_SESSION_STRING`.
4. Запуск: `docker compose up -d`.
5. В n8n импортировать workflow `n8n/workflows/pdf_processing.json`, настроить ноды (раздел 9).
6. В `.env` указать `N8N_WEBHOOK_URL` (URL webhook из n8n).

---

## 5. Переменные окружения (.env)

Файл `.env` — в **корне проекта** (например `~/parser`), не в домашнем каталоге.  
**Важно:** не пишите комментарии на той же строке, что и значение — в переменную попадёт весь текст. Комментарий — отдельной строкой выше.

| Переменная | Описание |
|------------|----------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | БД для n8n и editor_bot. Пароль: `openssl rand -base64 24` |
| `DATABASE_URL` | Опционально; в Docker часто собирается из POSTGRES_* |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | От my.telegram.org (аккаунт userbot) |
| `TELEGRAM_SESSION_STRING` | Строка сессии: `python scripts/generate_session.py` |
| `SOURCE_CHANNEL` | Опционально: fallback канал-источник (-100... или @channel) |
| `N8N_WEBHOOK_URL` | Полный URL webhook n8n (например https://n8n.neurascope.pro/webhook/pdf-post) |
| `BOT_TOKEN` | Токен бота @Neuralookerbot |
| `EDITOR_CHAT_ID` | Telegram user ID редактора (кому приходят посты на утверждение) |
| `TARGET_CHANNEL_ID` | Fallback целевого канала, если в БД (целевые каналы) пусто (-100...) |
| `EDITOR_BOT_WEBHOOK_PATH` | Путь для POST от n8n, **обязательно с /** (например `/incoming/post`) |
| `EDITOR_BOT_WEBHOOK_TOKEN` | Секрет для заголовка Authorization: Bearer (n8n передаёт тот же токен) |
| `USERBOT_API_PORT` | Порт внутреннего API userbot (по умолчанию 8081); для привязки PDF к посту в обсуждении |
| `USERBOT_API_TOKEN` | Секрет для вызова API userbot (один и тот же в .env userbot и editor-bot) |
| `USERBOT_API_URL` | URL API userbot для editor-bot (в Docker: `http://userbot:8081`) |
| `OPENAI_API_KEY` | Для n8n (credential или в .env контейнера n8n) |
| `VK_ENABLED`, `VK_TOKEN`, `VK_GROUP_ID` | Заготовка VK, пока не используется |

**После правки .env** контейнеры нужно пересоздать: `docker compose up -d`. Команда `docker compose restart` не перечитывает `.env`.

---

## 6. Структура проекта

| Каталог/файл | Назначение |
|--------------|------------|
| `userbot/` | Мониторинг канала, скачивание PDF в общий volume, отправка в n8n (нужны права на запись в volume) |
| `editor_bot/` | Приём постов от n8n, рассылка всем редакторам, подготовка саммари (удаление ** и *, экранирование HTML), публикация в каналы (текст чанками, PDF в обсуждение/ответ), очередь публикаций, отложенная публикация |
| `n8n/workflows/` | Workflow обработки PDF и OpenAI (очистка null-байтов, SQL-экранирование, ON CONFLICT) |
| `init_db/` | Схема БД и миграции (001–007: админка, pdf_path, keywords, target_channels, scheduled, outbox userbot, ретраи доставки редакторам) |
| `nginx/` | Reverse proxy для n8n, SSL |
| `scripts/` | generate_session.py, backup_db.sh, rollout_*, init-letsencrypt.sh |
| `shared/pdf_storage/` | Общий volume для PDF (монтируется в userbot и n8n; на хосте при Permission denied: `chown -R 1000:1000` на каталог volume) |

---

## 7. Деплой на VPS (90.156.134.38)

### Предварительно

- DNS: `n8n.neurascope.pro` → `90.156.134.38`.
- Локально: заполненный `.env` (можно скопировать с сервера после создания).

### 7.1 Подключение

```bash
ssh goutach@90.156.134.38
```

### 7.2 Установка Docker и Docker Compose (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo apt-get install -y docker-compose-plugin
```

Если пакет `docker-compose-plugin` не найден:

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
# x86_64:
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
# aarch64: заменить x86_64 на aarch64 в URL
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

Добавить пользователя в группу и перелогиниться:

```bash
sudo usermod -aG docker $USER
exit
# зайти по SSH снова: docker run hello-world && docker compose version
```

### 7.3 Копирование проекта

С локальной машины (из каталога проекта):

```bash
scp -r . goutach@90.156.134.38:~/parser
```

Или на сервере: `git clone <repo> ~/parser && cd ~/parser`.  
Путь к проекту на сервере: `~/parser` (например `/home/goutach/parser`). Проверка: `pwd`.

### 7.4 Создание .env на сервере

```bash
cd ~/parser
cp .env.example .env
nano .env
```

Заполнить переменные. Пароль Postgres: `openssl rand -base64 24`. Сессию Telegram — см. п. 7.5.

### 7.5 Генерация сессии Telegram (userbot)

Удобнее **локально** (Python + доступ в Telegram):

1. `pip install telethon pydantic-settings python-dotenv`
2. В каталоге проекта: `.env` с `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
3. `python scripts/generate_session.py` — ввести телефон и код из Telegram.
4. Скопировать строку `TELEGRAM_SESSION_STRING=...` в `.env` на сервере.

### 7.6 Запуск контейнеров

```bash
cd ~/parser
docker compose up -d
docker compose ps
```

При ошибке (нет POSTGRES_PASSWORD и т.п.) — исправить `.env` и снова `docker compose up -d`.

---

## 8. Настройка n8n

1. Открыть: `http://90.156.134.38:5678` или после SSL — `https://n8n.neurascope.pro`.
2. Создать учётную запись, войти.
3. Workflows → Import from File → `n8n/workflows/pdf_processing.json`.
4. Настроить ноды:
   - **Webhook** — активировать workflow, скопировать URL (например `/webhook/pdf-post`).
   - **OpenAI** — credential с ключом OpenAI.
   - **Postgres** — host: postgres, port: 5432, database/user/password из .env.
   - **Notify Editor Bot** — URL **ровно** `http://editor-bot:8080/incoming/post` (внутренний хост Docker). Иначе n8n не достучится до editor-bot.
5. В `.env`: `N8N_WEBHOOK_URL=https://n8n.neurascope.pro/webhook/pdf-post` (или ваш URL).
6. В `docker-compose.yml` у сервиса n8n в `environment` должны быть:
   - `EDITOR_BOT_WEBHOOK_TOKEN: ${EDITOR_BOT_WEBHOOK_TOKEN}` — для `$env.EDITOR_BOT_WEBHOOK_TOKEN` в workflow.
   - `N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"` — иначе нода не подставит токен из env.
   - При прокси для OpenAI (HTTP_PROXY): `NO_PROXY: "editor-bot,localhost,127.0.0.1,.local"` и `no_proxy: "editor-bot,localhost,127.0.0.1,.local"`, иначе 502 при запросе к editor-bot.
   - Для чтения PDF: `N8N_RESTRICT_FILE_ACCESS_TO: "/home/node/.n8n-files;/data/pdfs"`.
7. После правок: `docker compose up -d`; после смены `N8N_WEBHOOK_URL`: `docker compose restart userbot`.

---

## 9. Workflow n8n (pdf_processing)

Поддерживаются посты: **только PDF**, **только текст**, **PDF + текст**. Пустые посты не приходят (фильтр в userbot).

**Схема:** Webhook → Has PDF? → (Да: Read PDF → Extract → OpenAI → Set row) / (Нет: OpenAI по тексту → Set row) → Postgres INSERT … ON CONFLICT DO UPDATE RETURNING * → Notify Editor Bot.  
В канал-источник попадают только посты, в тексте которых есть хотя бы один маркер (если маркеры заданы в админке → Слова-маркеры); если маркеров нет — проходят все посты.

**Обработка данных в n8n:** в нодах Set row для полей `original_text`, `extracted_text`, `summary` выполняется удаление null-байтов. В запросе Postgres строковые поля экранируются; при дубликате по (source_channel, source_message_id) выполняется UPDATE.  
**Notify Editor Bot:** editor-bot получает post_id, summary, pdf_path и отправляет сообщение **всем редакторам** из БД (список «Редакторы» в админке); при отсутствии редакторов — 503.

**Тело POST от userbot:** `post_text`, `pdf_path` (или пусто), `message_id`, `source_channel`, `channel_id`.  
**Read PDF:** путь к файлу в Docker — `/data/pdfs/xxx.pdf`.  
**Notify Editor Bot:** URL `http://editor-bot:8080/incoming/post`, заголовок `Authorization: Bearer $env.EDITOR_BOT_WEBHOOK_TOKEN`.

Промпт OpenAI меняется в ноде OpenAI в n8n; перезапуск контейнеров не нужен.

**Editor-bot: формат сообщений и публикация.**  
- Сообщения редакторам и в канал отправляются с `parse_mode=HTML`. В тексте саммари символы `**` и `*` **удаляются** (не конвертируются в жирный/курсив), остальное экранируется для безопасности.  
- Длинный текст (>4000 символов) разбивается на части по пробелам/переводам строк; первая часть — с кнопками, остальные и PDF — отдельными сообщениями (PDF привязан ответом к первому текстовому).  
- При публикации в канал: текст уходит частями; PDF по возможности отправляется в связанное обсуждение канала (комментарием к посту). Для точной привязки PDF к посту editor-bot вызывает внутренний API userbot (POST /discussion/resolve); userbot через Telethon получает `discussion_message_id`. **Требование:** userbot должен быть участником целевого канала. При ошибке или недоступности API — PDF уходит ответом в сам канал. Публикации выполняются по очереди (глобальный lock). Используется повтор при FloodWait от Telegram.

---

## 10. SSL (HTTPS для n8n)

```bash
# 1. Сертификат
docker run -it --rm -v parser_certbot_www:/var/www/certbot -v parser_certbot_conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot -d n8n.neurascope.pro --email admin@neurascope.pro --agree-tos

# 2. options-ssl-nginx.conf и ssl-dhparams.pem
docker run --rm -v parser_certbot_conf:/etc/letsencrypt alpine sh -c "
  apk add --no-cache wget openssl &&
  wget -q -O /etc/letsencrypt/options-ssl-nginx.conf \
    'https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf' &&
  openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
"

# 3. Включить SSL и перезагрузить nginx
cp nginx/conf.d/n8n.ssl.conf.example nginx/conf.d/n8n.ssl.conf
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

При 502 после смены IP/контейнера n8n: `docker compose restart nginx`.

---

## 11. Проверка цепочки (E2E)

**С каналами:** пост с PDF в канал-источник → логи userbot → выполнение workflow в n8n → сообщение редактору в боте → «Опубликовать» → пост в целевом канале.

**Без каналов (только n8n → Postgres → editor-bot):**

Текст без PDF:

```bash
curl -X POST "https://n8n.neurascope.pro/webhook/pdf-post" \
  -H "Content-Type: application/json" \
  -d '{"post_text":"Тест без PDF","pdf_path":"","message_id":1,"source_channel":"-100111","channel_id":"-100111"}'
```

С PDF: положить файл в volume (`docker run --rm -v parser_pdf_storage:/data/pdfs -w /data/pdfs alpine wget -q -O -100111_1.pdf "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"`), в curl указать `"pdf_path":"/data/pdfs/-100111_1.pdf"` и **уникальный** `message_id`. При повторе менять `message_id` или удалять запись из `posts`, иначе duplicate key.

---

## 12. Админка и внедрение в прод (rollout)

### Подготовка и бэкап

```bash
docker compose ps
chmod +x scripts/rollout_backup.sh && ./scripts/rollout_backup.sh
# или: docker compose exec -T postgres pg_dump -U parser_user parser_db > backups/parser_db_$(date +%Y%m%d_%H%M%S).sql
```

### Миграции БД (порядок применения)

При первом развёртывании или после обновления кода применить миграции по очереди:

```bash
cd ~/parser
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_001_admin.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_002_pdf_path_nullable.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_003_keywords.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_004_target_channels.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_005_scheduled.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_006_userbot_outbox.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_007_delivery_retry.sql
```

- **001** — таблицы source_channels, admins, editors.
- **002** — pdf_path допускает пустое значение.
- **003** — таблица keywords (слова-маркеры для фильтрации постов в userbot).
- **004** — таблица target_channels (несколько целевых каналов), перенос значения из config.
- **005** — колонка posts.scheduled_at и статус `scheduled` (отложенная публикация).
- **006** — таблица userbot_outbox (очередь доставки в n8n, защита от потери и дублей).
- **007** — колонки posts.delivery_attempts, next_retry_at, last_delivery_error; статусы publishing, send_failed, publish_failed (ретраи доставки редакторам).

Проверка таблиц: `docker compose exec postgres psql -U parser_user -d parser_db -c "\dt keywords target_channels userbot_outbox"` и `SELECT column_name FROM information_schema.columns WHERE table_name='posts' AND column_name IN ('scheduled_at','delivery_attempts');`

### Окружение

В `.env`: `EDITOR_CHAT_ID`, при необходимости `TARGET_CHANNEL_ID` (fallback), `SOURCE_CHANNEL`. Целевые каналы и маркеры задаются в админке бота.

### Перезапуск после rollout

```bash
docker compose up -d --build editor-bot userbot
```

### Валидация

- `./scripts/rollout_validate_db.sh` — таблицы source_channels, admins, editors.
- В Telegram от пользователя с `EDITOR_CHAT_ID`: `/admin` — меню: Каналы-источники, **Целевые каналы**, **Слова-маркеры**, Редакторы, Админы.
- Добавить канал-источник; добавить целевые каналы (или один в «Целевые каналы»); при необходимости — слова-маркеры (если пусто — все посты проходят). В течение ~30 с userbot подхватит каналы и маркеры.
- У поста в боте должны быть кнопки: Опубликовать, Запланировать, Редактировать, Отклонить.
- Audit: `SELECT * FROM audit_log WHERE action LIKE 'admin_%' OR action IN ('scheduled','scheduled_published') ORDER BY created_at DESC LIMIT 10;`

---

## 13. Повседневные операции

| Действие | Команда |
|----------|--------|
| Текущий каталог / переход в проект | `pwd`, `cd ~/parser` |
| Логи | `docker compose logs -f userbot` / `editor-bot` / `n8n` |
| Перезапуск | `docker compose restart <service>` |
| Подхватить новый .env | `docker compose up -d` (или `docker compose up -d <service>`) |
| Остановка | `docker compose down` |
| Проверка БД | `docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT id, source_channel, status FROM posts ORDER BY id DESC LIMIT 5;"` |

**Смена канала-источника:** в админке бота → Каналы-источники (или в `.env` `SOURCE_CHANNEL` и `docker compose up -d`).  
**Целевые каналы:** в админке → Целевые каналы (добавить/удалить). Публикация идёт во все активные. Fallback — один канал из config/`TARGET_CHANNEL_ID`, если таблица target_channels пуста.  
**Слова-маркеры:** в админке → Слова-маркеры. Если список пуст — в обработку попадают все посты из канала-источника; если маркеры заданы — только посты, в тексте которых есть хотя бы одно совпадение (регистронезависимо).  
**Запланированная публикация:** кнопка «Запланировать» у поста → ввод даты/времени (ДД.ММ.ГГГГ ЧЧ:ММ, МСК). Планировщик в editor-bot раз в 30 с публикует посты с наступившим временем во все целевые каналы.

**Бэкап БД:**

```bash
docker compose exec -T postgres pg_dump -U parser_user parser_db > backup_$(date +%Y%m%d).sql
```

Или скрипт: `BACKUP_DIR=./backups ./scripts/backup_db.sh`.  
**Восстановление:** `BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh`. Регламент (cron, retention, место хранения): см. [docs/backup_restore.md](docs/backup_restore.md).

---

## 14. Тесты

- Userbot: `cd userbot && PYTHONPATH=. pytest tests/ -v`
- Editor-bot: `cd editor_bot && PYTHONPATH=. pytest tests/ -v`

---

## 15. Обновление на сервере без git

Если проект на сервер переносится без git (например копированием папок):

1. **С ПК скопировать на сервер** изменённые каталоги (из корня проекта):
   ```bash
   scp -r init_db userbot editor_bot n8n goutach@90.156.134.38:~/parser/
   ```
   Так обновятся миграции (003–005), userbot (фильтр по маркерам, внутренний API для привязки PDF к обсуждению), editor-bot (админка, рассылка всем редакторам, подготовка саммари — удаление ** и *, публикация текста чанками и PDF в обсуждение/ответ, очередь публикаций, планировщик) и при необходимости workflow n8n (очистка null-байтов, SQL, ON CONFLICT). После смены workflow в n8n переимпортировать или обновить вручную.

2. **На сервере** подключиться и перейти в проект:
   ```bash
   ssh goutach@90.156.134.38
   cd ~/parser
   ```

3. **Применить миграции** (если ещё не применялись): см. раздел «Миграции БД» выше; при обновлении с 005 добавить 006 и 007.

4. **Пересобрать и запустить** userbot и editor-bot:
   ```bash
   docker compose up -d --build userbot editor-bot
   ```

5. **Проверить:** `docker compose ps`, логи `docker compose logs --tail 30 editor-bot userbot`, в боте `/admin` — пункты «Целевые каналы» и «Слова-маркеры», у поста — кнопка «Запланировать».

---

## 16. Дополнительная документация

| Файл | Содержание |
|------|-------------|
| `README.md` | Краткое описание и быстрый старт (дублирует части этого файла) |
| `DEPLOY.md` | Деплой по шагам (дублирует разделы 7–11) |
| `ROLLOUT.md` | Чеклист внедрения админки в прод |
| `scripts/rollout_validate.md` | Чеклист валидации после внедрения |
| `AUDIT_REPORT.md` | Аудит проекта (качество, безопасность) |
| `ADMIN_PANEL_AUDIT.md` | Аудит админ-панели |
| `docs/AUDIT_text_only_posts.md` | Аудит поддержки постов без PDF |
| `docs/AUDIT_markers_multitarget_scheduling.md` | Аудит: маркеры, мультиканал, отложенная публикация |
| `.env.example` | Шаблон переменных окружения |

После объединения всей актуальной информации в этот файл остальные документы можно использовать как ссылки или архив.
