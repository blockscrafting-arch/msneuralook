"""Background worker: send pending outbox rows to n8n webhook."""

import asyncio
import time

import asyncpg
import structlog

from src.database.outbox import (
    get_pending_outbox_batch,
    mark_outbox_sent,
    mark_outbox_failed,
)
from src.services.webhook_sender import send_to_n8n_webhook

log = structlog.get_logger()

OUTBOX_POLL_INTERVAL_SEC = 30
OUTBOX_TABLE_MISSING_LOG_INTERVAL_SEC = 300  # remind once per 5 min


async def run_outbox_worker(
    pool: asyncpg.Pool,
    webhook_url: str,
    buffer_minutes: int = 0,
) -> None:
    """
    Loop: fetch pending outbox rows, POST to n8n, mark sent or failed with backoff.
    Runs until cancelled. If table userbot_outbox is missing, logs a hint and keeps running.
    If buffer_minutes > 0: one post per cycle, then sleep buffer_minutes before next cycle.
    """
    last_table_missing_log = 0.0
    batch_limit = 1 if buffer_minutes > 0 else 10
    while True:
        try:
            batch = await get_pending_outbox_batch(pool, limit=batch_limit)
            for row in batch:
                ok = await send_to_n8n_webhook(
                    webhook_url,
                    post_text=row.get("post_text") or "",
                    pdf_path=row.get("pdf_path") or "",
                    message_id=row["message_id"],
                    channel_id=row["channel_id"],
                    source_channel=row.get("source_channel") or row["channel_id"],
                )
                if ok:
                    await mark_outbox_sent(pool, row["id"])
                    log.info("outbox_sent", outbox_id=row["id"], message_id=row["message_id"])
                    if buffer_minutes > 0:
                        await asyncio.sleep(buffer_minutes * 60)
                else:
                    attempts = (row.get("attempts") or 0) + 1
                    await mark_outbox_failed(
                        pool,
                        row["id"],
                        error="webhook returned False or all retries failed",
                        attempts=attempts,
                    )
            await asyncio.sleep(OUTBOX_POLL_INTERVAL_SEC)
        except asyncio.CancelledError:
            log.info("outbox_worker_stopped")
            raise
        except asyncpg.UndefinedTableError as e:
            if "userbot_outbox" in str(e):
                now_ts = time.monotonic()
                if now_ts - last_table_missing_log >= OUTBOX_TABLE_MISSING_LOG_INTERVAL_SEC:
                    last_table_missing_log = now_ts
                    log.warning(
                        "outbox_table_missing",
                        msg="Table userbot_outbox does not exist. Apply migration: docker compose exec -T postgres psql -U parser_user -d parser_db < init_db/migrate_006_userbot_outbox.sql",
                    )
            else:
                log.error("outbox_worker_error", error=str(e), exc_info=True)
            await asyncio.sleep(OUTBOX_POLL_INTERVAL_SEC)
        except Exception as e:
            log.error("outbox_worker_error", error=str(e), exc_info=True)
            await asyncio.sleep(OUTBOX_POLL_INTERVAL_SEC)
