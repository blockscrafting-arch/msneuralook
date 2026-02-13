"""Outbox table: reliable delivery of posts to n8n."""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import asyncpg
import structlog

log = structlog.get_logger()

OUTBOX_MAX_ATTEMPTS = 5
OUTBOX_BACKOFF_BASE_SEC = 60


async def insert_outbox(
    pool: asyncpg.Pool,
    *,
    channel_id: str,
    message_id: int,
    pdf_path: str = "",
    pdf_missing: bool = False,
    post_text: str = "",
    source_channel: str = "",
) -> Optional[int]:
    """
    Insert or ignore outbox row. Returns outbox id if inserted, None if duplicate (channel_id, message_id).
    """
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO userbot_outbox
                (channel_id, message_id, pdf_path, pdf_missing, post_text, source_channel, status, attempts, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', 0, NOW())
            ON CONFLICT (channel_id, message_id) DO NOTHING
            RETURNING id
            """,
            channel_id,
            message_id,
            pdf_path or "",
            pdf_missing,
            post_text or "",
            source_channel or channel_id,
        )
        return row["id"] if row else None
    except Exception as e:
        log.error("outbox_insert_failed", channel_id=channel_id, message_id=message_id, error=str(e))
        return None


async def get_pending_outbox_batch(
    pool: asyncpg.Pool,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return pending rows where next_retry_at is null or past, ordered by created_at."""
    now = datetime.now(timezone.utc)
    rows = await pool.fetch(
        """
        SELECT id, channel_id, message_id, pdf_path, pdf_missing, post_text, source_channel, attempts
        FROM userbot_outbox
        WHERE status = 'pending'
          AND attempts < $1
          AND (next_retry_at IS NULL OR next_retry_at <= $2)
        ORDER BY created_at
        LIMIT $3
        """,
        OUTBOX_MAX_ATTEMPTS,
        now,
        limit,
    )
    return [dict(r) for r in rows]


async def mark_outbox_sent(pool: asyncpg.Pool, outbox_id: int) -> None:
    """Set status=sent, updated_at=NOW()."""
    await pool.execute(
        "UPDATE userbot_outbox SET status = 'sent', updated_at = NOW() WHERE id = $1",
        outbox_id,
    )


async def mark_outbox_failed(
    pool: asyncpg.Pool,
    outbox_id: int,
    error: str,
    attempts: int,
) -> None:
    """Set last_error, attempts, next_retry_at (backoff), or status=failed if attempts >= max."""
    if attempts >= OUTBOX_MAX_ATTEMPTS:
        await pool.execute(
            """
            UPDATE userbot_outbox
            SET status = 'failed', last_error = $2, attempts = $3, updated_at = NOW(), next_retry_at = NULL
            WHERE id = $1
            """,
            outbox_id,
            error[:2000] if error else None,
            attempts,
        )
        log.warning("outbox_marked_failed", outbox_id=outbox_id, attempts=attempts, error=error[:200])
    else:
        delay_sec = OUTBOX_BACKOFF_BASE_SEC * (2 ** attempts)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay_sec)
        await pool.execute(
            """
            UPDATE userbot_outbox
            SET last_error = $2, attempts = $3, next_retry_at = $4, updated_at = NOW()
            WHERE id = $1
            """,
            outbox_id,
            error[:2000] if error else None,
            attempts,
            next_retry,
        )
