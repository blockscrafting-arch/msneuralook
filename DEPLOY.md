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

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# выйти и зайти снова по SSH, чтобы группа применилась
```

## 3. Копирование проекта на сервер

С локальной машины (из каталога проекта):

```bash
scp -r . goutach@90.156.134.38:~/parser
# или через git:
# на сервере: git clone <repo> parser && cd parser
```

## 4. Создание .env на сервере

```bash
cd ~/parser
cp .env.example .env
nano .env   # или vi
```

Заполнить все переменные (токены, ID каналов, пароль Postgres и т.д.). Сохранить.

## 5. Генерация сессии Telegram (userbot)

Сессию удобнее сгенерировать **локально** (на компьютере с Python и доступом в Telegram):

1. Установить: `pip install telethon pydantic-settings python-dotenv`
2. В каталоге проекта скопировать `.env` с сервера или создать с `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` (остальное можно пустым).
3. Запустить: `python scripts/generate_session.py`
4. Ввести номер телефона и код из Telegram.
5. Скопировать выведенную строку `TELEGRAM_SESSION_STRING=...` и добавить в `.env` на сервере.

## 6. Запуск контейнеров

```bash
cd ~/parser
docker-compose up -d
docker-compose ps   # проверить, что все сервисы running
```

При первой ошибке (например, нет POSTGRES_PASSWORD) — исправить `.env` и снова `docker-compose up -d`.

## 7. Настройка n8n

1. Открыть в браузере: `http://90.156.134.38:5678` (или после SSL — `https://n8n.neurascope.pro`).
2. Создать учётную запись и войти.
3. Workflows → Import from File → выбрать `n8n/workflows/pdf_processing.json`.
4. В workflow настроить:
   - **Webhook** — активировать workflow, скопировать URL (например `/webhook/pdf-post`).
   - **OpenAI** — добавить credential с ключом OpenAI.
   - **Postgres** — добавить credential (host: postgres, port: 5432, database/user/password из .env).
5. В `.env` на сервере прописать `N8N_WEBHOOK_URL=https://n8n.neurascope.pro/webhook/pdf-post` (или ваш URL).
6. Перезапустить userbot: `docker-compose restart userbot`.

## 8. SSL (HTTPS)

Когда DNS и порты доступны:

```bash
# Вариант с certbot вручную (на сервере)
docker run -it --rm -v parser_certbot_www:/var/www/certbot -v parser_certbot_conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot -d n8n.neurascope.pro --email admin@neurascope.pro --agree-tos
```

Затем добавить конфиг SSL в nginx (см. `nginx/conf.d/n8n.ssl.conf.example`), смонтировать volume с сертификатами в nginx и перезагрузить nginx.

## 9. Проверка цепочки (E2E)

1. В канал-источник отправить тестовое сообщение с прикреплённым PDF.
2. Убедиться, что в логах userbot есть отправка в webhook: `docker-compose logs userbot`.
3. В n8n проверить выполнение workflow.
4. В Telegram у редактора должно прийти сообщение от бота с саммари и кнопками.
5. Нажать «Опубликовать» — пост должен появиться в целевом канале.

## Полезные команды

- Логи: `docker-compose logs -f userbot` / `editor-bot` / `n8n`
- Перезапуск: `docker-compose restart <service>`
- Остановка: `docker-compose down`
