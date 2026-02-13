# Повторная отправка постов редакторам

Если пост был создан в БД со статусом `pending_review` (до исправления n8n) и редакторам так и не пришёл, его можно один раз «вернуть в очередь» и переслать.

## Шаг 1: Сброс статуса в БД

На сервере подключиться к Postgres (из каталога проекта):

```bash
docker compose exec postgres psql -U parser_user -d parser_db
```

Выполнить (подставить нужные id):

```sql
UPDATE posts
SET status = 'processing', editor_message_id = NULL
WHERE id IN (65, 66);
```

Выйти: `\q`.

## Шаг 2: Вызвать webhook

После сброса editor-bot при следующем вызове webhook для этого `post_id` увидит статус `processing` и отправит сообщения редакторам.

- Либо в n8n перезапустить выполнение для этих постов (если есть такая возможность).
- Либо один раз вручную отправить POST на webhook editor-bot с телом как в n8n, например:

```json
{
  "post_id": 65,
  "summary": "<саммари из БД или из n8n>",
  "pdf_path": "<путь к PDF или пусто>",
  "original_text": "<исходный текст или пусто>"
}
```

Заголовок: `Authorization: Bearer <EDITOR_BOT_WEBHOOK_TOKEN>`.

После успешной отправки бот сам выставит `status = 'pending_review'` и `editor_message_id`.
