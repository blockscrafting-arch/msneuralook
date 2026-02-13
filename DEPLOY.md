# Деплой на VPS (90.156.134.38)

Пошаговая инструкция для запуска системы на сервере.

## Предварительно

- DNS: запись для `n8n.neurascope.pro` должна указывать на `90.156.134.38`.
- Локально: заполненный `.env` (можно скопировать с сервера после первого создания).

## 1. Подключение к серверу

```bash
ssh goutach@90.156.134.38
# пароль по запросу
```

## 2. Установка Docker и Docker Compose (если ещё не установлены)

**Ubuntu/Debian.** Сначала ставим Docker (он создаёт группу `docker`):

```bash
sudo apt-get update
sudo apt-get install -y docker.io
```

Плагин Compose (команда `docker compose`):

```bash
sudo apt-get install -y docker-compose-plugin
```

Если пакет `docker-compose-plugin` не найден (E: Unable to locate package), установить вручную:

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
# для x86_64:
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
# для aarch64 (ARM): заменить x86_64 на aarch64 в URL
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

Добавить пользователя в группу и перелогиниться:

```bash
sudo usermod -aG docker $USER
exit
# зайти по SSH снова, затем: docker run hello-world && docker compose version
```

## 3. Копирование проекта на сервер

**На сервере:** `~` — это домашний каталог пользователя (например `/home/goutach`). Путь к проекту: `~/parser` = `/home/goutach/parser`.

С локальной машины (из каталога проекта):

```bash
scp -r . goutach@90.156.134.38:~/parser
```

Или на сервере через git: `git clone <repo> ~/parser && cd ~/parser`.

**Обновление без git:** скопировать только изменённые каталоги, например `init_db`, `userbot`, `editor_bot`, затем на сервере применить миграции (см. раздел «Миграции БД») и выполнить `docker compose up -d --build userbot editor-bot`.

## 4. Создание .env на сервере

**Важно:** файл `.env` должен лежать в каталоге проекта (`~/parser`), а не в домашнем каталоге. Текущий каталог можно проверить: `pwd`.

```bash
cd ~/parser
cp .env.example .env
nano .env   # или vi
```

Заполнить все переменные (токены, ID каналов, пароль Postgres и т.д.). Пароль Postgres сгенерировать: `openssl rand -base64 24`. `TELEGRAM_SESSION_STRING` получают отдельно (см. п. 5).

**Важно:** в `.env` не пишите комментарии на той же строке, что и значение. Иначе в переменную попадёт весь текст (например `SOURCE_CHANNEL= # опционально...` сделает значение с комментарием). Комментарий — отдельной строкой выше. Для пустых значений используйте одну строку, например `SOURCE_CHANNEL=`.

## 5. Генерация сессии Telegram (userbot)

Сессию удобнее сгенерировать **локально** (на компьютере с Python и доступом в Telegram):

1. Установить: `pip install telethon pydantic-settings python-dotenv`
2. В каталоге проекта скопировать `.env` с сервера или создать с `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` (остальное можно пустым).
3. Запустить: `python scripts/generate_session.py`
4. Ввести номер телефона и код из Telegram.
5. Скопировать выведенную строку `TELEGRAM_SESSION_STRING=...` и добавить в `.env` на сервере.

## 6. Запуск контейнеров

**Важно:** все команды `docker compose` нужно выполнять из каталога проекта. Если видите ошибку `no configuration file provided: not found` — вы в другой директории; перейдите: `cd ~/parser`.

Убедиться, что вы в каталоге проекта (`pwd` → `/home/goutach/parser`), затем:

```bash
cd ~/parser
docker compose up -d
docker compose ps   # проверить, что все сервисы running
```

При первой ошибке (например, нет POSTGRES_PASSWORD) — исправить `.env` в `~/parser` и снова `docker compose up -d`.

**Изменения в `.env`** подхватываются только при пересоздании контейнеров. Команда `docker compose restart` не перечитывает `.env`. После правки `.env` выполняйте `docker compose up -d` (или `docker compose up -d <service>`).

**Сборка без кеша** (после смены зависимостей в requirements или при «странных» ошибках сборки): `docker compose build --no-cache && docker compose up -d`. Подробнее — раздел «Полная пересборка и наблюдение за логами».

### Бэкапы БД

Подробнее: [docs/backup_restore.md](docs/backup_restore.md). Перед применением миграций выполнить ручной бэкап: `./scripts/backup_db.sh` или `./scripts/rollout_backup.sh`.

### Миграции БД (при первом развёртывании или после обновления)

Применить по очереди (если ещё не применялись):

```bash
cd ~/parser
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_001_admin.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_002_pdf_path_nullable.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_003_keywords.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_004_target_channels.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_005_scheduled.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_006_userbot_outbox.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_007_delivery_retry.sql
docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_008_keyword_groups.sql
```

- 001 — админка (source_channels, admins, editors).
- 002 — pdf_path допускает NULL.
- 003 — слова-маркеры (keywords).
- 004 — несколько целевых каналов (target_channels).
- 005 — отложенная публикация (scheduled_at, статус scheduled).
- 006 — userbot outbox (надёжная доставка в n8n).
- 007 — editor-bot: delivery_attempts, next_retry_at, статусы publishing, send_failed, publish_failed.
- 008 — группы маркеров (keyword_groups), привязка маркеров к группе и к каналу для маршрутизации публикации.

Проверка: `docker compose exec postgres psql -U parser_user -d parser_db -c "\dt keywords target_channels userbot_outbox keyword_groups"` и `\d keywords` (колонка group_id).

## 7. Настройка n8n

1. Открыть в браузере: `http://90.156.134.38:5678` (или после SSL — `https://n8n.neurascope.pro`).
2. Создать учётную запись и войти.
3. Workflows → Import from File → выбрать `n8n/workflows/pdf_processing.json`.
4. В workflow настроить:
   - **Webhook** — активировать workflow, скопировать URL (например `/webhook/pdf-post`).
   - **OpenAI** — добавить credential с ключом OpenAI.
   - **Postgres** — добавить credential (host: postgres, port: 5432, database/user/password из .env). В workflow уже настроены очистка null-байтов в Set row и ON CONFLICT в INSERT.
   - **Notify Editor Bot** — URL должен быть ровно `http://editor-bot:8080/incoming/post` (внутренний хост Docker). В настройках ноды задайте **Timeout** 300000 ms (5 мин), иначе n8n может обрывать запрос до того, как бот разошлёт пост всем редакторам. Editor-bot отправит пост **всем редакторам** из админки (список «Редакторы»).
5. В `.env` на сервере прописать `N8N_WEBHOOK_URL=https://n8n.neurascope.pro/webhook/pdf-post` (или ваш URL). В workflow после Merge стоит нода **Build merged item** (Code), которая собирает один элемент из данных Webhook и Check duplicate; проверка «есть PDF» и путь к файлу берутся из `$('Webhook').first().json` для устойчивости.
6. В `docker-compose.yml` у сервиса n8n в `environment` должны быть (помимо DB_* и N8N_*):
   - `EDITOR_BOT_WEBHOOK_TOKEN: ${EDITOR_BOT_WEBHOOK_TOKEN}` — чтобы в workflow работало `$env.EDITOR_BOT_WEBHOOK_TOKEN`.
   - `N8N_BLOCK_ENV_ACCESS_IN_NODE: "false"` — иначе нода не сможет подставить токен из env.
   - Если для OpenAI задан прокси (HTTP_PROXY/HTTPS_PROXY), добавьте `NO_PROXY: "editor-bot,localhost,127.0.0.1,.local"` и `no_proxy: "editor-bot,localhost,127.0.0.1,.local"`, иначе запрос к editor-bot пойдёт через прокси и вернётся 502.
   - **Прокси для Telegram (РФ и др.):** чтобы направлять запросы editor-bot и userbot к Telegram через прокси, задайте в `.env` переменную `TELEGRAM_PROXY` (например `http://proxy:3128`) или используйте тот же `HTTP_PROXY`, что и для n8n. Один прокси тогда будет использоваться и для n8n (OpenAI и др.), и для Bot API и MTProto. После изменения: `docker compose up -d --build editor-bot userbot`.
   - Для чтения PDF в workflow: `N8N_RESTRICT_FILE_ACCESS_TO: "/home/node/.n8n-files;/data/pdfs"`.
7. После правок в `.env` или docker-compose пересоздать контейнеры: `docker compose up -d` (или только нужный сервис). После смены `N8N_WEBHOOK_URL` перезапустить userbot: `docker compose restart userbot`.

## 8. SSL (HTTPS)

Когда DNS и порты доступны:

```bash
# 1. Сертификат (на сервере)
docker run -it --rm -v parser_certbot_www:/var/www/certbot -v parser_certbot_conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot -d n8n.neurascope.pro --email admin@neurascope.pro --agree-tos

# 2. Файлы для nginx (options-ssl-nginx.conf и ssl-dhparams.pem)
docker run --rm -v parser_certbot_conf:/etc/letsencrypt alpine sh -c "
  apk add --no-cache wget openssl &&
  wget -q -O /etc/letsencrypt/options-ssl-nginx.conf \
    'https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf' &&
  openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
"

# 3. Включить SSL-конфиг и перезагрузить nginx
cp nginx/conf.d/n8n.ssl.conf.example nginx/conf.d/n8n.ssl.conf
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

После смены IP/контейнера n8n при 502 на сайте перезапустите nginx: `docker compose restart nginx`.

## 9. Проверка цепочки (E2E)

**С каналами (userbot → n8n → editor-bot):**

1. В канал-источник отправить тестовое сообщение с прикреплённым PDF.
2. Убедиться, что в логах userbot есть отправка в webhook: `docker compose logs userbot`.
3. В n8n проверить выполнение workflow.
4. В Telegram у редактора должно прийти сообщение от бота с саммари и кнопками.
5. Нажать «Опубликовать» — пост должен появиться в целевом канале.

**Без каналов (только n8n → Postgres → editor-bot):** можно вызвать webhook вручную. Текст без PDF:

```bash
curl -X POST "https://n8n.neurascope.pro/webhook/pdf-post" \
  -H "Content-Type: application/json" \
  -d '{"post_text":"Тест без PDF","pdf_path":"","message_id":1,"source_channel":"-100111","channel_id":"-100111"}'
```

С PDF: положить тестовый PDF в volume (`docker run --rm -v parser_pdf_storage:/data/pdfs -w /data/pdfs alpine wget -q -O -100111_1.pdf "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"`), затем вызвать curl с `"pdf_path":"/data/pdfs/-100111_1.pdf"` и уникальным `message_id`. При повторе с тем же message_id workflow выполнит ON CONFLICT DO UPDATE (дубликат не упадёт).  
**Если userbot не может записать PDF** (Permission denied в логах): на хосте выполнить `sudo chown -R 1000:1000 /var/lib/docker/volumes/parser_pdf_storage/_data` (или путь к вашему volume).

### Проверка общего тома PDF (userbot и editor-bot)

Все три сервиса (userbot, n8n, editor-bot) используют один и тот же named volume `parser_pdf_storage`, смонтированный в `/data/pdfs`. Если в editor-bot видны только старые файлы или PDF не прикрепляется к уведомлению, убедитесь, что списки файлов совпадают:

```bash
docker compose exec userbot ls /data/pdfs | tail
docker compose exec editor-bot ls /data/pdfs | tail
```

Списки должны совпадать (один том). Если не совпадают — проверить `docker compose config` (нет ли override с другим монтированием) и при необходимости пересоздать контейнеры: `docker compose up -d --build`.

## Как смотреть логи (посты не отправляются)

На сервере в каталоге проекта (`cd ~/parser`):

**Все сервисы (последние 200 строк):**
```bash
docker compose logs --tail=200
```

**Логи в реальном времени по сервису:**
```bash
docker compose logs -f editor-bot   # бот редактора, публикация в канал
docker compose logs -f userbot      # приём постов с канала, вызов n8n
docker compose logs -f n8n          # workflow (PDF → саммари → webhook в бот)
```

**Что искать, если посты не доходят:**

| Проблема | Сервис | Событие в логах (JSON) |
|----------|--------|-------------------------|
| Пост не ушёл в канал после «Опубликовать» | editor-bot | `publish_failed`, `approve_published`, `published_to_channel`, `publish_flood_wait` |
| Кнопка «Опубликовать» не срабатывает / «пост уже обработан» | editor-bot | `approve_rejected_status` (поле `status`), `approve_claim_failed`, `approve_no_target_channel` |
| Редактору не приходит уведомление о новом посте | editor-bot | `incoming_post_send_failed`, `incoming_post_send_done`, `incoming_post_editor_skip` (редактор не нажал Start) |
| Userbot не передаёт пост в n8n | userbot | `outbox_sent`, `outbox_table_missing`, `webhook_sent`, ошибки при отправке в webhook |
| n8n не вызывает бот | n8n | смотреть выполнение workflow и ответ от «Notify Editor Bot»; таймаут ноды не менее 300000 ms |

**Типичные проблемы по логам (что уже исправлено в репо):**

1. **nginx 504 и userbot `webhook_unexpected_error`** — n8n не успевает ответить за время таймаута (PDF + OpenAI занимают 60–120 сек). В конфиге nginx для `location /webhook/` выставлены `proxy_read_timeout 300s` и `proxy_send_timeout 300s`; у userbot таймаут запроса к webhook увеличен до 120 сек. После обновления кода пересобрать образы и перезапустить: `docker compose up -d --build userbot`, `docker compose exec nginx nginx -s reload`.
2. **editor-bot: `Failed to fetch updates - ServerDisconnectedError`** — временные обрывы соединения с Telegram API; бот сам переподключается. Если повторяется часто — проверить сеть/файрвол до api.telegram.org.
3. **n8n: `X-Forwarded-For' header ... trust proxy' setting is false`** — в `docker-compose.yml` у сервиса n8n добавлено `N8N_PROXY_HOPS: "1"`. После правки: `docker compose up -d n8n`.
4. **editor-bot: `incoming_post_duplicate_skipped`** — n8n при повторных попытках (retry) шлёт один и тот же пост несколько раз; бот игнорирует дубликаты по `post_id` и статусу — это нормально.

**Прокси для Telegram:** если в `.env` заданы `TELEGRAM_PROXY` или `HTTP_PROXY`, в логах при старте должны появиться: editor-bot — `"event": "telegram_proxy_enabled"` с полем `proxy` (URL без пароля); userbot — `"event": "telegram_proxy_enabled"` с `proxy_host` и `proxy_port`, затем `"event": "client_created"` с `"proxy": true`. Если этих записей нет — переменные не попали в контейнер (проверить `docker compose exec editor-bot env | grep -E TELEGRAM_PROXY|HTTP_PROXY` и при необходимости пересобрать: `docker compose up -d --build editor-bot userbot`).

5. **userbot: `webhook_failed` status 500, body "Error in workflow"** — n8n вернул 500; причина ошибки в самом workflow. Смотреть в n8n: **Executions** → фильтр по времени или по статусу Error → открыть выполнение и посмотреть, на какой ноде упало и текст ошибки. Часто бывает при рестарте n8n (незавершённые выполнения 123, 124 и т.д.) или при ошибке в ноде (Postgres, OpenAI, Read PDF). После рестарта n8n новые запросы обычно снова проходят (200).

6. **n8n: "Cannot remove headers after they are sent to the client"** — типично при ответе webhook после ошибки в workflow: ответ уже отправлен, затем код снова пытается изменить заголовки. Уменьшается после рестарта n8n; при частом появлении имеет смысл обновить n8n или посмотреть в Issues на GitHub.

7. **userbot показывает 200 (webhook_sent), но посты не пришли в бота** — n8n при 200 может вернуть тело `{ "ok": false, "error": "notify_failed" }`, если вызов Notify Editor Bot не удался после всех ретраев. Раньше userbot не смотрел тело; теперь при таком ответе пишет `webhook_ack_but_notify_failed` и считает доставку неуспешной. **Диагностика:** (1) Логи editor-bot за тот же период: `docker compose logs --since 30m editor-bot | grep -E "incoming_post|send_to_editor|no_editors|failed"` — пришёл ли webhook, были ли ошибки отправки в Telegram. (2) В n8n Executions открыть выполнение по времени — если последняя нода «Notify Failed Response», значит editor-bot не принял запрос (таймаут 120 с, недоступен или 5xx). (3) При большой пачке запросов n8n и editor-bot могут перегружаться; имеет смысл смотреть логи editor-bot на таймауты и FloodWait от Telegram.

**Логи за последние 15 минут (все сервисы):**
```bash
cd ~/parser
docker compose logs --since 15m
```
По одному сервису:
```bash
docker compose logs --since 15m editor-bot
docker compose logs --since 15m userbot
docker compose logs --since 15m n8n
docker compose logs --since 15m nginx
```

**Только ошибки за последний час:**
```bash
docker compose logs --since 1h editor-bot 2>&1 | grep -E '"event":"(publish_failed|send_to_editor_failed|incoming_post_send_failed|webhook_not_acked)"'
```

**Аудит в БД** (кто что одобрил/отклонил):
```bash
docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT * FROM audit_log ORDER BY id DESC LIMIT 20;"
```

## Мониторинг и алерты

Рекомендуется отслеживать следующие события в логах и при необходимости настроить алерты (например по логам в Grafana/Логинг-стек или по метрикам):

| Событие / текст | Где искать | Действие |
|------------------|------------|----------|
| `webhook_all_retries_failed` | userbot | Userbot не смог доставить пост в n8n после всех ретраев. Проверить доступность n8n и nginx, таймауты. |
| `incoming_post_send_to_editor_failed`, `incoming_post_send_failed`, `incoming_post_background_error` | editor-bot | Ошибка отправки уведомления редакторам (Telegram, таймаут). Проверить список редакторов, доступность api.telegram.org. |
| `upstream timed out`, `504` по `/webhook/` | nginx | n8n не успел ответить. Проверить таймауты nginx для `/webhook/` (600s), нагрузку n8n. |
| Ошибка выполнения ноды «Notify Editor Bot» в n8n | n8n (Executions) | Таймаут или обрыв при вызове editor-bot. Проверить editor-bot (логи, здоровье), ретраи в workflow. |

**При появлении таких логов:** проверить доступность сервисов (`docker compose ps`), при необходимости перезапуск: `docker compose restart editor-bot` / `userbot` / `n8n`; просмотр очереди выполнений в n8n (Executions). После смены конфигов nginx — `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload`.

## Диагностика: нет логов userbot и нет исполнений в n8n

Если посты приходят в канал, но в userbot нет записей `new_post` / `webhook_sent`, а в n8n нет исполнений — запрос до вебхука не доходит. Userbot отбрасывает сообщения до отправки в n8n в таких случаях:

| Причина | Лог userbot | Что проверить |
|--------|-------------|----------------|
| Нет ни одного мониторимого канала | `skip_no_monitored_channels` | В БД есть активные `source_channels` или в `.env` задан `SOURCE_CHANNEL`. |
| Сообщение из канала не из списка | `skip_channel_not_monitored` | ID канала (например `3353937872` или `-1003353937872`) совпадает с записью в `source_channels` или с `SOURCE_CHANNEL`. |
| Включён фильтр по ключевым словам, в тексте нет маркеров | `skip_no_keyword_match` | В таблице `keywords` есть слова; текст поста содержит хотя бы одно из них. Либо очистить ключевые слова для теста. |
| Есть PDF, но файл не скачался | `skip_webhook_no_pdf` | Права на каталог PDF, место на диске, доступ Telegram к файлу. |

**Проверки на сервере:**

```bash
cd ~/parser

# 1) Логи userbot за последние 30 минут (ищите skip_*, new_post, webhook_sent)
docker compose logs --since 30m userbot

# 2) Активные каналы-источники в БД (должны быть строки с is_active = true)
docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT channel_identifier, is_active FROM source_channels;"

# 3) Ключевые слова (если строки есть — пост должен содержать хотя бы одно слово)
docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT word FROM keywords;"

# 4) В .env должен быть N8N_WEBHOOK_URL и при пустом source_channels — SOURCE_CHANNEL (ID или -100... канала-источника)
grep -E "N8N_WEBHOOK_URL|SOURCE_CHANNEL" .env
```

После добавления канала в `source_channels` (через админку бота или вручную в БД) или установки `SOURCE_CHANNEL` в `.env` перезапустить userbot: `docker compose up -d --build userbot`, затем снова отправить пост и смотреть логи.

## Полная пересборка и наблюдение за логами

Пересобрать все образы и поднять сервисы заново:

```bash
cd ~/parser
docker compose build --no-cache
docker compose up -d
docker compose ps
```

Смотреть логи всех сервисов в реальном времени (для наблюдения за пачкой документов):

```bash
docker compose logs -f
```

Выйти из просмотра логов: `Ctrl+C`. Чтобы смотреть только n8n и userbot:

```bash
docker compose logs -f n8n userbot
```

## Надёжность цепочки

- **Userbot:** новые посты пишутся в таблицу `userbot_outbox` и по одному отправляются в n8n. При сбое (504, сеть) отправка повторяется с паузой (до 5 попыток). Один и тот же пост (channel_id + message_id) в outbox не дублируется.
- **Editor-bot:** посты, которые не удалось доставить ни одному редактору, раз в 30 с повторно отправляются (до 5 попыток); после 5 неудач статус `send_failed`, через 1 ч посты снова ставятся в очередь. Доставка редакторам — по одному, с паузой 1 с (меньше таймаутов и Broken pipe). Редактор, не нажавший Start в боте, не блокирует остальных. Кнопка «Опубликовать» принимается и при статусе поста `processing` (если редактор уже видит пост).
- **Публикация:** статус «опубликован» ставится только после успешной отправки в канал; при ошибке пост возвращается на утверждение. Посты, застрявшие в «публикуется» более 10 мин, автоматически возвращаются в очередь на утверждение.
- **n8n:** у ноды «Notify Editor Bot» должен быть таймаут не менее 300 000 ms (5 мин), иначе запрос к боту может обрываться до завершения рассылки редакторам.

## Почему пост не публикуется (диагностика)

- **pending_review** — пост уже у редакторов; публикации нет, пока кто-то не нажмёт «Опубликовать». Проверка: в боте есть сообщение с кнопками по этому посту.
- **processing / send_failed** — пост не дошёл до редакторов (n8n не вызвал webhook или отправка в Telegram всем редакторам не удалась). В логах editor-bot ищите `incoming_post_send_failed`, `incoming_post_send_to_editor_failed`. Раз в 30 с scheduler повторяет доставку; после 5 неудач статус станет `send_failed`. Через 1 час такие посты автоматически снова ставятся в очередь на доставку.
- **publishing** — публикация в канал началась, но упала (сеть/Telegram). Редактору показывается «Ошибка публикации. Пост возвращён на утверждение.» — нужно снова нажать «Опубликовать». Если никто не нажал, через 10 минут пост автоматически вернётся в `pending_review`.
- **«Не задан целевой канал»** — в админке бота не указан целевой канал. Зайти в /admin → целевые каналы.
- **«Пост уже обработан или не найден»** — в БД пост уже в статусе `published` или `rejected`, либо другой редактор только что нажал «Опубликовать». В логах: `approve_rejected_status` (текущий статус) или `approve_claim_failed`.

Проверка по БД:
```bash
docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT status, count(*) FROM posts GROUP BY status;"
docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT id, status, delivery_attempts, last_delivery_error FROM posts WHERE status IN ('send_failed','processing') ORDER BY id DESC LIMIT 10;"
```

Почему не опубликовался (по логам editor-bot):
```bash
docker compose logs --since 24h editor-bot 2>&1 | grep -E '"event":"(approve_rejected_status|approve_claim_failed|approve_no_target_channel|publish_failed|approve_published)"'
```
- **approve_published** — пост успешно опубликован (редактор нажал «Опубликовать», публикация в канал прошла).
- **approve_rejected_status** — нажали «Опубликовать», но статус поста не из разрешённых (pending_review, publishing, processing); в логе будет `status`.
- **approve_claim_failed** — между нажатием и записью статус сменился (другой редактор уже отправил в публикацию или пост уже published).
- **approve_no_target_channel** — не задан целевой канал в админке.
- **publish_failed** — ошибка при отправке в канал (сеть/Telegram); в логе будет `error`.

## Оповещения в Telegram при сбоях

**Куда приходят:** в личку Telegram пользователю с указанным ID (например 551570137).

**1. Ошибки внутри editor-bot (в .env сервера):**

В `~/parser/.env` добавьте (подставьте свой Telegram user ID):

```env
ALERT_CHAT_ID=551570137
```

После этого перезапустите editor-bot: `docker compose up -d editor-bot`.

Бот будет присылать сообщения при:
- необработанном исключении в event loop (кроме «connection lost» / «broken pipe»);
- ошибке публикации поста в канал (кнопка «Опубликовать» не сработала);
- ситуации, когда пост не удалось доставить ни одному редактору после 5 попыток.

Один и тот же тип алерта не повторяется чаще чем раз в 15 минут.

**2. Падение контейнеров (cron на сервере):**

Скрипт `scripts/health_alert.sh` проверяет, что контейнеры postgres, editor-bot, userbot, n8n в состоянии Up. Если какой-то не в работе — отправляет сообщение в Telegram.

На сервере в `~/parser/.env` добавьте (можно использовать тот же бот и тот же chat_id):

```env
TELEGRAM_ALERT_BOT_TOKEN=<токен бота, например BOT_TOKEN из .env>
TELEGRAM_ALERT_CHAT_ID=551570137
```

Добавьте в crontab (`crontab -e`):

```cron
*/5 * * * * cd /home/goutach/parser && set -a && [ -f .env ] && . ./.env && set +a && [ -n "$TELEGRAM_ALERT_CHAT_ID" ] && /bin/sh ./scripts/health_alert.sh
```

(замените `/home/goutach/parser` на свой путь к проекту). Тогда раз в 5 минут будет проверка; при падении сервиса придёт сообщение.

## Полезные команды

- Текущий каталог: `pwd`. Перейти в проект: `cd ~/parser`.
- Логи: `docker compose logs -f userbot` / `editor-bot` / `n8n`
- Перезапуск: `docker compose restart <service>`. Чтобы подхватить новый `.env`: `docker compose up -d` (или `docker compose up -d <service>`).
- После изменений таймаутов или кода userbot/editor-bot: `docker compose up -d --build userbot editor-bot`, затем `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload` (чтобы nginx подхватил новые таймауты для `/webhook/`).
- Остановка: `docker compose down`
- Проверка БД: `docker compose exec postgres psql -U parser_user -d parser_db -c "SELECT id, source_channel, status FROM posts ORDER BY id DESC LIMIT 5;"`

Целевые каналы, слова-маркеры и **список редакторов** настраиваются в боте через `/admin`. Уведомления о новых постах приходят **всем** из списка «Редакторы». У поста доступны кнопки: Опубликовать, Запланировать, Редактировать, Отклонить. Саммари отображается с форматированием (жирный/курсив); при публикации в канал текст уходит частями, PDF — в обсуждение канала или ответом. Подробнее — в `PROJECT.md` (разделы 9, 12, 15).
