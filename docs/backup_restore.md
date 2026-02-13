# Бэкапы и восстановление БД

## Подробный гайд: что сделать вручную

Пошаговая инструкция для однократной настройки на сервере. Выполнять по порядку.

### Шаг 1: Подключиться к серверу и перейти в каталог проекта

```bash
ssh ваш_пользователь@90.156.134.38
cd ~/parser
# или тот путь, где лежит проект (проверьте: ls docker-compose.yml)
```

Убедитесь, что вы в корне проекта: должны быть папки `scripts`, `init_db`, файлы `docker-compose.yml`, `.env`.

- [ ] Я в каталоге проекта, вижу `docker-compose.yml` и `scripts/backup_db.sh`.

---

### Шаг 2: Убедиться, что контейнер Postgres запущен

```bash
docker compose ps postgres
```

Должна быть строка с контейнером `parser_postgres` и статусом `Up` (или `running`).

Если контейнер не запущен:

```bash
docker compose up -d postgres
```

- [ ] Контейнер postgres запущен.

---

### Шаг 3: Создать каталог для бэкапов и один раз запустить бэкап вручную

Если при запуске скрипта появится `Permission denied`, выдайте права на выполнение (один раз):

```bash
chmod +x scripts/backup_db.sh scripts/restore_db.sh
```

Если появится **`cannot execute: required file not found`** — у скриптов скорее всего окончания строк Windows (CRLF). Исправьте на сервере (один раз):

```bash
sed -i 's/\r$//' scripts/backup_db.sh scripts/restore_db.sh
```

После этого снова запустите `./scripts/backup_db.sh`.

Затем:

```bash
mkdir -p backups
./scripts/backup_db.sh
```

Ожидаемый вывод: `Backup: ./backups/parser_db_YYYYMMDD_HHMMSS.sql` (с текущей датой и временем).

Проверьте, что файл создан и не пустой:

```bash
ls -la backups/
head -5 backups/parser_db_*.sql
```

В начале файла должны быть строки с `DROP` и далее `CREATE TABLE` (дамп с флагами `--clean --if-exists`).

- [ ] Файл бэкапа создан, в нём есть DROP и CREATE.

---

### Шаг 4: (Опционально) Проверить dry-run восстановления

Подставьте вместо `YYYYMMDD_HHMMSS` реальное имя файла из `backups/`:

```bash
RESTORE_DRY_RUN=1 BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh
```

Ожидаемый вывод: строка `Dry-run: would restore from ...` и команда с `psql -U postgres`. Код выхода 0.

- [ ] Dry-run выполнился без ошибок.

---

### Шаг 5: Настроить cron для ежедневного бэкапа

1. Откройте crontab:

   ```bash
   crontab -e
   ```

2. Узнайте полный путь к проекту (он понадобится в строке cron):

   ```bash
   pwd
   # например: /home/goutach/parser
   ```

3. Добавьте **одну строку** (замените `/home/goutach/parser` на ваш путь из `pwd`):

   ```bash
   0 3 * * * cd /home/goutach/parser && BACKUP_DIR=/home/goutach/parser/backups KEEP_DAYS=7 BACKUP_LOG=/home/goutach/parser/backups/cron.log ./scripts/backup_db.sh 2>&1
   ```

   Это запуск бэкапа каждый день в 03:00; логи пишутся в `backups/cron.log`.

4. Сохраните и закройте редактор (в nano: Ctrl+O, Enter, Ctrl+X; в vim: `:wq`).

5. Проверьте, что задание попало в crontab:

   ```bash
   crontab -l
   ```

- [ ] Строка cron добавлена, путь к проекту подставлен верно.

---

### Шаг 6: (Рекомендуется) Один раз проверить, что cron сработал

Дождаться следующего дня после 03:00 или добавить временное задание на ближайшие минуты.

Пример — запуск через 2 минуты (подставьте свой путь):

```bash
# Текущее время + 2 минуты, например если сейчас 14:30:
# 32 14 * * * cd /home/goutach/parser && ...
crontab -e
# добавьте строку с временем через 2 минуты, сохраните, подождите 2 минуты
```

Проверка:

```bash
ls -la backups/
cat backups/cron.log
```

Должна появиться новая запись в `cron.log` и новый файл бэкапа (или обновлённый список файлов).

После проверки можно удалить тестовую строку из crontab и оставить только `0 3 * * * ...`.

- [ ] Cron хотя бы один раз выполнил бэкап (по логу или по новому файлу).

---

### Шаг 7: Запомнить, как восстанавливаться при сбое

1. Остановить сервисы:  
   `docker compose stop editor-bot userbot n8n`

2. Восстановить (подставить путь к нужному файлу из `backups/`):  
   `BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh`  
   Подтвердить вводом `y` и Enter.

3. Запустить сервисы:  
   `docker compose up -d`

Перед первым реальным восстановлением лучше один раз потренироваться на тестовой копии БД или на стенде (см. раздел «Восстановление» ниже).

- [ ] Я знаю три команды: stop → restore → up -d.

---

### Краткий чек-лист после настройки

| Действие | Сделано |
|----------|---------|
| Каталог `backups/` создан, ручной бэкап выполнен | |
| В crontab добавлена строка с путём к проекту и BACKUP_LOG | |
| Проверено, что cron хотя бы раз создал бэкап (по cron.log или файлам) | |
| Запомнены команды восстановления (stop → restore → up -d) | |

---

## Регламент

- **Период:** минимум раз в сутки (рекомендуется cron, например в 03:00).
- **Retention:** хранить бэкапы не менее 7 дней (переменная `KEEP_DAYS`, по умолчанию 7). При нехватке места на диске — уменьшить срок или включить сжатие/вынос старых бэкапов.
- **Место хранения:** каталог на сервере (по умолчанию `./backups`, задаётся через `BACKUP_DIR`). При необходимости копировать в внешнее хранилище или другой сервер (см. раздел «Вынос бэкапов»).

## Рекомендуемый cron

На сервере выполнять бэкап из **корня проекта**. Путь к проекту замените на свой (например `pwd` в каталоге проекта).

```bash
crontab -e
```

Добавить строку (бэкап каждый день в 03:00, логирование в файл):

```bash
0 3 * * * cd /path/to/parser && BACKUP_DIR=/path/to/parser/backups KEEP_DAYS=7 BACKUP_LOG=/path/to/parser/backups/cron.log ./scripts/backup_db.sh 2>&1
```

Пример с путём `/home/goutach/parser`:

```bash
0 3 * * * cd /home/goutach/parser && BACKUP_DIR=/home/goutach/parser/backups KEEP_DAYS=7 BACKUP_LOG=/home/goutach/parser/backups/cron.log ./scripts/backup_db.sh 2>&1
```

## Восстановление

1. **Остановить сервисы**, использующие БД (обязательно для консистентности):
   ```bash
   docker compose stop editor-bot userbot n8n
   ```

2. **Восстановить** из файла (скрипт выполнит restore от пользователя `postgres`):
   ```bash
   BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh
   ```
   Скрипт запросит подтверждение. Для неинтерактивного запуска (например из своих скриптов): `RESTORE_CONFIRM=1 BACKUP_FILE=... ./scripts/restore_db.sh`.

3. **Запустить сервисы**:
   ```bash
   docker compose up -d
   ```

**Важно:** один раз после настройки проверьте восстановление на копии БД или тестовом стенде.

### Проверка перед первым продакшен-restore

- [ ] Остановлены сервисы editor-bot, userbot, n8n.
- [ ] Переменная `BACKUP_FILE` указывает на нужный файл бэкапа и файл существует.
- [ ] Выполнена команда восстановления.
- [ ] После `docker compose up -d` проверены логи и наличие данных в приложении и n8n.

## Dry-run восстановления

Проверить команду без выполнения:

```bash
RESTORE_DRY_RUN=1 BACKUP_FILE=./backups/parser_db_YYYYMMDD_HHMMSS.sql ./scripts/restore_db.sh
```

## Вынос бэкапов (опционально)

Скрипт `backup_db.sh` создаёт только SQL-файл. При необходимости:

- **Сжатие:** после бэкапа в cron можно добавить `gzip "$FILE"` (тогда при восстановлении использовать `zcat backup.sql.gz | docker compose exec -T postgres psql -U postgres -d parser_db -X` или распаковать и передать в `restore_db.sh`).
- **Копирование на другой сервер:** rsync, rclone или загрузка в S3 — настроить отдельно (например отдельная строка в cron после бэкапа).

## Проверка регламента

Раз в квартал или после изменения скриптов бэкапа/восстановления рекомендуется выполнить **тестовое восстановление** в отдельную БД или тестовый контейнер и убедиться, что приложение и n8n видят данные.
