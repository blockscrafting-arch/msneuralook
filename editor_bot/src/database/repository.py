"""CRUD operations for posts and config; audit_log writes."""

import json
from typing import Any, Optional

import asyncpg
import structlog

from src.database.models import Post

log = structlog.get_logger()


async def get_post_by_id(pool: asyncpg.Pool, post_id: int) -> Optional[Post]:
    """Load post by id."""
    row = await pool.fetchrow(
        """
        SELECT id, source_channel, source_message_id, original_text, pdf_path,
               extracted_text, summary, edited_summary, editor_message_id, status,
               created_at, updated_at
        FROM posts WHERE id = $1
        """,
        post_id,
    )
    if not row:
        return None
    return Post(
        id=row["id"],
        source_channel=row["source_channel"],
        source_message_id=row["source_message_id"],
        original_text=row["original_text"],
        pdf_path=row["pdf_path"],
        extracted_text=row["extracted_text"],
        summary=row["summary"],
        edited_summary=row["edited_summary"],
        editor_message_id=row["editor_message_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_post_status(
    pool: asyncpg.Pool,
    post_id: int,
    status: str,
    edited_summary: Optional[str] = None,
    editor_message_id: Optional[int] = None,
) -> None:
    """Update post status and optionally edited_summary / editor_message_id."""
    if edited_summary is not None and editor_message_id is not None:
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
