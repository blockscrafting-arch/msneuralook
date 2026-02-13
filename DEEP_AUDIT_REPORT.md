# Deep Code Review & Business Audit — Editor Bot / Webhook

Жёсткий аудит без прикрас. Только уязвимости, говнокод и логические дыры.

---

## КРИТИЧНО

### 1. Двойная публикация поста (race approve)

**Файл:** `editor_bot/src/database/repository.py` — `claim_pending_for_publish`.

```python
UPDATE posts SET status = 'publishing', updated_at = NOW()
WHERE id = $1 AND status IN ('pending_review', 'publishing', 'processing')
```

**Проблема:** Условие включает `'publishing'`. Первый редактор нажимает «Опубликовать» → статус становится `publishing` → идёт публикация. Второй редактор в это время тоже нажимает «Опубликовать» → тот же UPDATE снова выполняется (строка подходит: статус уже `publishing`) → возвращается `UPDATE 1` → оба получают `updated=True` и оба вызывают `publish_to_all_channels`. **Один и тот же пост публикуется в канал дважды.**

**Исправление:** Claim только из `pending_review`: `WHERE id = $1 AND status = 'pending_review'`. Тогда второй редактор получит `UPDATE 0` и корректное «Пост уже обработан».

---

### 2. Webhook без авторизации при пустом токене

**Файл:** `editor_bot/src/webhook/n8n_receiver.py` — `_check_webhook_auth`.

```python
if not expected_token or not expected_token.strip():
    return True
```

**Проблема:** Если `EDITOR_BOT_WEBHOOK_TOKEN` в `.env` не задан или пустой, **любой** может слать POST на `/incoming/post` и подсовывать произвольные `post_id`, `summary`, `pdf_path`. Это создаёт риск спама редакторам, подмены контента и нагрузки на БД/бот. В проде токен обязан быть задан и не пустой.

**Рекомендация:** В проде падать при старте, если webhook включён, а токен пустой; либо возвращать 401 при пустом токене (не «разрешать» запрос).

---

### 3. Lazy-init локов — гонка при первом вызове

**Файл:** `editor_bot/src/webhook/n8n_receiver.py` — `_get_serial_send_lock`, `_get_sending_lock`, `_get_webhook_lock`.

```python
if _serial_send_lock is None:
    _serial_send_lock = asyncio.Lock()
return _serial_send_lock
```

**Проблема:** Два корутина могут одновременно увидеть `None` и оба создать **разные** экземпляры `asyncio.Lock()`. Один будет использоваться в одном месте, другой — в другом. Сериализация «один пост за раз» ломается: два поста могут отправляться параллельно. Редко, но возможно при старте под нагрузкой.

**Исправление:** Инициализировать лока при импорте модуля или под защитой отдельного lock при первом вызове (double-checked locking с asyncio.Lock для инита).

---

## СЕРЬЁЗНО

### 4. Переменные после `async with`: возможный NameError при исключении

**Файл:** `editor_bot/src/webhook/n8n_receiver.py`, строки 341–346.

После выхода из `async with _get_serial_send_lock()` выполняется:

```python
for chat_id in remaining_editors:
    await _send_to_one_editor(bot, chat_id, chunks, kb, post_id, pdf_path, use_pdf_file)
```

`chunks`, `kb`, `use_pdf_file` определены **внутри** `try` (внутри `async with`). Если исключение произойдёт **до** их присвоения (например, в `get_post_by_id` или при первом `update_post_status` после break), мы выйдем из `with` через `except`/`finally` и попадём в этот цикл. Тогда `chunks`, `kb`, `use_pdf_file` могут быть не определены → **NameError**. На практике мы выходим в этот цикл только после нормального break (первый успех), но путь с исключением после break (например, в `add_audit_log`) тоже ведёт сюда, и там переменные уже заданы. Риск — если когда-нибудь добавят ранний выход или изменят порядок присвоений.

**Рекомендация:** Инициализировать `chunks`, `kb`, `use_pdf_file` до входа в `try` (например, `chunks = []`, `kb = None`, `use_pdf_file = False`) или выполнять цикл по `remaining_editors` только если они точно заданы (флаг или проверка).

---

### 5. Нет лимита на размер тела webhook

**Файл:** `editor_bot/src/webhook/n8n_receiver.py` — `handle_incoming_post`.

Тело запроса читается как `await request.json()` без ограничения размера. Злоумышленник может отправить гигантский JSON и исчерпать память или надолго занять поток. aiohttp по умолчанию ограничивает размер, но лучше явно задать лимит и при превышении возвращать 413.

---

### 6. Audit log при частичной доставке вводит в заблуждение

**Файл:** `editor_bot/src/webhook/n8n_receiver.py` — блок `except Exception` в `_send_to_editors_background`.

При любом исключении в фоне пишется `add_audit_log(pool, post_id, "send_to_editor_failed")`. Но к этому моменту первый редактор мог уже получить пост (статус `pending_review`, `editor_message_id` установлен). В аудите будет «send_to_editor_failed», хотя доставка одному редактору прошла. Для расследований это misleading.

**Рекомендация:** Либо разделять «полный провал» и «ошибка после первой успешной доставки», либо писать в details, что часть редакторов уже получила пост.

---

### 7. `update_post_status`: статус не валидируется

**Файл:** `editor_bot/src/database/repository.py` — `update_post_status`.

Любая строка передаётся в SQL как новый статус. В БД есть CHECK по списку статусов (из миграций), но в коде нет явной проверки. Опечатка или логическая ошибка (например, `status="pendng_review"`) приведёт к исключению на уровне БД, а не к явной ошибке в репозитории. Плюс нет защиты от перехода из «конечного» статуса (published) обратно в рабочий без явного сценария.

**Рекомендация:** В репозитории или сервисе явно проверять допустимые переходы статусов (state machine) и возвращать ошибку/логировать при недопустимых.

---

## СРЕДНЕ / КОД-КАЧЕСТВО

### 8. Дублирование логики «post not found / duplicate»

В `handle_incoming_post` пост запрашивается дважды: до `webhook_lock` (для 404) и внутри lock (для проверки статуса и создания таска). В `_send_to_editors_background` снова проверяются «post not found» и «duplicate». Можно упростить и держать один источник истины (например, один запрос под lock и передача поста в background или чёткое разграничение: webhook только создаёт таск, вся проверка — в фоне).

---

### 9. Строки 395 и 227: разная проверка статуса

- В webhook (handle_incoming_post): `post.status != "processing" or post.editor_message_id is not None` → считаем «уже отправлен».
- В фоне (_send_to_editors_background): `post.status not in ("processing", "send_failed") or post.editor_message_id is not None`.

В фоне мы ещё допускаем `send_failed` (ретрай). В webhook — нет. Если пост в `send_failed`, webhook вернёт «already_sent» (потому что editor_message_id может быть не null после прошлой попытки) или «post not found» в зависимости от того, как трактовать. Сценарии ретрая (scheduler vs n8n) различаются — лучше явно описать в коде или комментарии, когда какой путь срабатывает, чтобы не сломать ретраи.

---

### 10. Scheduler: ретрай доставки без лимита на одновременные посты

**Файл:** `editor_bot/src/services/scheduler.py`.

В цикле для каждого поста из `get_posts_for_delivery_retry(pool, limit=25)` вызывается `await _send_to_editors_background(...)`. До 25 постов подряд идут в очередь: каждый ждёт своей очереди по `_serial_send_lock`, но сам scheduler не ограничивает, сколько таких «ожидающих» задач висит. При большом бэклоге все они будут ждать друг друга и ретраи. Логика корректна, но при 25 постах и 3 редакторах с таймаутами это может надолго занять поток. Рассмотреть уменьшение `limit` или приоритизацию.

---

### 11. Path safety: симлинки

**Файл:** `editor_bot/src/webhook/n8n_receiver.py` — `_is_pdf_path_safe`.

Используется `os.path.realpath` — симлинки раскрываются. То есть симлинк внутри `pdf_storage_path`, указывающий наружу, будет отклонён. Это ок. Но если `allowed_base` сам по себе симлинк, поведение зависит от ОС. Для типичного деплоя (Linux, один каталог) риска нет, но в обзоре стоит отметить.

---

### 12. ZoneInfo и tzdata в тестах

**Файл:** `editor_bot/src/bot/handlers/review.py` — `MSK = ZoneInfo("Europe/Moscow")`.

На Windows без пакета `tzdata` тесты, импортирующие `review`, падают. Это не баг продакшена (Linux обычно с tzdata), но CI/локальная разработка на Windows ломается. Имеет смысл документировать зависимость или подменять в тестах.

---

## РЕЗЮМЕ

| Уровень   | Что делать в первую очередь |
|----------|-----------------------------|
| Критично | Исправить `claim_pending_for_publish`: только `status = 'pending_review'`. Обязательный webhook token в проде или 401 при пустом. Инициализировать lock’и без гонки (при импорте или под lock’ом). |
| Серьёзно | Защитить цикл по `remaining_editors` от неопределённых переменных; лимит размера тела webhook; уточнить audit_log при частичной доставке; валидация/state machine для статусов поста. |
| Средне   | Убрать дублирование проверок поста, выровнять условия статусов webhook vs background, ограничение/приоритизация ретраев в scheduler, зависимость tzdata в тестах. |

План исправлений лучше начать с пунктов 1–3 (критично), затем 4–7 (серьёзно).
