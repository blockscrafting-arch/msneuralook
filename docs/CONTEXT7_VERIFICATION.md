# Проверка по Context7 (n8n-docs, aiohttp)

Сверка текущей реализации с официальной документацией n8n и aiohttp.

---

## 1. n8n Workflow (pdf_processing.json)

### 1.1 Webhook — responseMode: lastNode

**Context7 (n8n-docs):** Режим "When Last Node Finishes" — webhook ждёт завершения workflow и возвращает **выход последней выполненной ноды**; код ответа по умолчанию 200.

**У нас:** `responseMode: "lastNode"`. Три концевые ветки:
- Дубликат → **Duplicate response** (Set) → `{ ok: true, skipped: "duplicate" }`.
- Успех → **Notify Editor Bot** (успех) → тело ответа editor-bot.
- Провал ретраев → **Notify Failed Response** (Set) → `{ ok: false, error: "notify_failed" }`.

**Вывод:** Соответствует. Рекомендация docs — таймауты у вызывающей стороны; у userbot таймаут 120 с — ок.

---

### 1.2 Merge — Combine by Position

**Context7 (n8n-docs):** В режиме Combine есть вариант "Merge by Position": элемент 0 входа 1 склеивается с элементом 0 входа 2. Для полей (mergeByFields) параметры другие.

**У нас:** `mode: "combine"`, `combinationMode: "mergeByPosition"`. Webhook → Input 1, Check duplicate → Input 2; один элемент с каждой стороны — склейка по позиции.

**Вывод:** Соответствует. Параметр `combinationMode` задан явно (в коде ноды Merge v2 — именно так).

---

### 1.3 Postgres — Execute Query и выражения в запросе

**Context7 (n8n-docs):** В Query можно использовать n8n expressions; для безопасности рекомендуются **Query Parameters** ($1, $2 + отдельное поле параметров). В вашей версии n8n (2.6.4) параметры из JSON в формате `options.queryParameters` не передавались в драйвер ("there is no parameter $1"), поэтому использован откат к подстановке в строку.

**У нас:**
- **Check duplicate:** запрос с выражениями `{{ ... }}` в строке; экранирование: `.toString().replace(/\\x00/g, '').replace(/'/g, "''").replace(/\\\\/g, '\\\\')`; `source_message_id` — `Math.floor(Number(...)) || 0`.
- **Postgres INSERT:** то же — подстановка в строку с теми же replace; число для `source_message_id` через `Math.floor(Number(...)) || 0`.
- Префикс `=` у поля Query включён (n8n трактует как expression).

**Вывод:** По документации предпочтительны параметризованные запросы; в текущей версии n8n они работают только при настройке Query Parameters в UI. Текущий вариант с ручным экранированием и приведением типов — рабочий компромисс; при обновлении n8n стоит снова попробовать Query Parameters в UI и перенести в JSON при необходимости.

---

### 1.4 Read Binary File (Read PDF) и путь к файлу

**Context7 (n8n-docs):** На чтение/запись файлов влияет **N8N_RESTRICT_FILE_ACCESS_TO**; по умолчанию ограничение до `~/.n8n-files`. Для Docker путь задаётся явно (например `/tmp/` или смонтированный том).

**У нас:** В docker-compose задано `N8N_RESTRICT_FILE_ACCESS_TO: "/home/node/.n8n-files;/data/pdfs"`. В ноде Read PDF путь берётся только если он начинается с `/data/pdfs`:  
`(($json.body?.pdf_path || $json.pdf_path) || '').toString().startsWith('/data/pdfs') ? ... : ''`.

**Вывод:** Соответствует: и глобальное ограничение, и явная проверка префикса `/data/pdfs` в выражении.

---

### 1.5 HTTP Request (Notify Editor Bot) — retry и ошибки

**Context7 (n8n-docs):** В настройках ноды есть Retry on Fail, Max Tries, Wait Between Tries; для обработки ошибок можно использовать второй выход ноды.

**У нас:** `retryOnFail: true`, `maxTries: 2`, `waitBetweenTries: 10000`, `onError: "continueErrorOutput"`. Ошибка идёт в Retry Attempt → IF Retry → повтор Notify или Notify Failed Response. Таймаут 120000 ms.

**Вывод:** Соответствует. Рекомендация docs по таймаутам для rate limit применима; у нас вызов к editor-bot — таймаут 120 с разумен.

---

### 1.6 Set (Duplicate response, Notify Failed Response)

**Context7:** Set node задаёт поля выхода; для ответа webhook при lastNode важно, чтобы концевая нода возвращала нужный JSON.

**У нас:** Duplicate response — `ok: true`, `skipped: "duplicate"`. Notify Failed Response — `ok: false`, `error: "notify_failed"`. Обе ноды — концы веток, без исходящих связей.

**Вывод:** Соответствует.

---

## 2. Editor-bot (aiohttp, безопасность)

### 2.1 aiohttp AppRunner — shutdown

**Context7 (aiohttp):** При использовании AppRunner для остановки сервера нужно вызывать `await runner.cleanup()`. Без этого не выполняется корректный graceful shutdown (остановка приёма новых соединений, закрытие keep-alive и т.д.).

**У нас:** В `main.py` в `finally` после остановки polling и закрытия сессии бота вызывается `await runner.cleanup()`, затем `await close_pool(pool)`.

**Вывод:** Соответствует.

---

### 2.2 Сравнение webhook-токена

**Context7 / best practice (Python):** Для сравнения секретов и токенов следует использовать constant-time сравнение, чтобы снизить риск timing attack (например `secrets.compare_digest`).

**У нас:** В `n8n_receiver.py` используется `secrets.compare_digest(auth[7:].strip(), expected_token.strip())`; при пустом `expected_token` авторизация пропускается (return True).

**Вывод:** Соответствует рекомендациям по безопасности.

---

## 3. Сводная таблица

| Компонент | Что проверено | Context7 / docs | Статус |
|-----------|----------------|------------------|--------|
| Webhook | responseMode lastNode | Ответ = выход последней ноды | OK |
| Merge | combinationMode | mergeByPosition для склейки по позиции | OK |
| Postgres Check duplicate | Запрос + экранирование | Выражения в Query; параметры в UI при необходимости | OK (компромисс) |
| Postgres INSERT | То же | То же | OK (компромисс) |
| Read PDF | Путь к файлу | N8N_RESTRICT + проверка префикса | OK |
| HTTP Notify Editor Bot | Retry, error output, timeout | Retry on Fail, второй выход, таймаут | OK |
| Set (ответы) | Концевые ноды | lastNode возвращает их выход | OK |
| Editor-bot main | runner.cleanup() | Graceful shutdown | OK |
| Editor-bot auth | Сравнение токена | secrets.compare_digest | OK |

---

## 4. Рекомендации на будущее

1. **Postgres:** После обновления n8n проверить, передаются ли Query Parameters из JSON (или настроить параметры в UI и переэкспортировать workflow).
2. **Webhook:** При желании явно задавать ответы и коды (например 503 при notify_failed) можно ввести ноды Respond to Webhook в трёх ветках и переключить Webhook на "Using Respond to Webhook node".
3. **Editor-bot:** Пустой webhook token по-прежнему отключает проверку; в проде лучше требовать непустой токен или отдельную переменную (например ALLOW_EMPTY_WEBHOOK_TOKEN=false).

Проверка выполнена по библиотекам: `/n8n-io/n8n-docs`, `/aio-libs/aiohttp`.
