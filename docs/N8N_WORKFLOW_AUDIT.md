# Проверка n8n workflow (pdf_processing.json) по Context7

Сверка с [n8n docs](https://docs.n8n.io) (библиотека `/n8n-io/n8n-docs`).

---

## 1. Webhook → ответ (responseMode: onReceived)

**Текущее:** Webhook с `responseMode: "onReceived"` (ответ сразу при получении запроса).

**Причина перехода с lastNode:** При `responseMode: "lastNode"` n8n держит HTTP-соединение открытым до завершения воркфлоу (иногда минуты: PDF + OpenAI). Когда соединение уже закрыто (таймаут nginx/клиента) или при особенностях обработки нескольких веток, при попытке отправить ответ возникает ошибка **"Cannot remove headers after they are sent to the client"** — в логах n8n десятки таких сообщений. Переход на **onReceived** устраняет это: ответ уходит сразу (200 + «Workflow got started»), воркфлоу выполняется в фоне, повторная отправка ответа не происходит.

**По документации n8n:**
- **Immediately (onReceived):** возвращает 200 сразу, не дожидаясь завершения воркфлоу; тело ответа по умолчанию — `{"status": "Workflow got started"}`.
- **When Last Node Finishes (lastNode):** ждёт окончания воркфлоу и отдаёт выход последней ноды — при длинном воркфлоу и таймаутах даёт «Cannot remove headers...».

**Компромисс:** Userbot больше не получает в теле ответа `{ ok: true, skipped: "duplicate" }` или `{ ok: false, error: "notify_failed" }` — только быстрый 200. Для приёма поста этого достаточно; различие «дубликат» / «notify_failed» можно отслеживать по логам и исполнениям n8n.

---

## 2. Merge (combine)

**Текущее:** `"mode": "combine", "options": {}` — без `mergeByFields` и без явного выбора «by position» / «by fields».

**По документации n8n:**
- Режим **Combine** может быть: **by position**, **by matching fields**, **by all combinations**.
- **By position:** элемент 0 входа 1 склеивается с элементом 0 входа 2 и т.д.
- В примерах «by fields» задаётся через `mergeByFields.values` (field1, field2).

**Риск:** При пустом `options` поведение по умолчанию может отличаться в разных версиях. У вас один элемент с Webhook и один с Check duplicate — нужна именно склейка по позиции.

**Рекомендация:** В UI n8n в ноде Merge для режима Combine явно выбрать **Combine by position** и пересохранить workflow, чтобы в JSON при необходимости появились явные параметры (если версия ноды это пишет в options). Так поведение не будет зависеть от дефолтов.

**Реализовано (обход проблемы):** На практике Merge в ряде конфигураций отдаёт только выход Check duplicate (`{ is_duplicate }`), без данных вебхука (`body`, `pdf_path` и т.д.) — элементы по позиции не сличаются. Поэтому после Merge добавлена нода **Build merged item** (Code): она формирует **один** элемент по ссылкам на узлы — данные из `$('Webhook').first().json` и `is_duplicate` из `$('Check duplicate').first().json`. Вход в **IF new post** идёт только от этой ноды. Условие **Has PDF** и путь в **Read PDF** используют `$('Webhook').first().json.body?.pdf_path ?? $('Webhook').first().json.pdf_path` для устойчивости (не зависят от выхода Merge).

---

## 3. Postgres: SQL-инъекции (Check duplicate + INSERT)

**Текущее:** Запросы собираются через подстановку выражений в строку:
- Check duplicate: `source_channel` и `message_id` вставлены как `'{{ ... }}'` и `{{ ... }}` с ручным экранированием (`.replace(/\\x00/g, '').replace(/'/g, "''")` и т.д.).
- Postgres INSERT: то же для всех текстовых полей.

**По документации n8n (Postgres):**
- Рекомендуется использовать **Query Parameters** (плейсхолдеры `$1`, `$2`, … в запросе и массив значений в Options).
- «n8n automatically sanitizes data provided in query parameters» — это снижает риск SQL-инъекций.

**Проблемы:**
- Ручное экранирование легко сломать при краевых случаях (обратные слэши, не-UTF-8, управляющие символы).
- `message_id`: используется `{{ $json.body?.message_id ?? $json.message_id ?? 0 }}`. Если приходит строка или не число — в запрос попадёт не число (риск ошибки или неверной логики). Для `source_message_id` в INSERT тип в Set задан number, но в Check duplicate выражение может вернуть не число.

**Рекомендация:**
- Переписать **Check duplicate** и **Postgres INSERT** на параметризованные запросы: в Query — `$1`, `$2`, …; в Options → Query Parameters — массив выражений, например `[ выражение для source_channel, выражение для message_id ]`. Значения передавать через параметры, а не подставлять в строку.
- Для `message_id` явно приводить к числу в выражении, например: `={{ Math.floor(Number($json.body?.message_id ?? $json.message_id ?? 0)) || 0 }}`.

---

## 4. Read PDF (Read Binary File)

**Текущее:** `filePath: "={{ $json.body?.pdf_path || $json.pdf_path }}"` — путь из входящего запроса.

**По документации n8n:**
- Для операций с файлами используется **N8N_RESTRICT_FILE_ACCESS_TO** (по умолчанию ограничение до `~/.n8n-files`).
- В вашем docker-compose задано: `N8N_RESTRICT_FILE_ACCESS_TO: "/home/node/.n8n-files;/data/pdfs"` — чтение возможно только из этих каталогов.

**Вывод:** Path traversal ограничивается n8n. Если в webhook попадёт `pdf_path: "../../etc/passwd"`, чтение не выйдет за пределы разрешённых путей. Риск низкий при текущей настройке. Имеет смысл явно требовать, что `pdf_path` должен начинаться с `/data/pdfs` (в выражении или в следующей ноде), чтобы не полагаться только на глобальный рестрикт.

---

## 5. Notify Editor Bot (HTTP Request)

**Текущее:** POST на editor-bot, retry на ноде: `retryOnFail: true`, `maxTries: 2`, `waitBetweenTries: 10000`, плюс ветка по ошибке: `onError: continueErrorOutput` → Retry Attempt → IF Retry → снова Notify или Notify Failed.

**По документации n8n:**
- В настройках HTTP Request есть **Retry on Fail**, **Max Tries**, **Wait Between Tries** — это стандартный механизм.
- Ошибки можно обрабатывать через второй выход ноды (error output).

**Замечания:**
- Таймаут 300000 ms (5 мин) — совпадает с ожиданием долгой обработки; для вызова к editor-bot обычно достаточно меньшего (например, 60–120 с). Большой таймаут корректен, но при частых таймаутах будет долго заниматься execution.
- Счётчик попыток в «Retry Attempt» даёт до 3 вызовов (1 + 2 по циклу). Логика согласована.

---

## 6. Поток данных и имена нод в выражениях

**Текущее:** В Set row и OpenAI используется `$('Get Prompt').first().json.value`. Get Prompt не соединён выходом с последующими нодами; он выполняется параллельно с Has PDF в одной ветке.

**По документации n8n:** Обращение к другой ноде по имени допустимо; к моменту выполнения нод с такими выражениями предыдущие ноды уже выполнены. Порядок выполнения: IF new post (true) → одновременно Get Prompt и Has PDF → затем Read PDF или OpenAI Text Only и т.д. К моменту OpenAI PDF нода Get Prompt уже отработала — данные доступны. Замечаний нет.

---

## 7. Дубликат и ответ (при responseMode: onReceived)

**Текущее:** Webhook отвечает сразу (`onReceived`), поэтому ветка дубликата и нода «Duplicate response» влияют только на логику воркфлоу (не отправлять повторно в editor-bot). Тело ответа для userbot всегда стандартное («Workflow got started»), не `{ ok, skipped }`. Это приемлемо: userbot считает успехом любой 2xx.

---

## Сводка по Context7

| Элемент | Best practice (Context7) | Текущее состояние | Действие |
|--------|--------------------------|-------------------|----------|
| Ответ webhook | При длинных воркфлоу — Immediately, иначе lastNode/Respond to Webhook | onReceived (исправляет «Cannot remove headers») | Ок; при необходимости — явный Respond to Webhook в ветках |
| Merge | Явно задавать способ combine (position/fields) | combine без явного by position | В UI выбрать Combine by position |
| Postgres | Параметризованные запросы ($1, $2 + Query Parameters) | Строковая подстановка и ручное экранирование | Перейти на Query Parameters; привести message_id к числу |
| Read Binary File | Ограничение путей (N8N_RESTRICT_FILE_ACCESS_TO) | Задано в docker-compose | Ок; при желании проверять префикс пути в выражении |
| HTTP Request retry | Retry on Fail + error output | Настроено, плюс ручной цикл ретраев | Ок |

Критично для безопасности и предсказуемости: **параметризовать запросы к Postgres** и **явно задать ответ при провале уведомления редакторам**. Остальное — усиление ясности и устойчивости к разным версиям n8n.
