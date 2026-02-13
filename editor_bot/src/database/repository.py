"""CRUD operations for posts and config; audit_log writes."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
import structlog

from src.database.models import Post

log = structlog.get_logger()

# Allowed post statuses (must match DB CHECK constraint)
VALID_STATUSES = frozenset({
    "processing", "pending_review", "approved", "rejected",
    "published", "scheduled", "publishing", "send_failed", "publish_failed",
})


async def get_post_by_id(pool: asyncpg.Pool, post_id: int) -> Optional[Post]:
    """Load post by id. Does not load scheduled_at (use get_scheduled_posts_due for that)."""
    row = await pool.fetchrow(
        "SELECT * FROM posts WHERE id = $1",
        post_id,
    )
    if not row:
        return None
    return Post(
        id=row["id"],
        source_channel=row["source_channel"],
        source_message_id=row["source_message_id"],
        original_text=row["original_text"],
        pdf_path=row["pdf_path"] or "",
        extracted_text=row["extracted_text"],
        summary=row["summary"],
        edited_summary=row["edited_summary"],
        editor_message_id=row["editor_message_id"],
        status=row["status"],
        scheduled_at=row.get("scheduled_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        delivery_attempts=int(row.get("delivery_attempts", 0)),
        last_delivery_error=row.get("last_delivery_error"),
        next_retry_at=row.get("next_retry_at"),
    )


async def get_scheduled_posts_due(pool: asyncpg.Pool) -> list[Post]:
    """Return posts with status=scheduled and scheduled_at <= NOW(). Returns [] if column missing."""
    try:
        rows = await pool.fetch(
            """
            SELECT id, source_channel, source_message_id, original_text, pdf_path,
                   extracted_text, summary, edited_summary, editor_message_id, status,
                   scheduled_at, created_at, updated_at
            FROM posts
            WHERE status = 'scheduled' AND scheduled_at IS NOT NULL AND scheduled_at <= NOW()
            ORDER BY scheduled_at
            """
        )
    except asyncpg.UndefinedColumnError:
        return []
    return [
        Post(
            id=r["id"],
            source_channel=r["source_channel"],
            source_message_id=r["source_message_id"],
            original_text=r["original_text"],
            pdf_path=r["pdf_path"] or "",
            extracted_text=r["extracted_text"],
            summary=r["summary"],
            edited_summary=r["edited_summary"],
            editor_message_id=r["editor_message_id"],
            status=r["status"],
            scheduled_at=r["scheduled_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def get_scheduled_posts_upcoming(
    pool: asyncpg.Pool, limit: int = 50
) -> list[Post]:
    """Return posts with status=scheduled, ordered by scheduled_at ASC (for schedule list view)."""
    try:
        rows = await pool.fetch(
            """
            SELECT id, source_channel, source_message_id, original_text, pdf_path,
                   extracted_text, summary, edited_summary, editor_message_id, status,
                   scheduled_at, created_at, updated_at
            FROM posts
            WHERE status = 'scheduled' AND scheduled_at IS NOT NULL
            ORDER BY scheduled_at ASC
            LIMIT $1
            """,
            limit,
        )
    except asyncpg.UndefinedColumnError:
        return []
    return [
        Post(
            id=r["id"],
            source_channel=r["source_channel"],
            source_message_id=r["source_message_id"],
            original_text=r["original_text"],
            pdf_path=r["pdf_path"] or "",
            extracted_text=r["extracted_text"],
            summary=r["summary"],
            edited_summary=r["edited_summary"],
            editor_message_id=r["editor_message_id"],
            status=r["status"],
            scheduled_at=r["scheduled_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def update_post_status(
    pool: asyncpg.Pool,
    post_id: int,
    status: str,
    edited_summary: Optional[str] = None,
    editor_message_id: Optional[int] = None,
    scheduled_at: Optional[Any] = None,
) -> None:
    """Update post status and optionally edited_summary / editor_message_id / scheduled_at."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid post status: {status!r}; allowed: {sorted(VALID_STATUSES)}")
    if scheduled_at is not None:
        await pool.execute(
            """
            UPDATE posts SET status = $1, scheduled_at = $2, updated_at = NOW()
            WHERE id = $3
            """,
            status,
            scheduled_at,
            post_id,
        )
    elif edited_summary is not None and editor_message_id is not None:
        await pool.execute(
            """
            UPDATE posts SET status = $1, edited_summary = $2, editor_message_id = $3, updated_at = NOW()
            WHERE id = $4
            """,
            status,
            edited_summary,
            editor_message_id,
            post_id,
        )
    elif edited_summary is not None:
        await pool.execute(
            "UPDATE posts SET status = $1, edited_summary = $2, updated_at = NOW() WHERE id = $3",
            status,
            edited_summary,
            post_id,
        )
    elif editor_message_id is not None:
        await pool.execute(
            "UPDATE posts SET status = $1, editor_message_id = $2, updated_at = NOW() WHERE id = $3",
            status,
            editor_message_id,
            post_id,
        )
    else:
        await pool.execute(
            "UPDATE posts SET status = $1, updated_at = NOW() WHERE id = $2",
            status,
            post_id,
        )


DELIVERY_RETRY_MAX_ATTEMPTS = 5
DELIVERY_RETRY_BACKOFF_BASE_SEC = 60


async def get_posts_for_delivery_retry(pool: asyncpg.Pool, limit: int = 5) -> list[Post]:
    """Return posts with status processing/send_failed, next_retry_at due, delivery_attempts < max."""
    try:
        rows = await pool.fetch(
            """
            SELECT * FROM posts
            WHERE status IN ('processing', 'send_failed')
              AND editor_message_id IS NULL
              AND (next_retry_at IS NULL OR next_retry_at <= NOW())
              AND COALESCE(delivery_attempts, 0) < $1
            ORDER BY next_retry_at NULLS FIRST, id
            LIMIT $2
            """,
            DELIVERY_RETRY_MAX_ATTEMPTS,
            limit,
        )
    except asyncpg.UndefinedColumnError:
        return []
    return [
        Post(
            id=r["id"],
            source_channel=r["source_channel"],
            source_message_id=r["source_message_id"],
            original_text=r["original_text"],
            pdf_path=r["pdf_path"] or "",
            extracted_text=r["extracted_text"],
            summary=r["summary"],
            edited_summary=r["edited_summary"],
            editor_message_id=r["editor_message_id"],
            status=r["status"],
            scheduled_at=r.get("scheduled_at"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            delivery_attempts=int(r.get("delivery_attempts", 0)),
            last_delivery_error=r.get("last_delivery_error"),
            next_retry_at=r.get("next_retry_at"),
        )
        for r in rows
    ]


async def update_post_delivery_failed(
    pool: asyncpg.Pool,
    post_id: int,
    error: str,
    attempts: int,
) -> None:
    """Set delivery_attempts, last_delivery_error, next_retry_at; if attempts >= max set status=send_failed."""
    if attempts >= DELIVERY_RETRY_MAX_ATTEMPTS:
        await pool.execute(
            """
            UPDATE posts
            SET status = 'send_failed', delivery_attempts = $2, last_delivery_error = $3,
                next_retry_at = NULL, updated_at = NOW()
            WHERE id = $1
            """,
            post_id,
            attempts,
            (error or "")[:2000],
        )
    else:
        delay_sec = DELIVERY_RETRY_BACKOFF_BASE_SEC * (2 ** attempts)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay_sec)
        await pool.execute(
            """
            UPDATE posts
            SET delivery_attempts = $2, last_delivery_error = $3, next_retry_at = $4, updated_at = NOW()
            WHERE id = $1
            """,
            post_id,
            attempts,
            (error or "")[:2000],
            next_retry,
        )


async def clear_scheduled_return_to_pending(pool: asyncpg.Pool, post_id: int) -> bool:
    """Set status to pending_review and clear scheduled_at. Returns True if row was updated."""
    result = await pool.execute(
        """
        UPDATE posts SET status = 'pending_review', scheduled_at = NULL, updated_at = NOW()
        WHERE id = $1 AND status = 'scheduled'
        """,
        post_id,
    )
    return result == "UPDATE 1"


# How long a post can stay in 'publishing' before we reset to pending_review (seconds)
PUBLISHING_STUCK_THRESHOLD_SEC = 600  # 10 minutes
# How long a post can stay in 'send_failed' before we reset delivery_attempts for one more retry (seconds)
SEND_FAILED_RETRY_AFTER_SEC = 3600  # 1 hour


async def reset_stuck_publishing_posts(pool: asyncpg.Pool) -> int:
    """
    Set status back to 'pending_review' for posts stuck in 'publishing' longer than threshold.
    Returns number of rows updated.
    """
    result = await pool.execute(
        """
        UPDATE posts SET status = 'pending_review', updated_at = NOW()
        WHERE status = 'publishing'
          AND updated_at < NOW() - INTERVAL '1 second' * $1
        """,
        PUBLISHING_STUCK_THRESHOLD_SEC,
    )
    # result is like "UPDATE 2"
    if result.startswith("UPDATE "):
        try:
            return int(result.split()[1])
        except (IndexError, ValueError):
            return 0
    return 0


async def reset_send_failed_for_retry(pool: asyncpg.Pool) -> int:
    """
    For posts in send_failed for longer than threshold, reset delivery_attempts to 0 and
    next_retry_at to NOW() so they are picked up by delivery retry again. Returns count updated.
    """
    try:
        result = await pool.execute(
            """
            UPDATE posts
            SET delivery_attempts = 0, last_delivery_error = NULL, next_retry_at = NOW(), updated_at = NOW()
            WHERE status = 'send_failed'
              AND updated_at < NOW() - INTERVAL '1 second' * $1
            """,
            SEND_FAILED_RETRY_AFTER_SEC,
        )
    except asyncpg.UndefinedColumnError:
        return 0
    if result.startswith("UPDATE "):
        try:
            return int(result.split()[1])
        except (IndexError, ValueError):
            return 0
    return 0


async def claim_pending_for_publish(pool: asyncpg.Pool, post_id: int) -> bool:
    """Set status to 'publishing' only if current status is pending_review. Returns True if row was updated."""
    result = await pool.execute(
        """
        UPDATE posts SET status = 'publishing', updated_at = NOW()
        WHERE id = $1 AND status = 'pending_review'
        """,
        post_id,
    )
    return result == "UPDATE 1"


async def get_post_counts_by_status(pool: asyncpg.Pool) -> dict[str, int]:
    """Return counts of posts per status (e.g. {'pending_review': 2, 'published': 5})."""
    rows = await pool.fetch(
        "SELECT status, count(*)::int AS cnt FROM posts GROUP BY status"
    )
    return {r["status"]: r["cnt"] for r in rows}


async def add_audit_log(
    pool: asyncpg.Pool,
    post_id: Optional[int],
    action: str,
    actor: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Append row to audit_log."""
    await pool.execute(
        """
        INSERT INTO audit_log (post_id, action, actor, details) VALUES ($1, $2, $3, $4)
        """,
        post_id,
        action,
        actor,
        json.dumps(details) if details is not None else None,
    )
